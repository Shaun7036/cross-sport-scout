"""Shared EDA, descriptive archetypes, and honestly separated baseline models.

Model selection uses 2024 (2024-25 outside NFL). The 2025 season is evaluated
after selection. Returning-player cohorts are defined by the previous season:
players disappearing from the following appearance feed remain zero-opportunity
outcomes. Physical association models also hold out entire athletes.
"""

from __future__ import annotations

import hashlib
import html
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    adjusted_rand_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    silhouette_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from possession_lab.io import save_frame, sha256, write_json

RANDOM_STATE = 42
VALIDATION_SEASON = 2024
TEST_SEASON = 2025
RATE_SCALE = 100.0


def safe_spearman(y: np.ndarray, predicted: np.ndarray) -> float | None:
    if len(y) < 3 or np.std(y) == 0 or np.std(predicted) == 0:
        return None
    return float(spearmanr(y, predicted).statistic)


def regression_scores(y, predicted) -> dict:
    y, predicted = np.asarray(y, dtype=float), np.asarray(predicted, dtype=float)
    valid = np.isfinite(y) & np.isfinite(predicted)
    y, predicted = y[valid], predicted[valid]
    if not len(y):
        return {"n": 0}
    return {
        "n": len(y),
        "mae": float(mean_absolute_error(y, predicted)),
        "rmse": float(np.sqrt(mean_squared_error(y, predicted))),
        "spearman": safe_spearman(y, predicted),
        "r2": float(r2_score(y, predicted)) if len(y) > 1 and np.std(y) else None,
    }


def _preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    numeric_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent", keep_empty_features=True)),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    return ColumnTransformer(
        [
            ("numeric", numeric_pipeline, numeric),
            ("categorical", categorical_pipeline, categorical),
        ]
    )


def make_regressor(numeric: list[str], categorical: list[str], alpha: float) -> Pipeline:
    return Pipeline(
        [
            ("prepare", _preprocessor(numeric, categorical)),
            ("model", Ridge(alpha=alpha)),
        ]
    )


def make_classifier(numeric: list[str], categorical: list[str], c: float = 1.0) -> Pipeline:
    return Pipeline(
        [
            ("prepare", _preprocessor(numeric, categorical)),
            ("model", LogisticRegression(C=c, max_iter=1500, random_state=RANDOM_STATE)),
        ]
    )


def validate_panel(panel: pd.DataFrame, metrics: dict[str, str]) -> pd.DataFrame:
    required = {"player_id", "name", "season", "role", "opportunity"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"Panel lacks {missing}")
    frame = panel.copy()
    if frame.player_id.isna().any():
        raise ValueError("Null canonical player ID")
    frame["player_id"] = frame.player_id.astype(str)
    frame["season"] = pd.to_numeric(frame.season, errors="raise").astype(int)
    frame["role"] = frame.role.fillna("UNKNOWN").astype(str)
    if frame.duplicated(["player_id", "season"]).any():
        raise ValueError("Duplicate player-season rows: trades must be aggregated first")
    frame["opportunity"] = pd.to_numeric(frame.opportunity, errors="coerce")
    if frame.opportunity.dropna().lt(0).any():
        raise ValueError("Negative opportunity")
    for column in set(metrics.values()):
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[column].dropna().lt(0).any():
            raise ValueError(f"Negative count in {column}")
    for column in ["height_cm", "weight_kg", "age"]:
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values(["player_id", "season"]).reset_index(drop=True)


def build_forecast_pairs(panel: pd.DataFrame, metrics: dict[str, str]) -> pd.DataFrame:
    """Previous-season candidates left-join next season, including nonreturners."""
    seasons = set(panel.season.unique())
    future = panel[["player_id", "season", "opportunity", *dict.fromkeys(metrics.values())]].copy()
    future = future.rename(
        columns={
            "opportunity": "target_opportunity",
            **{column: f"target_{column}" for column in set(metrics.values())},
        }
    )
    history = panel.copy()
    history = history.sort_values(["player_id", "season"]).copy()
    history["log_lag_opportunity"] = np.log1p(history.opportunity)
    history["ewma_log_opportunity"] = history.groupby("player_id")["log_lag_opportunity"].transform(
        lambda x: x.ewm(span=3, adjust=False, ignore_na=True).mean()
    )
    for label, column in metrics.items():
        history[f"lag_{label}_rate"] = RATE_SCALE * history[column] / history.opportunity.replace(0, np.nan)
        history[f"ewma_{label}_rate"] = history.groupby("player_id")[f"lag_{label}_rate"].transform(
            lambda x: x.ewm(span=3, adjust=False, ignore_na=True).mean()
        )
    history["target_season"] = history.season + 1
    history = history[history.target_season.isin(seasons)].copy()
    history["lag_opportunity"] = history.opportunity
    history["log_lag_opportunity"] = np.log1p(history.opportunity)
    history["lag_age"] = history.age
    history["prior_role"] = history.role
    # Forecast features contain no current physical listing. The common source
    # snapshots do not prove these listings were available before each anchor.
    for label, column in metrics.items():
        history[f"lag_{label}_rate"] = RATE_SCALE * history[column] / history.opportunity.replace(0, np.nan)
        history[f"lag_{label}_count"] = history[column]
    merged = history.merge(
        future,
        left_on=["player_id", "target_season"],
        right_on=["player_id", "season"],
        how="left",
        suffixes=("", "_future"),
        validate="one_to_one",
        indicator="future_join",
    )
    absent = merged.future_join.eq("left_only")
    merged.loc[absent, "target_opportunity"] = 0
    for column in set(metrics.values()):
        # A player with no opportunity cannot have an on-field count. Source
        # missingness for a present player remains null.
        merged.loc[absent | merged.target_opportunity.eq(0), f"target_{column}"] = 0
    merged["target_appeared"] = merged.target_opportunity.gt(0).astype(int)
    return merged


def _split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        frame[frame.target_season.lt(VALIDATION_SEASON)],
        frame[frame.target_season.eq(VALIDATION_SEASON)],
        frame[frame.target_season.eq(TEST_SEASON)],
    )


def _role_mean(train: pd.DataFrame, value: pd.Series, evaluation: pd.DataFrame) -> np.ndarray:
    values = pd.DataFrame({"role": train.prior_role, "value": np.asarray(value)})
    by_role = values.groupby("role").value.mean()
    return evaluation.prior_role.map(by_role).fillna(values.value.mean()).to_numpy(float)


def forecast_models(panel: pd.DataFrame, metrics: dict[str, str], root: Path, sport: str) -> dict:
    pairs = build_forecast_pairs(panel, metrics)
    report_dir, model_dir = root / "reports" / sport, root / "models" / sport
    model_dir.mkdir(parents=True, exist_ok=True)
    save_frame(pairs, root / "data" / "processed" / sport / "forecast_pairs.parquet")
    train, validation, test = _split(pairs)
    contract = {
        "training_target_seasons": sorted(train.target_season.unique().tolist()),
        "validation_target_season": VALIDATION_SEASON,
        "test_target_season": TEST_SEASON,
        "cohort": "Prior-season roster/appearance candidates, including subsequent zero-opportunity players.",
        "forecast_type": "Retrospective temporal evaluation with corrected final source snapshots; not an audited historical live forecast.",
        "physical_features_in_forecast": False,
        "normalization": "Rate per 100 sport-specific opportunity units; cross-sport raw rates are not compared.",
    }
    if len(train) < 100 or len(validation) < 20 or len(test) < 20:
        return {"status": "insufficient_temporal_history", "split": contract, "rows": len(pairs)}
    numeric = [
        "log_lag_opportunity",
        "ewma_log_opportunity",
        "lag_age",
        *[f"lag_{label}_rate" for label in metrics],
        *[f"ewma_{label}_rate" for label in metrics],
    ]
    categorical = ["prior_role"]
    numeric = [c for c in numeric if train[c].notna().sum() >= 20]
    features = numeric + categorical
    rows, predictions = [], []
    # Availability is distinct from effectiveness. A regularized logistic model
    # is compared to training prevalence without filtering on future exposure.
    t = train[train.target_opportunity.notna()].copy()
    v = validation[validation.target_opportunity.notna()].copy()
    z = test[test.target_opportunity.notna()].copy()
    availability_c = None
    if t.target_appeared.nunique() == 2:
        candidates = []
        for c in [0.1, 1.0, 10.0]:
            clf = make_classifier(numeric, categorical, c)
            clf.fit(t[features], t.target_appeared)
            score = brier_score_loss(v.target_appeared, clf.predict_proba(v[features])[:, 1])
            candidates.append((score, c, clf))
        _, availability_c, selected_clf = min(candidates, key=lambda item: item[0])
    else:
        selected_clf = DummyClassifier(strategy="prior").fit(t[features], t.target_appeared)
    validation_probability = selected_clf.predict_proba(v[features])
    validation_classes = list(selected_clf.classes_)
    validation_probability = (
        validation_probability[:, validation_classes.index(1)]
        if 1 in validation_classes
        else np.zeros(len(v))
    )
    availability_choice = (
        "logistic"
        if brier_score_loss(v.target_appeared, validation_probability)
        < brier_score_loss(v.target_appeared, np.full(len(v), t.target_appeared.mean()))
        else "prevalence"
    )
    refit = pd.concat([t, v], ignore_index=True)
    if availability_c is None:
        fitted_clf = DummyClassifier(strategy="prior").fit(refit[features], refit.target_appeared)
    else:
        fitted_clf = make_classifier(numeric, categorical, availability_c)
        fitted_clf.fit(refit[features], refit.target_appeared)
    joblib.dump(
        {
            "model": fitted_clf,
            "features": features,
            "training_cutoff": 2024,
            "target": "next_season_any_opportunity",
            "selection": availability_choice,
            "prevalence": float(refit.target_appeared.mean()),
        },
        model_dir / "availability.joblib",
    )
    for fold, frame, fitted, prevalence in [
        ("validation", v, selected_clf, t.target_appeared.mean()),
        ("test", z, fitted_clf, refit.target_appeared.mean()),
    ]:
        probabilities = fitted.predict_proba(frame[features])
        classes = list(fitted.classes_)
        probability = probabilities[:, classes.index(1)] if 1 in classes else np.zeros(len(frame))
        for name, estimate in [("prevalence", np.full(len(frame), prevalence)), ("logistic", probability)]:
            record = {
                "task": "availability",
                "target": "any_opportunity",
                "fold": fold,
                "model": name,
                "selected_on_validation": name == availability_choice,
                "n": len(frame),
                "brier": float(brier_score_loss(frame.target_appeared, estimate)),
                "average_precision": float(average_precision_score(frame.target_appeared, estimate))
                if frame.target_appeared.nunique() > 1
                else None,
            }
            rows.append(record)
        if fold == "test":
            chosen_probability = (
                probability if availability_choice == "logistic" else np.full(len(frame), prevalence)
            )
            availability_test = pd.Series(chosen_probability, index=frame.index)
    # Conditional opportunity model; total expected opportunity multiplies the
    # conditional estimate by availability exactly once.
    positive_t = t[t.target_opportunity.gt(0)]
    positive_v = v[v.target_opportunity.gt(0)]
    opp_candidates = []
    for alpha in [1.0, 10.0, 100.0]:
        model = make_regressor(numeric, categorical, alpha)
        model.fit(positive_t[features], np.log1p(positive_t.target_opportunity))
        pred = np.maximum(0, np.expm1(model.predict(positive_v[features])))
        opp_candidates.append((mean_absolute_error(positive_v.target_opportunity, pred), alpha, model))
    _, opp_alpha, opp_selected = min(opp_candidates, key=lambda item: item[0])
    positive_refit = refit[refit.target_opportunity.gt(0)]
    opp_final = make_regressor(numeric, categorical, opp_alpha)
    opp_final.fit(positive_refit[features], np.log1p(positive_refit.target_opportunity))
    opportunity_choice = None
    for fold, frame, fitted, classifier in [
        ("validation", v, opp_selected, selected_clf),
        ("test", z, opp_final, fitted_clf),
    ]:
        classes = list(classifier.classes_)
        proba = classifier.predict_proba(frame[features])
        appearance = proba[:, classes.index(1)] if 1 in classes else np.zeros(len(frame))
        if availability_choice == "prevalence":
            appearance = np.full(
                len(frame), t.target_appeared.mean() if fold == "validation" else refit.target_appeared.mean()
            )
        predicted = appearance * np.maximum(0, np.expm1(fitted.predict(frame[features])))
        persistence = frame.lag_opportunity.fillna(0).to_numpy()
        if fold == "validation":
            opportunity_choice = (
                "hurdle_ridge"
                if mean_absolute_error(frame.target_opportunity, predicted)
                < mean_absolute_error(frame.target_opportunity, persistence)
                else "persistence"
            )
        for name, estimate in [("persistence", persistence), ("hurdle_ridge", predicted)]:
            rows.append(
                {
                    "task": "opportunity",
                    "target": "opportunity",
                    "fold": fold,
                    "selected_on_validation": name == opportunity_choice,
                    "model": name,
                    **regression_scores(frame.target_opportunity, estimate),
                }
            )
        if fold == "test":
            opportunity_test = pd.Series(
                predicted if opportunity_choice == "hurdle_ridge" else persistence, index=frame.index
            )
    joblib.dump(
        {
            "model": opp_final,
            "features": features,
            "training_cutoff": 2024,
            "conditional_on_appearance": True,
            "selection": opportunity_choice,
            "availability_selection": availability_choice,
        },
        model_dir / "opportunity.joblib",
    )
    selections = {}
    for label, column in metrics.items():
        target_column = f"target_{column}"
        work = pairs[pairs.target_opportunity.gt(0) & pairs[target_column].notna()].copy()
        work["target_rate"] = RATE_SCALE * work[target_column] / work.target_opportunity
        a, b, c = _split(work)
        if min(len(a), len(b), len(c)) < 20 or len(a) < 100:
            selections[label] = {"status": "insufficient_temporal_target_coverage"}
            continue
        candidates = []
        for alpha in [1.0, 10.0, 100.0]:
            estimator = make_regressor(numeric, categorical, alpha)
            estimator.fit(
                a[features],
                np.log1p(a.target_rate),
                model__sample_weight=np.sqrt(
                    a.target_opportunity.clip(upper=a.target_opportunity.quantile(0.95))
                ),
            )
            prediction = np.maximum(0, np.expm1(estimator.predict(b[features])))
            candidates.append((mean_absolute_error(b.target_rate, prediction), alpha, estimator))
        val_mae, alpha, estimator = min(candidates, key=lambda item: item[0])
        val_role = _role_mean(a, a.target_rate, b)
        val_persistence = b[f"lag_{label}_rate"].fillna(pd.Series(val_role, index=b.index)).to_numpy()
        validation_candidates = {
            "ridge": val_mae,
            "role_mean": float(mean_absolute_error(b.target_rate, val_role)),
            "persistence": float(mean_absolute_error(b.target_rate, val_persistence)),
        }
        choice = min(validation_candidates, key=validation_candidates.get)
        ab = pd.concat([a, b], ignore_index=True)
        final = make_regressor(numeric, categorical, alpha)
        final.fit(
            ab[features],
            np.log1p(ab.target_rate),
            model__sample_weight=np.sqrt(
                ab.target_opportunity.clip(upper=ab.target_opportunity.quantile(0.95))
            ),
        )
        selections[label] = {
            "selected_on_2024": choice,
            "ridge_alpha": alpha,
            "validation_mae": validation_candidates,
            "n_train": len(a),
            "n_validation": len(b),
            "n_test": len(c),
        }
        selected_validation_estimate = {
            "ridge": np.maximum(0, np.expm1(estimator.predict(b[features]))),
            "role_mean": val_role,
            "persistence": val_persistence,
        }[choice]
        residual = b.target_rate.to_numpy() - selected_validation_estimate
        interval_radius = float(np.quantile(np.abs(residual), 0.9))
        joblib.dump(
            {
                "model": final,
                "features": features,
                "training_cutoff": 2024,
                "rate_scale": RATE_SCALE,
                "target": label,
                "ridge_alpha": alpha,
                "selection": choice,
                "role_means": ab.groupby("prior_role").target_rate.mean().to_dict(),
                "global_mean": float(ab.target_rate.mean()),
                "interval_abs_residual_q90": interval_radius,
                "interval_note": "Marginal validation residual interval; not player-specific confidence or causal effect.",
            },
            model_dir / f"effectiveness_{label}.joblib",
        )
        for fold, frame, fitted, training in [("validation", b, estimator, a), ("test", c, final, ab)]:
            role_pred = _role_mean(training, training.target_rate, frame)
            estimates = {
                "role_mean": role_pred,
                "persistence": frame[f"lag_{label}_rate"]
                .fillna(pd.Series(role_pred, index=frame.index))
                .to_numpy(),
                "ridge": np.maximum(0, np.expm1(fitted.predict(frame[features]))),
            }
            for model_name, estimate in estimates.items():
                rows.append(
                    {
                        "task": "effectiveness_rate",
                        "target": label,
                        "fold": fold,
                        "model": model_name,
                        "selected_on_validation": choice == model_name,
                        **regression_scores(frame.target_rate, estimate),
                    }
                )
            if fold == "test":
                pred_frame = frame[
                    ["player_id", "name", "prior_role", "target_season", "target_opportunity"]
                ].copy()
                pred_frame["target"] = label
                pred_frame["actual_rate"] = frame.target_rate
                pred_frame["prediction"] = estimates[choice]
                pred_frame["selected_model"] = choice
                pred_frame["ridge_prediction"] = estimates["ridge"]
                pred_frame["interval_low"] = np.maximum(0, estimates[choice] - interval_radius)
                pred_frame["interval_high"] = estimates[choice] + interval_radius
                pred_frame["expected_opportunity"] = opportunity_test.reindex(frame.index).values
                pred_frame["availability_probability"] = availability_test.reindex(frame.index).values
                pred_frame["expected_count"] = (
                    pred_frame.prediction * pred_frame.expected_opportunity / RATE_SCALE
                )
                predictions.append(pred_frame)
        # Evaluate total contribution without a future-opportunity filter.
        # This ensures nonreturners remain failures when a model projected value.
        count_test = z[z[target_column].notna()].copy()
        all_role = _role_mean(ab, ab.target_rate, count_test)
        all_estimates = {
            "ridge": np.maximum(0, np.expm1(final.predict(count_test[features]))),
            "role_mean": all_role,
            "persistence": count_test[f"lag_{label}_rate"]
            .fillna(pd.Series(all_role, index=count_test.index))
            .to_numpy(),
        }
        expected_count = (
            all_estimates[choice] * opportunity_test.reindex(count_test.index).to_numpy() / RATE_SCALE
        )
        rows.append(
            {
                "task": "total_contribution_count",
                "target": label,
                "fold": "test",
                "model": "selected_rate_x_expected_opportunity",
                **regression_scores(count_test[target_column], expected_count),
            }
        )
        rows.append(
            {
                "task": "total_contribution_count",
                "target": label,
                "fold": "test",
                "model": "prior_count",
                **regression_scores(count_test[target_column], count_test[f"lag_{label}_count"].fillna(0)),
            }
        )
    evaluation = pd.DataFrame(rows)
    evaluation.to_csv(report_dir / "model_metrics.csv", index=False)
    if predictions:
        combined = pd.concat(predictions, ignore_index=True)
        combined.to_csv(report_dir / "predictions_2025.csv", index=False)
        save_frame(combined, report_dir / "predictions_2025.parquet")
    write_json(report_dir / "model_selection.json", selections)
    write_json(
        report_dir / "split_manifest.json",
        {
            **contract,
            "train_rows": len(train),
            "validation_rows": len(validation),
            "test_rows": len(test),
            "features": features,
            "source_snapshot_warning": "Final corrected snapshots; source publication history is not complete.",
        },
    )
    return {
        "status": "trained",
        "split": contract,
        "metrics": rows,
        "selection": selections,
        "availability_selection": availability_choice,
        "opportunity_selection": opportunity_choice,
        "train_rows": len(train),
        "validation_rows": len(validation),
        "test_rows": len(test),
    }


def physical_role_model(panel: pd.DataFrame, physical: list[str], root: Path, sport: str) -> dict:
    """Temporal, unseen-athlete role compatibility baseline; descriptive dimensions."""
    body = [c for c in physical if c != "age" and c in panel and panel[c].notna().mean() >= 0.1]
    if len(body) < 2:
        return {"status": "insufficient_physical_coverage", "features": body}
    first = (
        panel[panel[body].notna().sum(axis=1) >= 2].sort_values("season").drop_duplicates("player_id").copy()
    )
    unknown_roles = first.role.str.contains("unknown", case=False) | first.role.eq("NON_DEFENSE")
    excluded_unknown_roles = int(unknown_roles.sum())
    first = first[~unknown_roles]
    train = first[first.season.le(2023)]
    val = first[first.season.eq(2024)]
    test = first[first.season.eq(2025)]
    split_description = "First observed with sufficient body data, not necessarily league rookie; temporal first-observation cohorts."
    if len(train) < 100 and len(first) >= 200:
        # A recent-only profile source supports a descriptive athlete holdout,
        # not a historical forecast. Keep that alternative explicit.
        first["physical_partition"] = first.player_id.map(
            lambda x: int(hashlib.sha256(x.encode()).hexdigest()[:8], 16) % 10
        )
        train = first[first.physical_partition.lt(6)]
        val = first[first.physical_partition.isin([6, 7])]
        test = first[first.physical_partition.isin([8, 9])]
        split_description = "Recent-profile descriptive SHA256 athlete holdout; no temporal forecast claim."
    if len(train) < 100 or len(test) < 20 or train.role.nunique() < 2:
        return {
            "status": "insufficient_unseen_player_cohorts",
            "features": body,
            "train": len(train),
            "validation": len(val),
            "test": len(test),
        }
    allowed = train.role.value_counts()
    common = allowed[allowed.ge(10)].index
    train, val, test = [x[x.role.isin(common)] for x in [train, val, test]]
    if len(test) < 20:
        return {"status": "insufficient_test_roles"}
    if len(val) >= 20:
        choices = []
        for c in [0.1, 1, 10]:
            model = make_classifier(body, [], c)
            model.fit(train[body], train.role)
            choices.append((balanced_accuracy_score(val.role, model.predict(val[body])), c))
        _, c = max(choices, key=lambda x: x[0])
    else:
        c = 1
    development = pd.concat([train, val], ignore_index=True)
    final = make_classifier(body, [], c)
    final.fit(development[body], development.role)
    pred = final.predict(test[body])
    dummy = DummyClassifier(strategy="prior").fit(development[body], development.role)
    baseline = dummy.predict(test[body])
    result = {
        "status": "trained",
        "features": body,
        "n_train": len(development),
        "n_test_unseen_players": len(test),
        "class_count": int(development.role.nunique()),
        "unknown_role_athletes_excluded": excluded_unknown_roles,
        "accuracy": float(accuracy_score(test.role, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(test.role, pred)),
        "majority_accuracy": float(accuracy_score(test.role, baseline)),
        "majority_balanced_accuracy": float(balanced_accuracy_score(test.role, baseline)),
        "interpretation": "Role-label compatibility among observed elite athletes. No calibrated cross-sport success probability.",
        "cohort": split_description,
        "physical_timing": "Archived listings or current source bios; see sport data card. Descriptive body-role association.",
    }
    joblib.dump(
        {"model": final, "features": body, "roles": list(final.classes_), "metadata": result},
        root / "models" / sport / "physical_role_compatibility.joblib",
    )
    write_json(root / "reports" / sport / "physical_role_model.json", result)
    return result


def physical_effectiveness_models(
    panel: pd.DataFrame, metrics: dict[str, str], physical: list[str], root: Path, sport: str
) -> dict:
    """Conditional build-to-rate associations with temporal and athlete isolation.

    Source physical listings may be reconstructed or current. These models are
    therefore retrospective physical associations, distinct from the stricter
    lagged-statistic forecast. They cannot estimate success for unselected people.
    """
    body = [c for c in physical if c != "age" and c in panel and panel[c].notna().mean() >= 0.1]
    if len(body) < 2:
        return {"status": "insufficient_physical_coverage"}
    data = panel[panel.opportunity.ge(100) & panel[body].notna().sum(axis=1).ge(2)].copy()
    data["athlete_partition"] = data.player_id.map(
        lambda x: int(hashlib.sha256(x.encode()).hexdigest()[:8], 16) % 10
    )
    data["prior_role"] = data.role
    numeric = body + (["age"] if data.age.notna().sum() > 20 else [])
    features = numeric + ["prior_role"]
    results, evaluated = {}, []
    for label, column in metrics.items():
        work = data[data[column].notna()].copy()
        work["rate"] = RATE_SCALE * work[column] / work.opportunity
        train = work[work.season.le(2023) & work.athlete_partition.lt(6)]
        val = work[work.season.eq(2024) & work.athlete_partition.isin([6, 7])]
        test = work[work.season.eq(2025) & work.athlete_partition.isin([8, 9])]
        if len(train) < 100 or min(len(val), len(test)) < 20:
            results[label] = {"status": "insufficient_independent_temporal_samples"}
            continue
        assert not set(train.player_id) & set(val.player_id)
        assert not set(train.player_id) & set(test.player_id)
        assert not set(val.player_id) & set(test.player_id)
        candidates = []
        for alpha in [1.0, 10.0, 100.0]:
            model = make_regressor(numeric, ["prior_role"], alpha)
            model.fit(train[features], np.log1p(train.rate), model__sample_weight=np.sqrt(train.opportunity))
            estimate = np.maximum(0, np.expm1(model.predict(val[features])))
            candidates.append((mean_absolute_error(val.rate, estimate), alpha, model))
        _, alpha, _ = min(candidates, key=lambda item: item[0])
        development = pd.concat([train, val], ignore_index=True)
        model = make_regressor(numeric, ["prior_role"], alpha)
        model.fit(
            development[features],
            np.log1p(development.rate),
            model__sample_weight=np.sqrt(development.opportunity),
        )
        prediction = np.maximum(0, np.expm1(model.predict(test[features])))
        baseline = _role_mean(development, development.rate, test)
        for name, estimate in [("physical_ridge", prediction), ("role_mean", baseline)]:
            evaluated.append(
                {"target": label, "model": name, "fold": "test", **regression_scores(test.rate, estimate)}
            )
        metadata = {
            "features": features,
            "n_train": len(train),
            "n_validation": len(val),
            "n_test": len(test),
            "ridge_alpha": alpha,
            "rate_scale": RATE_SCALE,
            "model_test": regression_scores(test.rate, prediction),
            "role_mean_test": regression_scores(test.rate, baseline),
            "interpretation": "Physical association within elite role populations; conditional on 100+ opportunity.",
            "timing": "Physical source timing is not verified for historical deployment; not a live preseason forecast.",
            "athlete_split": "SHA256 ID buckets: train 0-5, validation 6-7, test 8-9; no shared athletes.",
        }
        joblib.dump(
            {
                "model": model,
                "features": features,
                "metadata": metadata,
                "reference_physical": development[numeric].describe().to_dict(),
            },
            root / "models" / sport / f"physical_effectiveness_{label}.joblib",
        )
        results[label] = {"status": "trained", **metadata}
    pd.DataFrame(evaluated).to_csv(
        root / "reports" / sport / "physical_effectiveness_metrics.csv", index=False
    )
    write_json(root / "reports" / sport / "physical_effectiveness.json", results)
    return {"status": "completed", "targets": results}


def descriptive_archetypes(
    panel: pd.DataFrame, metrics: dict[str, str], physical: list[str], root: Path, sport: str
) -> dict:
    report_dir, model_dir = root / "reports" / sport, root / "models" / sport
    output = panel[["player_id", "name", "season", "role", "opportunity"]].copy()
    body = [c for c in physical if c != "age" and c in panel and panel[c].notna().mean() >= 0.1]
    results = {}
    if len(body) >= 2:
        unique = panel.sort_values("season").drop_duplicates("player_id")
        physical_models = {}
        profiles = []
        for role, group in unique.groupby("role"):
            eligible = group[group[body].notna().sum(axis=1).ge(2)]
            development = eligible[eligible.season.le(2023)]
            if len(development) < 40:
                continue
            prepare = Pipeline(
                [
                    ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                    ("scale", StandardScaler()),
                ]
            )
            values = prepare.fit_transform(development[body])
            clustering = KMeans(n_clusters=3, n_init=15, random_state=RANDOM_STATE).fit(values)
            physical_models[role] = {"preprocess": prepare, "model": clustering}
            current_mask = panel.role.eq(role) & panel[body].notna().sum(axis=1).ge(2)
            labels = clustering.predict(prepare.transform(panel.loc[current_mask, body]))
            output.loc[current_mask, "physical_archetype"] = [f"{role}_size_{x}" for x in labels]
            centers = prepare.named_steps["scale"].inverse_transform(clustering.cluster_centers_)
            for label, center in enumerate(centers):
                profiles.append({"role": role, "cluster": f"{role}_size_{label}", **dict(zip(body, center))})
        if physical_models:
            joblib.dump(
                {"features": body, "roles": physical_models}, model_dir / "physical_archetypes.joblib"
            )
            pd.DataFrame(profiles).to_csv(report_dir / "physical_archetype_profiles.csv", index=False)
        results["physical"] = {
            "features": body,
            "roles_fitted": sorted(physical_models),
            "note": "Three descriptive size clusters per role where supported; not evidence of three natural biological types.",
        }
    active_metrics = {label: c for label, c in metrics.items() if panel[c].notna().sum() >= 100}
    style = panel[panel.opportunity.ge(100) & panel[list(active_metrics.values())].notna().any(axis=1)].copy()
    train = style[style.season.le(2023)]
    # A single-season enhanced source can describe clusters but cannot create a
    # temporal forecast. Label that case explicitly.
    descriptive_only = False
    if not len(train) and len(style):
        train = style
        descriptive_only = True
    rate_features = []
    if len(train) >= 100 and len(active_metrics) >= 2:
        shrink_exposure = float(train.opportunity.median() * 0.25)
        for label, column in active_metrics.items():
            totals = train.groupby("role")[[column, "opportunity"]].sum(min_count=1)
            prior = totals[column] / totals.opportunity
            global_prior = train[column].sum() / train.opportunity.sum()
            prior_vector = style.role.map(prior).fillna(global_prior)
            feature = f"shrunk_{label}_per100"
            style[feature] = (
                RATE_SCALE
                * (style[column] + prior_vector * shrink_exposure)
                / (style.opportunity + shrink_exposure)
            )
            rate_features.append(feature)
        development = style[style.season.le(2023)] if not descriptive_only else style
        rate_features = [c for c in rate_features if development[c].notna().sum() >= 50]
        if len(rate_features) >= 2:
            role_means = development.groupby("role")[rate_features].mean()
            role_stds = development.groupby("role")[rate_features].std().replace(0, np.nan)
            global_stds = development[rate_features].std().replace(0, 1)
            role_stds = role_stds.fillna(global_stds)

            def role_relative(source):
                means = (
                    role_means.reindex(source.role)
                    .set_axis(source.index)
                    .fillna(development[rate_features].mean())
                )
                stds = role_stds.reindex(source.role).set_axis(source.index).fillna(global_stds)
                return (source[rate_features] - means) / stds

            prep = Pipeline(
                [
                    ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                    ("scale", StandardScaler()),
                ]
            )
            values = prep.fit_transform(role_relative(development))
            candidates = []
            for k in [2, 3, 4, 5]:
                km = KMeans(n_clusters=k, n_init=15, random_state=RANDOM_STATE).fit(values)
                silhouette = silhouette_score(
                    values, km.labels_, sample_size=min(2000, len(values)), random_state=42
                )
                candidates.append((silhouette, k, km))
            silhouette, k, km = max(candidates, key=lambda x: x[0])
            rng = np.random.default_rng(RANDOM_STATE)
            stability = []
            for _ in range(5):
                sampled = rng.choice(len(values), len(values), replace=True)
                alternative = KMeans(n_clusters=k, n_init=10, random_state=42).fit(values[sampled])
                stability.append(adjusted_rand_score(km.labels_, alternative.predict(values)))
            style["play_style_archetype"] = km.predict(prep.transform(role_relative(style))).astype(str)
            style["play_style_archetype"] = "style_" + style.play_style_archetype
            output = output.merge(
                style[["player_id", "season", "play_style_archetype", *rate_features]],
                on=["player_id", "season"],
                how="left",
                validate="one_to_one",
            )
            profiles = style.groupby("play_style_archetype")[rate_features].mean()
            profiles["player_seasons"] = style.groupby("play_style_archetype").size()
            profiles.to_csv(report_dir / "play_style_profiles.csv")
            joblib.dump(
                {
                    "model": km,
                    "preprocess": prep,
                    "features": rate_features,
                    "role_means": role_means,
                    "role_stds": role_stds,
                    "shrink_exposure": shrink_exposure,
                    "descriptive_only": descriptive_only,
                },
                model_dir / "play_style_archetypes.joblib",
            )
            results["play_style"] = {
                "clusters": k,
                "training_silhouette": float(silhouette),
                "bootstrap_adjusted_rand_mean": float(np.mean(stability)),
                "features": rate_features,
                "minimum_opportunity": 100,
                "descriptive_only": descriptive_only,
                "normalization": "Role-relative means and standard deviations learned from development seasons.",
                "note": "Descriptive event-rate groups; success is not independently proven by clustering on those events.",
            }
    output.to_csv(report_dir / "player_archetypes.csv", index=False)
    save_frame(output, report_dir / "player_archetypes.parquet")
    write_json(report_dir / "archetypes.json", results)
    return results


def _make_eda(panel: pd.DataFrame, metrics: dict[str, str], root: Path, sport: str, unit: str) -> dict:
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    report = root / "reports" / sport
    figures = report / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    count_columns = list(dict.fromkeys(metrics.values()))
    coverage = panel.groupby("season").agg(
        players=("player_id", "nunique"),
        active_players=("opportunity", lambda x: int(x.gt(0).sum())),
        opportunity=("opportunity", "sum"),
        missing_opportunity=("opportunity", lambda x: int(x.isna().sum())),
        height_coverage=("height_cm", lambda x: float(x.notna().mean())),
        weight_coverage=("weight_kg", lambda x: float(x.notna().mean())),
    )
    for label, column in metrics.items():
        coverage[f"{label}_observed_players"] = panel.groupby("season")[column].count()
        coverage[f"{label}_total"] = panel.groupby("season")[column].sum(min_count=1)
    coverage.to_csv(report / "season_coverage.csv")
    role = panel.groupby(["season", "role"]).agg(
        players=("player_id", "nunique"),
        opportunity=("opportunity", "sum"),
        height_cm=("height_cm", "median"),
        weight_kg=("weight_kg", "median"),
    )
    role.to_csv(report / "role_summary.csv")
    columns = ["height_cm", "weight_kg", "age", "opportunity", *count_columns]
    missingness = panel[columns].isna().mean().sort_values(ascending=False)
    missingness.rename("missing_fraction").to_csv(report / "missingness.csv")
    panel[columns].describe(percentiles=[0.01, 0.1, 0.5, 0.9, 0.99]).to_csv(report / "numeric_summary.csv")
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    coverage[["players", "active_players"]].plot.bar(ax=axes[0], color=["#9ab9d1", "#175d80"])
    axes[0].set(title=f"{sport.upper()} player coverage", ylabel="Players", xlabel="Season start year")
    missingness.plot.barh(ax=axes[1], color="#b36b4a")
    axes[1].set(title="Field missingness", xlabel="Missing fraction", xlim=(0, 1))
    for index, fraction in enumerate(missingness):
        axes[1].text(min(float(fraction) + 0.01, 0.93), index, f"{fraction:.1%}", va="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(figures / "coverage.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    if panel[["height_cm", "weight_kg"]].dropna().shape[0]:
        for name, group in panel.groupby("role"):
            axes[0].scatter(group.height_cm, group.weight_kg, s=9, alpha=0.35, label=name)
        axes[0].legend(fontsize=7, ncols=2)
    axes[0].set(title="Listed size by role", xlabel="Height (cm)", ylabel="Mass (kg)")
    positive = panel.loc[panel.opportunity.gt(0), "opportunity"]
    axes[1].hist(positive, bins=40, color="#175d80")
    axes[1].set(title="Opportunity among appearances", xlabel=unit, ylabel="Player-seasons")
    fig.tight_layout()
    fig.savefig(figures / "physical_opportunity.png", dpi=150)
    plt.close(fig)
    correlation_rows, event_rows = [], []
    for label, column in metrics.items():
        eligible = panel[panel.opportunity.ge(100) & panel[column].notna()].copy()
        event_rows.append(
            {
                "metric": label,
                "observed_player_seasons": int(panel[column].notna().sum()),
                "missing_player_seasons": int(panel[column].isna().sum()),
                "zero_event_player_seasons": int(panel[column].eq(0).sum()),
                "total_recorded_events": float(panel[column].sum(min_count=1))
                if panel[column].notna().any()
                else None,
                "reliable_exposure_sample": len(eligible),
            }
        )
        if len(eligible) < 20:
            continue
        eligible["event_rate"] = RATE_SCALE * eligible[column] / eligible.opportunity
        eligible["rate_residual"] = eligible.event_rate - eligible.groupby(
            ["season", "role"]
        ).event_rate.transform("mean")
        for attribute in ["height_cm", "weight_kg", "age"]:
            valid = eligible[eligible[attribute].notna()].copy()
            if len(valid) < 20:
                continue
            centered = valid[attribute] - valid.groupby(["season", "role"])[attribute].transform("mean")
            correlation_rows.append(
                {
                    "metric": label,
                    "physical_attribute": attribute,
                    "player_seasons": len(valid),
                    "within_role_season_spearman": safe_spearman(
                        centered.to_numpy(), valid.rate_residual.to_numpy()
                    ),
                    "note": "Descriptive repeated player-seasons; no causal or independent-sample inference.",
                }
            )
    pd.DataFrame(event_rows).to_csv(report / "event_distribution.csv", index=False)
    correlation_frame = pd.DataFrame(correlation_rows)
    correlation_frame.to_csv(report / "physical_correlations.csv", index=False)
    if len(correlation_frame):
        grid = correlation_frame.pivot(
            index="metric", columns="physical_attribute", values="within_role_season_spearman"
        )
        fig, ax = plt.subplots(figsize=(7, max(3.5, 0.5 * len(grid))))
        plot = ax.imshow(grid.to_numpy(float), cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
        ax.set_xticks(range(len(grid.columns)), grid.columns)
        ax.set_yticks(range(len(grid.index)), grid.index)
        for i in range(len(grid.index)):
            for j in range(len(grid.columns)):
                value = grid.iloc[i, j]
                if pd.notna(value):
                    ax.text(j, i, f"{value:.2f}", ha="center", va="center")
        ax.set_title(
            "Body and event-rate associations within role and season\n100+ opportunity; descriptive Spearman correlation"
        )
        fig.colorbar(plot, ax=ax, label="Correlation")
        fig.tight_layout()
        fig.savefig(figures / "physical_association.png", dpi=150)
        plt.close(fig)
    rate_rows = []
    for label, column in metrics.items():
        valid = panel[panel.opportunity.gt(0) & panel[column].notna()]
        for (season, role_name), group in valid.groupby(["season", "role"]):
            rate_rows.append(
                {
                    "season": int(season),
                    "role": role_name,
                    "metric": label,
                    "events": float(group[column].sum()),
                    "opportunity": float(group.opportunity.sum()),
                    "rate_per100": float(RATE_SCALE * group[column].sum() / group.opportunity.sum()),
                    "players": group.player_id.nunique(),
                }
            )
    pd.DataFrame(rate_rows).to_csv(report / "role_event_rates.csv", index=False)
    summary = {
        "rows": len(panel),
        "unique_players": panel.player_id.nunique(),
        "seasons": sorted(panel.season.unique().tolist()),
        "zero_opportunity_rows": int(panel.opportunity.eq(0).sum()),
        "missing_opportunity_rows": int(panel.opportunity.isna().sum()),
        "height_coverage": float(panel.height_cm.notna().mean()),
        "weight_coverage": float(panel.weight_kg.notna().mean()),
        "metric_coverage": {label: float(panel[column].notna().mean()) for label, column in metrics.items()},
        "opportunity_unit": unit,
        "season_coverage": coverage.reset_index().replace({np.nan: None}).to_dict("records"),
    }
    write_json(report / "eda.json", summary)
    return summary


def analyze_sport(
    panel: pd.DataFrame,
    sport: str,
    root: Path,
    *,
    metrics: dict[str, str],
    physical_features: list[str] | None = None,
    limitations: list[str] | None = None,
    opportunity_unit: str = "minutes",
) -> dict:
    root = Path(root)
    report = root / "reports" / sport
    report.mkdir(parents=True, exist_ok=True)
    (root / "models" / sport).mkdir(parents=True, exist_ok=True)
    physical = physical_features or ["height_cm", "weight_kg", "age"]
    frame = validate_panel(panel, metrics)
    eda = _make_eda(frame, metrics, root, sport, opportunity_unit)
    archetypes = descriptive_archetypes(frame, metrics, physical, root, sport)
    forecast = forecast_models(frame, metrics, root, sport)
    role_model = physical_role_model(frame, physical, root, sport)
    physical_effectiveness = physical_effectiveness_models(frame, metrics, physical, root, sport)
    result = {
        "sport": sport,
        "eda": eda,
        "archetypes": archetypes,
        "forecast": forecast,
        "physical_role_model": role_model,
        "physical_effectiveness_models": physical_effectiveness,
        "limitations": limitations or [],
        "model_scope": "Research baseline; temporal validation, returning-player forecast, descriptive role compatibility.",
    }
    active_files = []
    if forecast.get("status") == "trained":
        active_files.extend(["availability.joblib", "opportunity.joblib"])
        active_files.extend(
            f"effectiveness_{label}.joblib"
            for label, selection in forecast["selection"].items()
            if "selected_on_2024" in selection
        )
    if role_model.get("status") == "trained":
        active_files.append("physical_role_compatibility.joblib")
    physical_effect_files = [
        f"physical_effectiveness_{label}.joblib"
        for label, model in physical_effectiveness.get("targets", {}).items()
        if model.get("status") == "trained"
    ]
    active_files.extend(physical_effect_files)
    if archetypes.get("physical", {}).get("roles_fitted"):
        active_files.append("physical_archetypes.joblib")
    if archetypes.get("play_style"):
        active_files.append("play_style_archetypes.joblib")
    registry = {
        "sport": sport,
        "physical_effectiveness_files": physical_effect_files,
        "files": [
            {"filename": filename, "sha256": sha256(root / "models" / sport / filename)}
            for filename in active_files
        ],
        "note": "Only these artifacts belong to this run; older files in a local model directory are not active.",
    }
    write_json(root / "models" / sport / "model_registry.json", registry)
    write_json(report / "model_registry.json", registry)
    write_json(report / "summary.json", result)
    lines = [
        f"# {sport.upper()} first data and model results",
        "",
        f"{eda['rows']:,} player-season rows; {eda['unique_players']:,} distinct athletes.",
        f"Season start years: {', '.join(map(str, eda['seasons']))}. Opportunity unit: {opportunity_unit}.",
        "",
        "## Coverage",
        "",
        coverage_markdown(eda),
        "",
        "![Coverage](figures/coverage.png)",
        "",
        "![Physical measurements and opportunity](figures/physical_opportunity.png)",
        "",
        "![Body and event-rate associations](figures/physical_association.png)",
        "",
        "The correlation chart removes role/season means and requires 100 opportunity units. It describes association among already-selected athletes; repeated seasons are not independent athletes.",
        "",
        "## Model evaluation",
        "",
        "The 2024 season selects hyperparameters and the baseline/model choice. The 2025 season evaluates that frozen choice.",
        "Returning-player candidates come from the prior season; nonreturners stay in availability and total-count evaluation.",
        "Effectiveness rates are conditional on positive future opportunity. Total-contribution errors include nonreturners.",
        "Forecast features use previous-season statistics, opportunity, role and age. Current physical listings are excluded.",
        "Source snapshots contain final corrections; these are retrospective temporal tests, not point-in-time audited live forecasts.",
        "",
        model_markdown(forecast),
        "",
        "## Physical compatibility",
        "",
        f"Status: {role_model.get('status')}.",
    ]
    if role_model.get("status") == "trained":
        lines.extend(
            [
                f"Unseen-player test accuracy: {role_model['accuracy']:.3f}; majority baseline: {role_model['majority_accuracy']:.3f}.",
                f"Balanced accuracy: {role_model['balanced_accuracy']:.3f}. Body inputs: {', '.join(role_model['features'])}.",
                "These probabilities describe role labels among elite athletes, not success probabilities for outside-sport candidates.",
            ]
        )
    lines.extend(
        [
            "",
            "## Limits and interpretation",
            "",
            *[f"- {s}" for s in (limitations or [])],
            "",
            "See qa.json, season_coverage.csv, model_metrics.csv, split_manifest.json, and model_selection.json for evidence.",
            "Raw data and fitted player predictions are local artifacts and retain their source terms.",
            "",
        ]
    )
    (report / "report.md").write_text("\n".join(lines))
    model_table = pd.DataFrame(forecast.get("metrics", []))
    table_html = (
        model_table.to_html(index=False, float_format=lambda x: f"{x:.3f}")
        if len(model_table)
        else "<p>Insufficient temporal target coverage.</p>"
    )
    document = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<title>{sport.upper()} — Possession Lab</title>
<style>body{{font:16px/1.55 system-ui;margin:40px auto;max-width:1100px;padding:0 24px;color:#17303b}}
h1,h2{{line-height:1.15}}img{{width:100%;height:auto}}table{{border-collapse:collapse;font-size:12px}}
td,th{{padding:7px;border-bottom:1px solid #ddd;text-align:right}}.table{{overflow:auto}}
.note{{background:#edf4f7;padding:16px}}a{{color:#155e83}}</style>
<h1>{sport.upper()} research baseline</h1>
<p>{eda["rows"]:,} player-season rows · {eda["unique_players"]:,} athletes · {html.escape(str(eda["seasons"]))}</p>
<p class="note">Role-specific event evidence, data coverage and uncertainty govern interpretation.
Physical role similarity does not establish cross-sport success.</p>
<h2>Data coverage</h2><img src="figures/coverage.png" alt="Coverage and missingness">
<h2>Body profiles and opportunity</h2><img src="figures/physical_opportunity.png" alt="Body profiles">
<h2>Within-role physical associations</h2><img src="figures/physical_association.png" alt="Descriptive physical correlations">
<h2>Temporal model evaluation</h2><p>2024 selects the model; 2025 evaluates it.
Forecasts exclude current physical listings. Baselines are retained when they perform better on validation.</p>
<div class="table">{table_html}</div><h2>Limitations</h2><ul>
{"".join("<li>" + html.escape(x) + "</li>" for x in (limitations or []))}</ul>
<p><a href="report.md">Detailed report</a> · <a href="summary.json">Machine-readable results</a></p></html>"""
    (report / "report.html").write_text(document)
    print(f"{sport.upper()} analysis complete: {report / 'report.html'}", flush=True)
    return result


def coverage_markdown(eda: dict) -> str:
    lines = ["| Season | Players | Active | Height coverage | Weight coverage |", "|---|---:|---:|---:|---:|"]
    for row in eda["season_coverage"]:
        lines.append(
            f"| {row['season']} | {row['players']:,} | {row['active_players']:,} | "
            f"{row['height_coverage']:.1%} | {row['weight_coverage']:.1%} |"
        )
    return "\n".join(lines)


def model_markdown(forecast: dict) -> str:
    if forecast.get("status") != "trained":
        return f"Status: {forecast.get('status')}. A future-season effectiveness model requires comparable labels in development, validation, and test seasons."
    lines = [
        "| Target rate | Selected on 2024 | 2025 MAE | Persistence MAE | Role-mean MAE |",
        "|---|---|---:|---:|---:|",
    ]
    records = forecast.get("metrics", [])
    for target, selection in forecast.get("selection", {}).items():
        if "selected_on_2024" not in selection:
            continue
        matches = {
            x["model"]: x
            for x in records
            if x["task"] == "effectiveness_rate" and x["target"] == target and x["fold"] == "test"
        }
        selected = selection["selected_on_2024"]
        if selected in matches:
            lines.append(
                f"| {target} | {selected} | {matches[selected]['mae']:.3f} | "
                f"{matches['persistence']['mae']:.3f} | {matches['role_mean']['mae']:.3f} |"
            )
    return "\n".join(lines)
