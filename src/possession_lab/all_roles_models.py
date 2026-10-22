"""Leakage-aware native forecasts and exploratory cross-sport role bridges."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import RidgeCV

from possession_lab.all_roles_context import CONTEXT_FEATURES, CONTEXT_VERSION
from possession_lab.all_roles_pooling import (
    POOLING_TAUS,
    POOLING_VERSION,
    ROLE_FAMILIES,
    BlendedPercentileModel,
    add_role_dummies,
    effective_sample_size,
    family_for_role,
    pooling_gate,
    role_blend_weight,
    role_dummy_name,
)
from possession_lab.all_roles_registry import (
    BRIDGE_VERSION,
    FROZEN_TEST_SEASON,
    ROLE_TAXONOMY_VERSION,
    SCHEMA_VERSION,
    TARGET_VERSION,
    RoleSpec,
    role_specs,
)

PHYSICAL_FEATURES = ("height_cm", "weight_kg", "bmi", "age")
INTERVAL_COVERAGE = 0.90
ATHLETE_DISJOINT_FOLDS = 5
NBA_MODEL_FACE_CHECKS = {
    "guard": {"3975": "stephen_curry"},
    "forward": {"1966": "lebron_james"},
}


def _with_bmi(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in ("height_cm", "weight_kg", "age"):
        if column not in result:
            result[column] = np.nan
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["bmi"] = result["weight_kg"] / (result["height_cm"] / 100.0) ** 2
    result.loc[~np.isfinite(result["bmi"]) | result["bmi"].le(0), "bmi"] = np.nan
    return result


def _finite_target(frame: pd.DataFrame, target: str) -> pd.Series:
    return pd.to_numeric(frame[target], errors="coerce").replace([np.inf, -np.inf], np.nan).notna()


def _complete_numeric_inputs(frame: pd.DataFrame, features: tuple[str, ...]) -> pd.Series:
    """Return rows that have every input required by the deployed scorer.

    Age and other model inputs may still be median-imputed.  Callers pass only
    the fields that the scoring contract refuses to impute (listed build and,
    where applicable, the fixed semantic performance dimensions).
    """
    if not features:
        return pd.Series(True, index=frame.index)
    values = frame.reindex(columns=features).apply(pd.to_numeric, errors="coerce")
    return np.isfinite(values).all(axis=1)


def _coverage_summary(
    candidates: pd.DataFrame,
    eligible: pd.DataFrame,
    usable: pd.DataFrame,
    *,
    required_inputs: tuple[str, ...],
    extra: dict | None = None,
) -> dict:
    """Describe label eligibility separately from deployable feature coverage."""
    eligible_count = int(len(eligible))
    missing = {}
    for feature in required_inputs:
        if feature not in eligible:
            missing[feature] = eligible_count
            continue
        values = pd.to_numeric(eligible[feature], errors="coerce")
        missing[feature] = int((~np.isfinite(values)).sum())
    summary = {
        "candidate_rows": int(len(candidates)),
        "eligible_label_rows": eligible_count,
        "usable_rows": int(len(usable)),
        "usable_fraction_of_eligible_labels": (
            float(len(usable) / eligible_count) if eligible_count else None
        ),
        "required_observed_inputs": list(required_inputs),
        "missing_required_input_rows": missing,
        "usable_rows_by_season": {
            str(int(season)): int(count)
            for season, count in usable.groupby("season", dropna=False).size().items()
            if pd.notna(season)
        },
    }
    if extra:
        summary.update(extra)
    return summary


@dataclass
class LinearPercentileModel:
    """A small, deterministic ridge model with explicit missing-value handling."""

    features: tuple[str, ...]
    medians: np.ndarray | None = None
    means: np.ndarray | None = None
    scales: np.ndarray | None = None
    coefficients: np.ndarray | None = None
    intercept: float | None = None
    alpha: float | None = None
    training_rows: int = 0
    training_weight_sum: float = 0.0

    def _matrix(self, frame: pd.DataFrame) -> np.ndarray:
        values = frame.reindex(columns=self.features).apply(pd.to_numeric, errors="coerce")
        return values.to_numpy(float)

    def fit(
        self,
        frame: pd.DataFrame,
        target: str,
        sample_weight: pd.Series | np.ndarray | None = None,
    ) -> "LinearPercentileModel":
        matrix = self._matrix(frame)
        y = pd.to_numeric(frame[target], errors="coerce").to_numpy(float)
        if sample_weight is None:
            weights = np.ones(len(frame), dtype=float)
        else:
            weights = pd.to_numeric(
                pd.Series(np.asarray(sample_weight), index=frame.index), errors="coerce"
            ).to_numpy(float)
        valid_y = np.isfinite(y) & np.isfinite(weights) & (weights > 0)
        matrix = matrix[valid_y]
        y = y[valid_y]
        weights = weights[valid_y]
        if len(y) < max(12, len(self.features) * 3):
            raise ValueError(
                f"Model with {len(self.features)} features needs at least "
                f"{max(12, len(self.features) * 3)} rows; found {len(y)}"
            )
        finite_counts = np.isfinite(matrix).sum(axis=0)
        if np.any(finite_counts == 0):
            missing = [self.features[index] for index in np.flatnonzero(finite_counts == 0)]
            raise ValueError(f"Training features have no observations: {missing}")
        self.medians = np.asarray(
            [_weighted_median(matrix[:, index], weights) for index in range(matrix.shape[1])]
        )
        imputed = np.where(np.isfinite(matrix), matrix, self.medians)
        self.means = np.average(imputed, axis=0, weights=weights)
        variance = np.average((imputed - self.means) ** 2, axis=0, weights=weights)
        self.scales = np.sqrt(variance)
        self.scales[self.scales < 1e-9] = 1.0
        standardized = (imputed - self.means) / self.scales
        estimator = RidgeCV(alphas=np.asarray([0.1, 1.0, 10.0, 100.0, 1000.0]))
        estimator.fit(standardized, y, sample_weight=weights)
        self.coefficients = np.asarray(estimator.coef_, dtype=float)
        self.intercept = float(estimator.intercept_)
        self.alpha = float(estimator.alpha_)
        self.training_rows = int(len(y))
        self.training_weight_sum = float(weights.sum())
        return self

    def _standardized(self, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        if any(value is None for value in [self.medians, self.means, self.scales]):
            raise ValueError("Model is not fit")
        matrix = self._matrix(frame)
        missing = ~np.isfinite(matrix)
        imputed = np.where(np.isfinite(matrix), matrix, self.medians)
        return (imputed - self.means) / self.scales, missing

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        if self.coefficients is None or self.intercept is None:
            raise ValueError("Model is not fit")
        standardized, _ = self._standardized(frame)
        prediction = self.intercept + standardized @ self.coefficients
        return np.clip(prediction, 0.0, 100.0)

    def explain(self, frame: pd.DataFrame) -> list[list[dict]]:
        if self.coefficients is None:
            raise ValueError("Model is not fit")
        standardized, missing = self._standardized(frame)
        contributions = standardized * self.coefficients
        output: list[list[dict]] = []
        for row, row_missing in zip(contributions, missing):
            entries = [
                {
                    "feature": feature,
                    "contribution": float(value),
                    "imputed": bool(was_missing),
                }
                for feature, value, was_missing in zip(self.features, row, row_missing)
            ]
            output.append(sorted(entries, key=lambda item: abs(item["contribution"]), reverse=True))
        return output

    def metadata(self) -> dict:
        coefficients = [] if self.coefficients is None else self.coefficients
        return {
            "features": list(self.features),
            "alpha": self.alpha,
            "training_rows": self.training_rows,
            "training_weight_sum": self.training_weight_sum,
            "coefficients": {
                feature: float(value)
                for feature, value in zip(self.features, coefficients)
            },
            "missing_values": "median imputation learned from the training rows; never filled with a neutral percentile",
        }


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not valid.any():
        return float("nan")
    ordered = np.argsort(values[valid], kind="stable")
    observed = values[valid][ordered]
    observed_weights = weights[valid][ordered]
    cutoff = observed_weights.sum() / 2.0
    return float(observed[np.searchsorted(np.cumsum(observed_weights), cutoff, side="left")])


def _training_weights(frame: pd.DataFrame, column: str | None) -> np.ndarray | None:
    if column is None:
        return None
    if column not in frame:
        return np.ones(len(frame), dtype=float)
    weights = pd.to_numeric(frame[column], errors="coerce").to_numpy(float)
    return np.where(np.isfinite(weights) & (weights > 0), weights, np.nan)


def _regression_metrics(actual, predicted) -> dict:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    valid = np.isfinite(actual) & np.isfinite(predicted)
    if not valid.any():
        return {"n": 0, "mae": None, "rmse": None, "spearman": None}
    actual = actual[valid]
    predicted = predicted[valid]
    correlation = None
    if len(actual) >= 3 and np.ptp(actual) > 0 and np.ptp(predicted) > 0:
        value = spearmanr(actual, predicted).statistic
        correlation = float(value) if np.isfinite(value) else None
    return {
        "n": int(len(actual)),
        "mae": float(np.mean(np.abs(actual - predicted))),
        "rmse": float(np.sqrt(np.mean((actual - predicted) ** 2))),
        "spearman": correlation,
    }


def _percentile_diagnostics(actual, predicted) -> dict:
    """Check whether predicted percentiles behave like observed percentiles.

    The bin gap is descriptive calibration error on the 0--100 target scale,
    not probability calibration.  The top-decile block reports both the fixed
    90-point threshold and a cohort-relative precision-at-10% check so a model
    that regresses all predictions toward 50 cannot appear successful merely
    because it never emits a value above 90.
    """
    frame = pd.DataFrame(
        {
            "actual": pd.to_numeric(pd.Series(np.asarray(actual)), errors="coerce"),
            "predicted": pd.to_numeric(
                pd.Series(np.asarray(predicted)), errors="coerce"
            ),
        }
    ).replace([np.inf, -np.inf], np.nan).dropna()
    if frame.empty:
        return {
            "n": 0,
            "mean_bias": None,
            "weighted_mean_absolute_bin_gap": None,
            "bins": [],
            "top_decile": {
                "actual_at_or_above_90": 0,
                "predicted_at_or_above_90": 0,
                "threshold_precision": None,
                "threshold_recall": None,
                "selection_n": 0,
                "overlap_n": 0,
                "precision_at_10_percent": None,
                "observed_mean_for_predicted_top_decile": None,
                "cohort_observed_mean": None,
                "lift_over_cohort_mean": None,
            },
        }

    # Fixed 10-point bins make model heads directly comparable and preserve
    # empty bins rather than hiding output-range compression.
    edges = np.linspace(0.0, 100.0, 11)
    bucket = np.minimum(
        np.searchsorted(edges, frame["predicted"].to_numpy(float), side="right") - 1,
        9,
    )
    bucket = np.maximum(bucket, 0)
    bins = []
    weighted_gap = 0.0
    for index in range(10):
        values = frame.loc[bucket == index]
        if values.empty:
            continue
        predicted_mean = float(values["predicted"].mean())
        observed_mean = float(values["actual"].mean())
        gap = observed_mean - predicted_mean
        weighted_gap += len(values) * abs(gap)
        bins.append(
            {
                "lower": float(edges[index]),
                "upper": float(edges[index + 1]),
                "n": int(len(values)),
                "predicted_mean": predicted_mean,
                "observed_mean": observed_mean,
                "observed_minus_predicted": float(gap),
            }
        )

    actual_top = frame["actual"].ge(90.0)
    predicted_top = frame["predicted"].ge(90.0)
    true_positive = int((actual_top & predicted_top).sum())
    threshold_precision = (
        float(true_positive / predicted_top.sum()) if predicted_top.any() else None
    )
    threshold_recall = float(true_positive / actual_top.sum()) if actual_top.any() else None

    selection_n = max(1, int(np.ceil(len(frame) * 0.10)))
    predicted_selection = set(
        frame.sort_values("predicted", ascending=False, kind="stable")
        .head(selection_n)
        .index
    )
    observed_selection = set(
        frame.sort_values("actual", ascending=False, kind="stable")
        .head(selection_n)
        .index
    )
    overlap = len(predicted_selection & observed_selection)
    predicted_top_rows = frame.loc[list(predicted_selection)]
    cohort_mean = float(frame["actual"].mean())
    selected_mean = float(predicted_top_rows["actual"].mean())
    return {
        "n": int(len(frame)),
        "mean_bias": float((frame["predicted"] - frame["actual"]).mean()),
        "weighted_mean_absolute_bin_gap": float(weighted_gap / len(frame)),
        "bins": bins,
        "top_decile": {
            "actual_at_or_above_90": int(actual_top.sum()),
            "predicted_at_or_above_90": int(predicted_top.sum()),
            "threshold_precision": threshold_precision,
            "threshold_recall": threshold_recall,
            "selection_n": int(selection_n),
            "overlap_n": int(overlap),
            "precision_at_10_percent": float(overlap / selection_n),
            "observed_mean_for_predicted_top_decile": selected_mean,
            "cohort_observed_mean": cohort_mean,
            "lift_over_cohort_mean": float(selected_mean - cohort_mean),
        },
    }


def _conformal_interval(
    residual_rows: list[dict],
    *,
    coverage: float = INTERVAL_COVERAGE,
) -> dict:
    """Calibrate an athlete-level residual radius from rolling-origin errors.

    One latest residual per athlete is retained so a long-tenured athlete does
    not dominate calibration.  The finite-sample conformal order statistic is
    used when the sample is large enough.  This is intentionally independent
    of the frozen 2025 labels; frozen coverage is added later as a diagnostic.
    """
    if not residual_rows:
        return {
            "status": "insufficient_rolling_origin_calibration",
            "method": "rolling_origin_latest_per_athlete_absolute_residual",
            "nominal_coverage": float(coverage),
            "half_width": None,
            "calibration_athletes": 0,
            "calibration_seasons": [],
        }
    frame = pd.DataFrame(residual_rows).replace([np.inf, -np.inf], np.nan)
    frame = frame.dropna(subset=["absolute_residual", "athlete_id", "season"])
    if frame.empty:
        return {
            "status": "insufficient_rolling_origin_calibration",
            "method": "rolling_origin_latest_per_athlete_absolute_residual",
            "nominal_coverage": float(coverage),
            "half_width": None,
            "calibration_athletes": 0,
            "calibration_seasons": [],
        }
    latest = (
        frame.sort_values(["athlete_id", "season"], kind="stable")
        .groupby("athlete_id", sort=False)
        .tail(1)
    )
    residuals = np.sort(latest["absolute_residual"].to_numpy(float))
    rank = int(np.ceil((len(residuals) + 1) * coverage))
    radius = float(residuals[rank - 1]) if rank <= len(residuals) else None
    return {
        "status": (
            "calibrated_from_rolling_origin"
            if radius is not None
            else "insufficient_rolling_origin_calibration"
        ),
        "method": "rolling_origin_latest_per_athlete_absolute_residual",
        "nominal_coverage": float(coverage),
        "half_width": radius,
        "calibration_athletes": int(len(residuals)),
        "calibration_seasons": sorted(int(value) for value in latest["season"].unique()),
        "finite_sample_rank": int(rank),
        "assumption_warning": (
            "A rolling-origin empirical range, not a causal or cross-sport success interval; "
            "nominal coverage can fail under drift or source-to-target distribution shift."
        ),
    }


def _athlete_disjoint_validation(
    source: pd.DataFrame,
    evaluation_source: pd.DataFrame,
    *,
    features: tuple[str, ...],
    target: str,
    time_column: str,
    frozen_season: int,
    sample_weight_column: str | None,
) -> dict:
    """Measure identity generalization with deterministic group folds.

    This diagnostic uses only pre-freeze rows and keeps every season for one
    athlete in a single fold.  It is deliberately separate from the primary
    chronological evidence gate because it answers a different question and
    is not a future-season backtest.
    """
    empty = {
        "status": "insufficient_athlete_disjoint_evidence",
        "design": "pre_freeze_group_folds_by_player_id",
        "n": 0,
        "athletes": 0,
        "folds_requested": ATHLETE_DISJOINT_FOLDS,
        "folds_completed": 0,
        "mae": None,
        "rmse": None,
        "spearman": None,
        "athlete_balanced_mae": None,
        "train_test_identity_overlap": 0,
        "interpretation": (
            "Identity-generalization diagnostic only; the chronological frozen test remains "
            "the evidence gate."
        ),
    }
    if "player_id" not in source or "player_id" not in evaluation_source:
        return empty
    seasons = pd.to_numeric(source[time_column], errors="coerce")
    evaluation_seasons = pd.to_numeric(evaluation_source[time_column], errors="coerce")
    pool = source.loc[seasons < frozen_season].copy()
    evaluation_pool = evaluation_source.loc[evaluation_seasons < frozen_season].copy()
    athletes = sorted(evaluation_pool["player_id"].dropna().astype(str).unique())
    if len(athletes) < 3:
        return {**empty, "athletes": int(len(athletes))}
    fold_count = min(ATHLETE_DISJOINT_FOLDS, len(athletes))
    assignments = {
        athlete: int.from_bytes(
            hashlib.sha256(f"all-roles-athlete-disjoint-v1:{athlete}".encode()).digest()[:8],
            "big",
        )
        % fold_count
        for athlete in athletes
    }
    predictions: list[float] = []
    actuals: list[float] = []
    predicted_athletes: list[str] = []
    completed = 0
    training_rows = []
    minimum = max(12, len(features) * 3)
    for fold in range(fold_count):
        held_out = {athlete for athlete, assignment in assignments.items() if assignment == fold}
        if not held_out:
            continue
        fold_train = pool.loc[~pool["player_id"].astype(str).isin(held_out)]
        fold_test = evaluation_pool.loc[
            evaluation_pool["player_id"].astype(str).isin(held_out)
        ]
        if len(fold_train) < minimum or fold_test.empty:
            continue
        try:
            model = LinearPercentileModel(features).fit(
                fold_train,
                target,
                sample_weight=_training_weights(fold_train, sample_weight_column),
            )
        except ValueError:
            continue
        fold_prediction = model.predict(fold_test)
        predictions.extend(fold_prediction.tolist())
        actuals.extend(pd.to_numeric(fold_test[target], errors="coerce").tolist())
        predicted_athletes.extend(fold_test["player_id"].astype(str).tolist())
        training_rows.append(int(len(fold_train)))
        completed += 1
    if not predictions:
        return {**empty, "athletes": int(len(athletes)), "folds_requested": int(fold_count)}
    metrics = _regression_metrics(actuals, predictions)
    errors = pd.DataFrame(
        {
            "athlete_id": predicted_athletes,
            "absolute_error": np.abs(np.asarray(actuals) - np.asarray(predictions)),
        }
    )
    return {
        **empty,
        **metrics,
        "status": "available",
        "athletes": int(errors["athlete_id"].nunique()),
        "folds_requested": int(fold_count),
        "folds_completed": int(completed),
        "athlete_balanced_mae": float(
            errors.groupby("athlete_id", sort=False)["absolute_error"].mean().mean()
        ),
        "training_rows_min": min(training_rows),
        "training_rows_max": max(training_rows),
    }


def _cluster_bootstrap_advantage(
    actual,
    predicted,
    baseline,
    clusters,
    *,
    iterations: int = 500,
    seed: int = 20261021,
) -> dict:
    """Cluster bootstrap the MAE improvement over a comparator."""
    frame = pd.DataFrame(
        {
            "actual": pd.to_numeric(pd.Series(np.asarray(actual)), errors="coerce"),
            "predicted": pd.to_numeric(pd.Series(np.asarray(predicted)), errors="coerce"),
            "baseline": pd.to_numeric(pd.Series(np.asarray(baseline)), errors="coerce"),
            "cluster": pd.Series(np.asarray(clusters)).astype("string"),
        }
    ).dropna()
    if frame.empty:
        return {"estimate": None, "ci90": [None, None], "clusters": 0, "iterations": 0}
    frame["model_error"] = (frame["actual"] - frame["predicted"]).abs()
    frame["baseline_error"] = (frame["actual"] - frame["baseline"]).abs()
    grouped = frame.groupby("cluster", sort=False)[["model_error", "baseline_error"]].mean()
    estimate = float(grouped["baseline_error"].mean() - grouped["model_error"].mean())
    if len(grouped) < 5:
        return {
            "estimate": estimate,
            "ci90": [None, None],
            "clusters": int(len(grouped)),
            "iterations": 0,
        }
    rng = np.random.default_rng(seed)
    values = grouped.to_numpy(float)
    samples = np.empty(iterations, dtype=float)
    for index in range(iterations):
        draw = values[rng.integers(0, len(values), size=len(values))]
        samples[index] = float(np.mean(draw[:, 1] - draw[:, 0]))
    low, high = np.quantile(samples, [0.05, 0.95])
    return {
        "estimate": estimate,
        "ci90": [float(low), float(high)],
        "clusters": int(len(grouped)),
        "iterations": int(iterations),
        "unit": "athlete-clustered MAE advantage; positive favors the model",
    }


def _reference_summary(frame: pd.DataFrame, features: tuple[str, ...]) -> dict:
    summary: dict[str, dict] = {}
    for feature in features:
        values = pd.to_numeric(frame.get(feature), errors="coerce").dropna()
        if values.empty:
            continue
        q1, median, q3 = values.quantile([0.25, 0.5, 0.75])
        summary[feature] = {
            "n": int(len(values)),
            "median": float(median),
            "iqr": float(q3 - q1),
            "p01": float(values.quantile(0.01)),
            "p99": float(values.quantile(0.99)),
        }
    return summary


def ood_diagnostics(row: pd.DataFrame, reference: dict) -> dict:
    if len(row) != 1:
        raise ValueError("OOD diagnostics expect exactly one athlete row")
    details = []
    for feature, stats in reference.items():
        value = pd.to_numeric(row.get(feature), errors="coerce").iloc[0]
        if not np.isfinite(value):
            details.append({"feature": feature, "status": "missing", "robust_z": None})
            continue
        scale = stats["iqr"] / 1.349 if stats["iqr"] > 1e-9 else 1.0
        robust_z = float(abs(value - stats["median"]) / scale)
        outside = bool(value < stats["p01"] or value > stats["p99"])
        details.append(
            {
                "feature": feature,
                "status": "outside_1_99_reference" if outside else "inside_reference",
                "robust_z": robust_z,
            }
        )
    finite = [item["robust_z"] for item in details if item["robust_z"] is not None]
    physical = [
        item["robust_z"]
        for item in details
        if item["feature"] in {"height_cm", "weight_kg", "bmi"}
        and item["robust_z"] is not None
    ]
    capability = [
        item["robust_z"]
        for item in details
        if item["feature"].startswith("dimension_") and item["robust_z"] is not None
    ]
    maximum = max(finite, default=None)
    physical_maximum = max(physical, default=None)
    capability_maximum = max(capability, default=None)
    physical_status = (
        "out_of_domain"
        if physical_maximum is not None and physical_maximum > 3.5
        else "in_domain"
    )
    capability_status = (
        "out_of_domain"
        if capability_maximum is not None and capability_maximum > 4.5
        else "in_domain"
    )
    return {
        "status": (
            "out_of_domain"
            if physical_status == "out_of_domain" or capability_status == "out_of_domain"
            else "in_domain_with_age_warning"
            if any(
                item["feature"] == "age"
                and item["robust_z"] is not None
                and item["robust_z"] > 3.5
                for item in details
            )
            else "in_domain"
        ),
        "max_robust_z": maximum,
        "physical_status": physical_status,
        "physical_max_robust_z": physical_maximum,
        "capability_status": capability_status,
        "capability_max_robust_z": capability_maximum,
        "features": details,
    }


def _fit_with_evaluation(
    frame: pd.DataFrame,
    *,
    features: tuple[str, ...],
    target: str,
    time_column: str = "season",
    frozen_season: int = FROZEN_TEST_SEASON,
    sample_weight_column: str | None = None,
    evaluation_eligible_column: str | None = None,
    diagnostic_player_ids: dict[str, str] | None = None,
) -> dict:
    source = _with_bmi(frame)
    source = source.loc[_finite_target(source, target)].copy()
    train = source.loc[pd.to_numeric(source[time_column], errors="coerce") < frozen_season]
    evaluation_source = source
    if evaluation_eligible_column is not None:
        eligible = evaluation_source.get(
            evaluation_eligible_column,
            pd.Series(False, index=evaluation_source.index),
        )
        evaluation_source = evaluation_source.loc[eligible.fillna(False).astype(bool)]
    test = evaluation_source.loc[
        pd.to_numeric(evaluation_source[time_column], errors="coerce") == frozen_season
    ]
    if train.empty:
        raise ValueError("No pre-freeze rows available")

    rolling = []
    rolling_residuals: list[dict] = []
    for season in sorted(pd.to_numeric(source[time_column], errors="coerce").dropna().unique()):
        season = int(season)
        if season >= frozen_season:
            continue
        fold_train = source.loc[source[time_column] < season]
        fold_test = evaluation_source.loc[evaluation_source[time_column] == season]
        minimum = max(12, len(features) * 3)
        if len(fold_train) < minimum or len(fold_test) < 5:
            continue
        try:
            model = LinearPercentileModel(features).fit(
                fold_train,
                target,
                sample_weight=_training_weights(fold_train, sample_weight_column),
            )
        except ValueError:
            continue
        fold_prediction = model.predict(fold_test)
        rolling.append(
            {
                "season": season,
                **_regression_metrics(fold_test[target], fold_prediction),
            }
        )
        fold_actual = pd.to_numeric(fold_test[target], errors="coerce").to_numpy(float)
        if "player_id" in fold_test:
            athlete_ids = fold_test["player_id"].astype(str).tolist()
        else:
            athlete_ids = [f"row-{season}-{index}" for index in range(len(fold_test))]
        for athlete_id, actual, prediction in zip(
            athlete_ids, fold_actual, fold_prediction
        ):
            if np.isfinite(actual) and np.isfinite(prediction):
                rolling_residuals.append(
                    {
                        "athlete_id": athlete_id,
                        "season": int(season),
                        "absolute_residual": float(abs(actual - prediction)),
                    }
                )

    evaluation_model = LinearPercentileModel(features).fit(
        train,
        target,
        sample_weight=_training_weights(train, sample_weight_column),
    )
    frozen_prediction = evaluation_model.predict(test) if len(test) else np.asarray([])
    frozen = _regression_metrics(test[target], frozen_prediction) if len(test) else {
        "n": 0,
        "mae": None,
        "rmse": None,
        "spearman": None,
    }
    baseline = _regression_metrics(test[target], np.full(len(test), 50.0)) if len(test) else {
        "n": 0,
        "mae": None,
        "rmse": None,
        "spearman": None,
    }
    clusters = (
        test["player_id"].astype(str)
        if "player_id" in test
        else pd.Series(np.arange(len(test)), index=test.index).astype(str)
    )
    baseline_advantage = _cluster_bootstrap_advantage(
        test[target],
        frozen_prediction,
        np.full(len(test), 50.0),
        clusters,
    )
    percentile_diagnostics = _percentile_diagnostics(test[target], frozen_prediction)
    top_decile = percentile_diagnostics.pop("top_decile")
    prediction_interval = _conformal_interval(rolling_residuals)
    interval_radius = prediction_interval["half_width"]
    if interval_radius is not None and len(test):
        frozen_actual = pd.to_numeric(test[target], errors="coerce").to_numpy(float)
        valid = np.isfinite(frozen_actual) & np.isfinite(frozen_prediction)
        covered = np.abs(frozen_actual[valid] - frozen_prediction[valid]) <= interval_radius
        lower = np.maximum(0.0, frozen_prediction[valid] - interval_radius)
        upper = np.minimum(100.0, frozen_prediction[valid] + interval_radius)
        prediction_interval["frozen_empirical_coverage"] = (
            float(covered.mean()) if len(covered) else None
        )
        prediction_interval["frozen_evaluation_n"] = int(len(covered))
        prediction_interval["frozen_mean_clipped_width"] = (
            float(np.mean(upper - lower)) if len(covered) else None
        )
    else:
        prediction_interval["frozen_empirical_coverage"] = None
        prediction_interval["frozen_evaluation_n"] = int(len(test))
        prediction_interval["frozen_mean_clipped_width"] = None

    face_checks: dict[str, dict] = {}
    if diagnostic_player_ids and len(test) and "player_id" in test:
        test_ids = test["player_id"].astype(str).to_numpy()
        actual_values = pd.to_numeric(test[target], errors="coerce").to_numpy(float)
        for player_id, label in diagnostic_player_ids.items():
            matches = np.flatnonzero(test_ids == str(player_id))
            if not len(matches):
                face_checks[label] = {
                    "player_id": str(player_id),
                    "status": "identity_not_in_frozen_role",
                    "actual": None,
                    "predicted": None,
                }
                continue
            index = int(matches[-1])
            actual = float(actual_values[index])
            predicted = float(frozen_prediction[index])
            if actual >= 90.0 and predicted >= 90.0:
                check_status = "top_decile_reproduced"
            elif actual >= 90.0:
                check_status = "top_decile_missed"
            elif predicted >= 90.0:
                check_status = "false_top_decile"
            else:
                check_status = "reference_not_top_decile_in_broad_role_target"
            check = {
                "player_id": str(player_id),
                "status": check_status,
                "actual": actual,
                "predicted": predicted,
                "absolute_error": float(abs(actual - predicted)),
                "actual_top_decile": bool(actual >= 90.0),
                "predicted_top_decile": bool(predicted >= 90.0),
                "interpretation": (
                    "Predeclared descriptive face check; it is never used to tune features, "
                    "weights, gates, or the interval."
                ),
            }
            if interval_radius is not None:
                check["prediction_range_90"] = [
                    max(0.0, predicted - interval_radius),
                    min(100.0, predicted + interval_radius),
                ]
                check["range_covers_actual"] = bool(
                    abs(actual - predicted) <= interval_radius
                )
            face_checks[label] = check

    athlete_disjoint = _athlete_disjoint_validation(
        source,
        evaluation_source,
        features=features,
        target=target,
        time_column=time_column,
        frozen_season=frozen_season,
        sample_weight_column=sample_weight_column,
    )
    unseen_history = {"n": 0, "mae": None, "rmse": None, "spearman": None}
    if len(test) and "player_id" in source:
        known = set(train["player_id"].astype(str))
        unseen_history_mask = ~test["player_id"].astype(str).isin(known)
        unseen_history = _regression_metrics(
            test.loc[unseen_history_mask, target],
            frozen_prediction[unseen_history_mask.to_numpy()],
        )
    final = LinearPercentileModel(features).fit(
        source,
        target,
        sample_weight=_training_weights(source, sample_weight_column),
    )
    status = "insufficient_frozen_evidence"
    if frozen["n"] >= 20 and frozen["mae"] is not None and baseline["mae"] is not None:
        status = (
            "beats_neutral_baseline"
            if frozen["mae"] < baseline["mae"]
            else "does_not_beat_neutral_baseline"
        )
    ci_low = baseline_advantage["ci90"][0]
    evidence_gate = (
        "supported"
        if status == "beats_neutral_baseline" and ci_low is not None and ci_low > 0
        else "not_supported"
        if frozen["n"] >= 20
        else "insufficient_frozen_evidence"
    )
    residual_mae = frozen["mae"] if frozen["mae"] is not None else baseline["mae"]
    return {
        "model": final,
        "features": list(features),
        "status": status,
        "evaluation": {
            "frozen_season": frozen_season,
            "frozen": frozen,
            "unseen_history_slice": unseen_history,
            "neutral_50": baseline,
            "mae_advantage_vs_neutral": baseline_advantage,
            "rolling_origin": rolling,
            "athlete_disjoint": athlete_disjoint,
            "percentile_calibration": percentile_diagnostics,
            "top_decile": top_decile,
            "frozen_player_face_checks": face_checks,
        },
        "evidence_gate": evidence_gate,
        "frozen_residual_mae": residual_mae,
        "prediction_interval": prediction_interval,
        "reference": _reference_summary(source, features),
        "training_weight_policy": (
            sample_weight_column if sample_weight_column is not None else "uniform"
        ),
        "evaluation_policy": (
            f"{evaluation_eligible_column} == True"
            if evaluation_eligible_column is not None
            else "all finite-target rows"
        ),
    }


def _dimensions(spec: RoleSpec) -> tuple[str, ...]:
    return spec.dimensions


def _weighted_training_rows(
    frame: pd.DataFrame,
    *,
    status_column: str = "target_status",
    weight_column: str = "training_sample_weight",
) -> pd.DataFrame:
    """Keep positive-evidence labels and attach a conservative fallback weight.

    Real scored panels provide empirical opportunity/coverage weights.  The
    status fallback keeps synthetic and older cached panels compatible while
    ensuring a low-sample row never receives the same influence as an eligible
    row.
    """
    result = frame.loc[frame[status_column].isin(["eligible", "low_sample"])].copy()
    fallback = result[status_column].map({"eligible": 1.0, "low_sample": 0.25}).astype(float)
    if weight_column in result:
        observed = pd.to_numeric(result[weight_column], errors="coerce")
        result[weight_column] = observed.where(observed.gt(0), fallback)
    else:
        result[weight_column] = fallback
    return result


def _frozen_feature_advantage(
    frame: pd.DataFrame,
    *,
    full_features: tuple[str, ...],
    baseline_features: tuple[str, ...],
    target: str,
    time_column: str,
    sample_weight_column: str,
    evaluation_eligible_column: str,
    frozen_season: int = FROZEN_TEST_SEASON,
) -> tuple[dict, dict]:
    """Compare two feature contracts on the same future eligible athletes."""
    source = _with_bmi(frame)
    source = source.loc[_finite_target(source, target)].copy()
    seasons = pd.to_numeric(source[time_column], errors="coerce")
    train = source.loc[seasons < frozen_season]
    test = source.loc[
        seasons.eq(frozen_season)
        & source[evaluation_eligible_column].fillna(False).astype(bool)
    ]
    minimum = max(12, len(full_features) * 3, len(baseline_features) * 3)
    if len(train) < minimum or test.empty:
        empty = {
            "estimate": None,
            "ci90": [None, None],
            "clusters": 0,
            "iterations": 0,
            "comparator": "build_only",
        }
        return empty, _regression_metrics([], [])
    weights = _training_weights(train, sample_weight_column)
    full = LinearPercentileModel(full_features).fit(train, target, sample_weight=weights)
    baseline = LinearPercentileModel(baseline_features).fit(
        train, target, sample_weight=weights
    )
    actual = test[target]
    full_prediction = full.predict(test)
    baseline_prediction = baseline.predict(test)
    advantage = _cluster_bootstrap_advantage(
        actual,
        full_prediction,
        baseline_prediction,
        test["player_id"],
    )
    advantage["comparator"] = "build_only"
    return advantage, _regression_metrics(actual, baseline_prediction)


def train_physical_models(
    scored: pd.DataFrame,
    *,
    specs: dict[str, RoleSpec] | None = None,
) -> dict[str, dict]:
    available = role_specs() if specs is None else specs
    source = _with_bmi(scored)
    heads: dict[str, dict] = {}
    for key, spec in available.items():
        if not spec.domains:
            heads[key] = {"status": spec.evidence_status, "limitation": spec.limitation}
            continue
        candidates = source.loc[
            source["sport"].eq(spec.sport) & source["role"].eq(spec.role)
        ].copy()
        eligible = candidates.loc[
            candidates["target_status"].eq("eligible")
            & _finite_target(candidates, "observed_role_percentile")
        ].copy()
        trainable = _weighted_training_rows(candidates)
        trainable = trainable.loc[
            _finite_target(trainable, "observed_role_percentile")
        ].copy()
        trainable["evaluation_eligible"] = trainable["target_status"].eq("eligible")
        required_inputs = ("height_cm", "weight_kg")
        eligible_usable = eligible.loc[
            _complete_numeric_inputs(eligible, required_inputs)
        ].copy()
        role_frame = trainable.loc[
            _complete_numeric_inputs(trainable, required_inputs)
        ].copy()
        coverage = _coverage_summary(
            candidates,
            eligible,
            eligible_usable,
            required_inputs=required_inputs,
            extra={
                "training_usable_rows": int(len(role_frame)),
                "weighted_low_sample_rows": int(
                    role_frame["target_status"].eq("low_sample").sum()
                ),
            },
        )
        try:
            head = _fit_with_evaluation(
                role_frame,
                features=PHYSICAL_FEATURES,
                target="observed_role_percentile",
                sample_weight_column="training_sample_weight",
                evaluation_eligible_column="evaluation_eligible",
                diagnostic_player_ids=(
                    NBA_MODEL_FACE_CHECKS.get(spec.role)
                    if spec.sport == "nba"
                    else None
                ),
            )
        except ValueError as error:
            heads[key] = {
                "status": "not_fit",
                "reason": str(error),
                "usable_coverage": coverage,
            }
            continue
        head["usable_coverage"] = coverage
        head["training_label_policy"] = (
            "eligible labels receive full empirical reliability weight; positive-opportunity "
            "low-sample labels receive reduced opportunity/coverage weight; frozen evaluation "
            "remains eligible-only"
        )
        heads[key] = head
    return heads


def build_native_forecast_pairs(scored: pd.DataFrame) -> pd.DataFrame:
    source = _with_bmi(scored)
    if "training_sample_weight" not in source:
        source["training_sample_weight"] = source["target_status"].map(
            {"eligible": 1.0, "low_sample": 0.25}
        )
    if "opportunity_reliability" not in source:
        source["opportunity_reliability"] = source["target_status"].map(
            {"eligible": 1.0, "low_sample": 0.25}
        )
    prior = source.copy()
    prior["target_season"] = prior["season"] + 1
    target = source[
        [
            "sport",
            "player_id",
            "season",
            "observed_role_percentile",
            "role",
            "target_status",
            "training_sample_weight",
            "opportunity_reliability",
        ]
    ].rename(
        columns={
            "season": "target_season",
            "observed_role_percentile": "target_observed_role_percentile",
            "role": "realized_target_role",
            "target_status": "realized_target_status",
            "training_sample_weight": "realized_training_sample_weight",
            "opportunity_reliability": "realized_opportunity_reliability",
        }
    )
    pairs = prior.merge(
        target,
        on=["sport", "player_id", "target_season"],
        how="inner",
        validate="one_to_one",
    )
    pairs = pairs.rename(columns={"role": "prior_role", "season": "feature_season"})
    pairs["same_role_target"] = pairs["realized_target_role"].eq(pairs["prior_role"])
    pairs["target_eligible"] = pairs["realized_target_status"].eq("eligible")
    prior_weight = pd.to_numeric(pairs["training_sample_weight"], errors="coerce")
    realized_weight = pd.to_numeric(
        pairs["realized_training_sample_weight"], errors="coerce"
    )
    pairs["pair_training_sample_weight"] = np.sqrt(prior_weight * realized_weight)
    return pairs


def train_native_forecast_models(
    scored: pd.DataFrame,
    *,
    specs: dict[str, RoleSpec] | None = None,
) -> tuple[dict[str, dict], pd.DataFrame]:
    available = role_specs() if specs is None else specs
    pairs = build_native_forecast_pairs(scored)
    heads: dict[str, dict] = {}
    for key, spec in available.items():
        if not spec.domains:
            heads[key] = {"status": spec.evidence_status}
            continue
        dimensions = tuple(f"dimension_{name}_percentile" for name in _dimensions(spec))
        features = (
            *PHYSICAL_FEATURES,
            "observed_role_percentile",
            "availability_percentile",
            "sustained_3y_percentile",
            *dimensions,
        )
        candidates = pairs.loc[
            pairs["sport"].eq(spec.sport) & pairs["prior_role"].eq(spec.role)
        ].copy()
        same_role = candidates.loc[candidates["same_role_target"]].copy()
        eligible = same_role.loc[
            same_role["target_status"].eq("eligible")
            & same_role["target_eligible"]
            & _finite_target(same_role, "target_observed_role_percentile")
        ].copy()
        trainable = same_role.loc[
            same_role["target_status"].isin(["eligible", "low_sample"])
            & same_role["realized_target_status"].isin(["eligible", "low_sample"])
            & _finite_target(same_role, "target_observed_role_percentile")
        ].copy()
        trainable["evaluation_eligible"] = (
            trainable["target_status"].eq("eligible")
            & trainable["realized_target_status"].eq("eligible")
        )
        required_inputs = ("height_cm", "weight_kg", *dimensions)
        eligible_usable = eligible.loc[
            _complete_numeric_inputs(eligible, required_inputs)
        ].copy()
        eligible_usable["season"] = eligible_usable["target_season"]
        role_pairs = trainable.loc[
            _complete_numeric_inputs(trainable, required_inputs)
        ].copy()
        role_pairs["season"] = role_pairs["target_season"]
        coverage = _coverage_summary(
            candidates,
            eligible,
            eligible_usable,
            required_inputs=required_inputs,
            extra={
                "same_role_rows": int(len(same_role)),
                "excluded_role_transition_rows": int(len(candidates) - len(same_role)),
                "prior_eligible_same_role_rows": int(
                    same_role["target_status"].eq("eligible").sum()
                ),
                "realized_target_eligible_same_role_rows": int(
                    same_role["target_eligible"].sum()
                ),
                "training_usable_rows": int(len(role_pairs)),
                "weighted_low_sample_rows": int(
                    (~role_pairs["evaluation_eligible"]).sum()
                ),
            },
        )
        try:
            head = _fit_with_evaluation(
                role_pairs,
                features=tuple(features),
                target="target_observed_role_percentile",
                sample_weight_column="pair_training_sample_weight",
                evaluation_eligible_column="evaluation_eligible",
                diagnostic_player_ids=(
                    NBA_MODEL_FACE_CHECKS.get(spec.role)
                    if spec.sport == "nba"
                    else None
                ),
            )
        except ValueError as error:
            heads[key] = {
                "status": "not_fit",
                "reason": str(error),
                "usable_coverage": coverage,
            }
            continue
        head["usable_coverage"] = coverage
        head["training_label_policy"] = (
            "same-role consecutive seasons with positive observed labels; low-sample pairs are "
            "reliability-weighted for training and frozen evaluation remains eligible-only"
        )

        frozen = role_pairs.loc[
            role_pairs["target_season"].eq(FROZEN_TEST_SEASON)
            & role_pairs["evaluation_eligible"]
        ]
        y = frozen["target_observed_role_percentile"]
        prior_baseline = _regression_metrics(y, frozen["observed_role_percentile"])
        sustained_baseline = _regression_metrics(y, frozen["sustained_3y_percentile"])
        head["evaluation"]["prior_season_baseline"] = prior_baseline
        head["evaluation"]["rolling_3y_baseline"] = sustained_baseline
        candidates = {
            "previous_season": (prior_baseline, frozen["observed_role_percentile"]),
            "rolling_3y": (sustained_baseline, frozen["sustained_3y_percentile"]),
        }
        candidates = {
            name: values for name, values in candidates.items() if values[0]["mae"] is not None
        }
        if len(frozen) and candidates:
            comparator_name = min(candidates, key=lambda name: candidates[name][0]["mae"])
            prefreeze = role_pairs.loc[role_pairs["target_season"] < FROZEN_TEST_SEASON]
            evaluation_model = LinearPercentileModel(tuple(features)).fit(
                prefreeze,
                "target_observed_role_percentile",
                sample_weight=_training_weights(prefreeze, "pair_training_sample_weight"),
            )
            model_prediction = evaluation_model.predict(frozen)
            advantage = _cluster_bootstrap_advantage(
                y,
                model_prediction,
                candidates[comparator_name][1],
                frozen["player_id"],
            )
            advantage["comparator"] = comparator_name
        else:
            advantage = {
                "estimate": None,
                "ci90": [None, None],
                "clusters": 0,
                "iterations": 0,
                "comparator": None,
            }
        head["evaluation"]["mae_advantage_vs_best_history_baseline"] = advantage
        ci_low = advantage["ci90"][0]
        head["forecast_support"] = (
            "supported_over_history_baselines"
            if ci_low is not None and ci_low > 0
            else "history_baseline_preferred_or_insufficient"
        )
        head["deployment_support"] = (
            "supported_over_neutral_and_history_baselines"
            if head["evidence_gate"] == "supported"
            and head["forecast_support"] == "supported_over_history_baselines"
            else "experimental_unsupported"
        )
        head["selected_model_family"] = "native_forecast_without_team_context"
        head["context_version"] = CONTEXT_VERSION
        head["context_features"] = []
        head["context_candidate_features"] = list(CONTEXT_FEATURES)
        head["context_model_selected"] = False

        # Team context is a predeclared candidate, not an automatic feature
        # expansion.  Completed season t is already on the prior side of the
        # pair, so these inputs can only predict t+1.  The role/history model
        # remains deployed unless the contextual candidate clears an explicit
        # frozen comparison on the same athletes.
        context_columns = role_pairs.reindex(columns=list(CONTEXT_FEATURES)).apply(
            pd.to_numeric, errors="coerce"
        )
        context_complete = np.isfinite(context_columns).all(axis=1)
        prefreeze_mask = role_pairs["target_season"].lt(FROZEN_TEST_SEASON)
        frozen_mask = role_pairs["target_season"].eq(FROZEN_TEST_SEASON) & role_pairs[
            "evaluation_eligible"
        ]
        context_coverage = {
            "training_rows_with_both_fields": int(
                (context_complete & prefreeze_mask).sum()
            ),
            "frozen_eligible_rows_with_both_fields": int(
                (context_complete & frozen_mask).sum()
            ),
            "training_fraction_with_both_fields": (
                float(context_complete.loc[prefreeze_mask].mean())
                if prefreeze_mask.any()
                else None
            ),
            "frozen_eligible_fraction_with_both_fields": (
                float(context_complete.loc[frozen_mask].mean())
                if frozen_mask.any()
                else None
            ),
        }
        head["context_coverage"] = context_coverage
        head["context_increment_gate"] = "not_available"
        head["context_selection_reason"] = "context_fields_absent_or_too_sparse"

        context_features = (*features, *CONTEXT_FEATURES)
        has_context_training = all(
            feature in role_pairs
            and pd.to_numeric(role_pairs.loc[prefreeze_mask, feature], errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .notna()
            .any()
            for feature in CONTEXT_FEATURES
        )
        if has_context_training:
            try:
                context_head = _fit_with_evaluation(
                    role_pairs,
                    features=tuple(context_features),
                    target="target_observed_role_percentile",
                    sample_weight_column="pair_training_sample_weight",
                    evaluation_eligible_column="evaluation_eligible",
                    diagnostic_player_ids=(
                        NBA_MODEL_FACE_CHECKS.get(spec.role)
                        if spec.sport == "nba"
                        else None
                    ),
                )
                context_vs_base, base_frozen_metrics = _frozen_feature_advantage(
                    role_pairs,
                    full_features=tuple(context_features),
                    baseline_features=tuple(features),
                    target="target_observed_role_percentile",
                    time_column="target_season",
                    sample_weight_column="pair_training_sample_weight",
                    evaluation_eligible_column="evaluation_eligible",
                )
                context_vs_base["comparator"] = (
                    "native_forecast_without_team_context"
                )

                if len(frozen) and candidates:
                    comparator_name = min(
                        candidates, key=lambda name: candidates[name][0]["mae"]
                    )
                    context_evaluation_model = LinearPercentileModel(
                        tuple(context_features)
                    ).fit(
                        prefreeze,
                        "target_observed_role_percentile",
                        sample_weight=_training_weights(
                            prefreeze, "pair_training_sample_weight"
                        ),
                    )
                    context_prediction = context_evaluation_model.predict(frozen)
                    context_vs_history = _cluster_bootstrap_advantage(
                        y,
                        context_prediction,
                        candidates[comparator_name][1],
                        frozen["player_id"],
                    )
                    context_vs_history["comparator"] = comparator_name
                else:
                    context_vs_history = {
                        "estimate": None,
                        "ci90": [None, None],
                        "clusters": 0,
                        "iterations": 0,
                        "comparator": None,
                    }

                context_head["evaluation"]["prior_season_baseline"] = prior_baseline
                context_head["evaluation"]["rolling_3y_baseline"] = sustained_baseline
                context_head["evaluation"][
                    "mae_advantage_vs_best_history_baseline"
                ] = context_vs_history
                context_head["evaluation"][
                    "mae_advantage_context_vs_base_native_forecast"
                ] = context_vs_base
                context_head["evaluation"][
                    "base_native_forecast_on_same_frozen_rows"
                ] = base_frozen_metrics

                context_base_ci_low = context_vs_base["ci90"][0]
                context_history_ci_low = context_vs_history["ci90"][0]
                context_frozen_n = context_head["evaluation"]["frozen"]["n"]
                complete_frozen_n = context_coverage[
                    "frozen_eligible_rows_with_both_fields"
                ]
                context_gate = (
                    "supported"
                    if context_frozen_n >= 20
                    and complete_frozen_n >= 20
                    and context_head["evidence_gate"] == "supported"
                    and context_base_ci_low is not None
                    and context_base_ci_low > 0
                    and context_history_ci_low is not None
                    and context_history_ci_low > 0
                    else "not_supported"
                    if context_frozen_n >= 20
                    else "insufficient_frozen_evidence"
                )
                context_summary = {
                    "features": list(context_features),
                    "status": context_head["status"],
                    "evidence_gate": context_head["evidence_gate"],
                    "frozen": context_head["evaluation"]["frozen"],
                    "athlete_disjoint": context_head["evaluation"][
                        "athlete_disjoint"
                    ],
                    "percentile_calibration": context_head["evaluation"][
                        "percentile_calibration"
                    ],
                    "top_decile": context_head["evaluation"]["top_decile"],
                    "prediction_interval": context_head["prediction_interval"],
                    "mae_advantage_vs_base_native_forecast": context_vs_base,
                    "mae_advantage_vs_best_history_baseline": context_vs_history,
                }
                head["evaluation"]["team_context_candidate"] = context_summary
                head["context_increment_gate"] = context_gate
                head["context_selection_reason"] = (
                    "frozen_context_candidate_cleared_neutral_history_and_base_gates"
                    if context_gate == "supported"
                    else "role_history_model_retained_by_context_evidence_gate"
                )

                if context_gate == "supported":
                    context_head["usable_coverage"] = coverage
                    context_head["training_label_policy"] = head[
                        "training_label_policy"
                    ]
                    context_head["selected_model_family"] = (
                        "native_forecast_with_team_context"
                    )
                    context_head["context_version"] = CONTEXT_VERSION
                    context_head["context_features"] = list(CONTEXT_FEATURES)
                    context_head["context_candidate_features"] = list(
                        CONTEXT_FEATURES
                    )
                    context_head["context_model_selected"] = True
                    context_head["context_coverage"] = context_coverage
                    context_head["context_increment_gate"] = context_gate
                    context_head["context_selection_reason"] = head[
                        "context_selection_reason"
                    ]
                    context_head["forecast_support"] = (
                        "supported_over_history_baselines"
                    )
                    context_head["deployment_support"] = (
                        "supported_over_neutral_history_and_base_native_forecast"
                    )
                    context_head["evaluation"][
                        "base_native_forecast_ablation"
                    ] = {
                        "features": list(features),
                        "frozen": head["evaluation"]["frozen"],
                        "evidence_gate": head["evidence_gate"],
                    }
                    head = context_head
            except ValueError as error:
                head["context_selection_reason"] = (
                    f"context_candidate_not_fit: {error}"
                )
        heads[key] = head
    return heads, pairs


_POOL_ROLE_COLUMN = "_pool_role_key"
_POOL_TARGET = "target_observed_role_percentile"
_POOL_WEIGHT = "pair_training_sample_weight"


def _empty_pooling_advantage() -> dict:
    return {
        "estimate": None,
        "ci90": [None, None],
        "clusters": 0,
        "iterations": 0,
        "comparator": "role_only",
    }


def _pooling_family_frame(
    pooling_inputs: dict[str, dict],
    family_role_keys: tuple[str, ...],
) -> tuple[pd.DataFrame, tuple[str, ...]] | None:
    """Combine successfully fit role frames under one fixed feature contract."""
    active = [role_key for role_key in family_role_keys if role_key in pooling_inputs]
    if len(active) < 2:
        return None
    first_features = tuple(pooling_inputs[active[0]]["features"])
    feature_set = set(first_features)
    if any(set(pooling_inputs[key]["features"]) != feature_set for key in active[1:]):
        return None
    frames = []
    for role_key in active:
        role_frame = pooling_inputs[role_key]["frame"].copy()
        role_frame[_POOL_ROLE_COLUMN] = role_key
        frames.append(role_frame)
    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined = add_role_dummies(
        combined,
        role_column=_POOL_ROLE_COLUMN,
        family_role_keys=family_role_keys,
    )
    return _with_bmi(combined), first_features


def _select_family_pooling_tau(
    family_frame: pd.DataFrame,
    *,
    features: tuple[str, ...],
    family_role_keys: tuple[str, ...],
    frozen_season: int = FROZEN_TEST_SEASON,
    candidate_taus: tuple[float, ...] = POOLING_TAUS,
) -> dict:
    """Choose shrinkage on rolling-origin folds strictly before the freeze.

    Tau zero is the predeclared role-only candidate.  The selected value is
    frozen before the 2025 outcome comparison and is never recomputed from
    frozen labels.
    """
    source = _with_bmi(family_frame)
    dummy_features = tuple(role_dummy_name(key) for key in family_role_keys)
    family_features = (*features, *dummy_features)
    seasons = pd.to_numeric(source["target_season"], errors="coerce")
    records = {
        float(tau): {"actual": [], "predicted": []} for tau in candidate_taus
    }
    fold_rows: list[dict] = []
    family_minimum = max(12, len(family_features) * 3)
    role_minimum = max(12, len(features) * 3)
    for value in sorted(seasons.dropna().unique()):
        season = int(value)
        if season >= frozen_season:
            continue
        fold_train = source.loc[seasons < season]
        fold_test = source.loc[
            seasons.eq(season)
            & source["evaluation_eligible"].fillna(False).astype(bool)
        ]
        if len(fold_train) < family_minimum or fold_test.empty:
            continue
        try:
            family_model = LinearPercentileModel(family_features).fit(
                fold_train,
                _POOL_TARGET,
                sample_weight=_training_weights(fold_train, _POOL_WEIGHT),
            )
        except ValueError:
            continue
        role_counts: dict[str, int] = {}
        for role_key in family_role_keys:
            role_train = fold_train.loc[fold_train[_POOL_ROLE_COLUMN].eq(role_key)]
            role_test = fold_test.loc[fold_test[_POOL_ROLE_COLUMN].eq(role_key)]
            if len(role_train) < role_minimum or role_test.empty:
                continue
            try:
                role_model = LinearPercentileModel(features).fit(
                    role_train,
                    _POOL_TARGET,
                    sample_weight=_training_weights(role_train, _POOL_WEIGHT),
                )
            except ValueError:
                continue
            role_prediction = role_model.predict(role_test)
            family_prediction = family_model.predict(role_test)
            actual = pd.to_numeric(role_test[_POOL_TARGET], errors="coerce").to_numpy(float)
            effective_rows = effective_sample_size(
                _training_weights(role_train, _POOL_WEIGHT)
            )
            role_counts[role_key] = int(len(role_test))
            for tau in candidate_taus:
                role_weight = role_blend_weight(effective_rows, float(tau))
                prediction = (
                    role_weight * role_prediction
                    + (1.0 - role_weight) * family_prediction
                )
                records[float(tau)]["actual"].extend(actual.tolist())
                records[float(tau)]["predicted"].extend(prediction.tolist())
        if role_counts:
            fold_rows.append(
                {
                    "season": season,
                    "n": int(sum(role_counts.values())),
                    "roles": role_counts,
                }
            )

    scores = []
    for tau in candidate_taus:
        values = records[float(tau)]
        scores.append(
            {
                "tau": float(tau),
                **_regression_metrics(values["actual"], values["predicted"]),
            }
        )
    usable = [score for score in scores if score["n"] and score["mae"] is not None]
    selected = min(usable, key=lambda item: (item["mae"], item["tau"])) if usable else None
    return {
        "status": "selected_from_prefreeze_rolling_origin" if selected else "insufficient_prefreeze_evidence",
        "policy": (
            "minimum unweighted MAE across rolling-origin evaluation rows with target season "
            f"strictly before {frozen_season}; ties prefer the smaller tau"
        ),
        "candidate_taus": [float(tau) for tau in candidate_taus],
        "rolling_folds": fold_rows,
        "scores": scores,
        "selected_tau": float(selected["tau"]) if selected else None,
        "tuning_season_upper_bound_exclusive": int(frozen_season),
    }


def _pooling_frozen_comparison(
    family_frame: pd.DataFrame,
    *,
    role_key: str,
    features: tuple[str, ...],
    family_role_keys: tuple[str, ...],
    tau: float,
    frozen_season: int = FROZEN_TEST_SEASON,
) -> dict:
    """Compare fixed-tau shrinkage with role-only on the frozen cohort."""
    source = _with_bmi(family_frame)
    dummy_features = tuple(role_dummy_name(key) for key in family_role_keys)
    family_features = (*features, *dummy_features)
    seasons = pd.to_numeric(source["target_season"], errors="coerce")
    prefreeze = source.loc[seasons < frozen_season]
    role_prefreeze = prefreeze.loc[prefreeze[_POOL_ROLE_COLUMN].eq(role_key)]
    frozen = source.loc[
        seasons.eq(frozen_season)
        & source[_POOL_ROLE_COLUMN].eq(role_key)
        & source["evaluation_eligible"].fillna(False).astype(bool)
    ]
    empty = {
        "n": int(len(frozen)),
        "effective_role_rows": effective_sample_size(
            _training_weights(role_prefreeze, _POOL_WEIGHT)
        ),
        "role_weight": None,
        "role_only": _regression_metrics([], []),
        "partially_pooled": _regression_metrics([], []),
        "advantage": _empty_pooling_advantage(),
    }
    family_minimum = max(12, len(family_features) * 3)
    role_minimum = max(12, len(features) * 3)
    if (
        len(prefreeze) < family_minimum
        or len(role_prefreeze) < role_minimum
        or frozen.empty
    ):
        return empty
    try:
        family_model = LinearPercentileModel(family_features).fit(
            prefreeze,
            _POOL_TARGET,
            sample_weight=_training_weights(prefreeze, _POOL_WEIGHT),
        )
        role_model = LinearPercentileModel(features).fit(
            role_prefreeze,
            _POOL_TARGET,
            sample_weight=_training_weights(role_prefreeze, _POOL_WEIGHT),
        )
    except ValueError:
        return empty
    role_prediction = role_model.predict(frozen)
    family_prediction = family_model.predict(frozen)
    effective_rows = effective_sample_size(
        _training_weights(role_prefreeze, _POOL_WEIGHT)
    )
    role_weight = role_blend_weight(effective_rows, tau)
    pooled_prediction = (
        role_weight * role_prediction + (1.0 - role_weight) * family_prediction
    )
    actual = frozen[_POOL_TARGET]
    advantage = _cluster_bootstrap_advantage(
        actual,
        pooled_prediction,
        role_prediction,
        frozen["player_id"],
    )
    advantage["comparator"] = "role_only"
    return {
        "n": int(len(frozen)),
        "effective_role_rows": float(effective_rows),
        "role_weight": float(role_weight),
        "role_only": _regression_metrics(actual, role_prediction),
        "partially_pooled": _regression_metrics(actual, pooled_prediction),
        "advantage": advantage,
        "_actual": pd.to_numeric(actual, errors="coerce").to_numpy(float),
        "_prediction": np.asarray(pooled_prediction, dtype=float),
        "_athlete_ids": frozen["player_id"].astype(str).tolist(),
    }


def _pooling_rolling_diagnostics(
    family_frame: pd.DataFrame,
    *,
    role_key: str,
    features: tuple[str, ...],
    family_role_keys: tuple[str, ...],
    tau: float,
    frozen_season: int = FROZEN_TEST_SEASON,
) -> dict:
    """Calibrate diagnostics for the exact selected pooled estimator."""
    source = _with_bmi(family_frame)
    dummy_features = tuple(role_dummy_name(key) for key in family_role_keys)
    family_features = (*features, *dummy_features)
    seasons = pd.to_numeric(source["target_season"], errors="coerce")
    family_minimum = max(12, len(family_features) * 3)
    role_minimum = max(12, len(features) * 3)
    rolling = []
    residuals = []
    for value in sorted(seasons.dropna().unique()):
        season = int(value)
        if season >= frozen_season:
            continue
        fold_train = source.loc[seasons < season]
        role_train = fold_train.loc[fold_train[_POOL_ROLE_COLUMN].eq(role_key)]
        role_test = source.loc[
            seasons.eq(season)
            & source[_POOL_ROLE_COLUMN].eq(role_key)
            & source["evaluation_eligible"].fillna(False).astype(bool)
        ]
        if (
            len(fold_train) < family_minimum
            or len(role_train) < role_minimum
            or role_test.empty
        ):
            continue
        try:
            family_model = LinearPercentileModel(family_features).fit(
                fold_train,
                _POOL_TARGET,
                sample_weight=_training_weights(fold_train, _POOL_WEIGHT),
            )
            role_model = LinearPercentileModel(features).fit(
                role_train,
                _POOL_TARGET,
                sample_weight=_training_weights(role_train, _POOL_WEIGHT),
            )
        except ValueError:
            continue
        role_weight = role_blend_weight(
            effective_sample_size(_training_weights(role_train, _POOL_WEIGHT)),
            tau,
        )
        prediction = (
            role_weight * role_model.predict(role_test)
            + (1.0 - role_weight) * family_model.predict(role_test)
        )
        actual = pd.to_numeric(role_test[_POOL_TARGET], errors="coerce").to_numpy(
            float
        )
        rolling.append({"season": season, **_regression_metrics(actual, prediction)})
        for athlete_id, observed, estimate in zip(
            role_test["player_id"].astype(str), actual, prediction
        ):
            if np.isfinite(observed) and np.isfinite(estimate):
                residuals.append(
                    {
                        "athlete_id": athlete_id,
                        "season": season,
                        "absolute_residual": float(abs(observed - estimate)),
                    }
                )
    return {
        "rolling_origin": rolling,
        "prediction_interval": _conformal_interval(residuals),
    }


def _default_pooling_metadata(role_key: str) -> dict:
    declared = family_for_role(role_key)
    return {
        "version": POOLING_VERSION,
        "status": "role_only_retained" if declared else "not_applicable",
        "gate": "insufficient_frozen_evidence" if declared else "not_applicable",
        "reason": (
            "awaiting_family_evaluation"
            if declared
            else "role_not_in_a_predeclared_related_role_family"
        ),
        "family": declared[0] if declared else None,
        "family_role_keys": list(declared[1]) if declared else [],
        "active_role_keys": [],
        "selected_tau": None,
        "tau_selection": None,
        "effective_role_rows_prefreeze": 0.0,
        "role_weight_prefreeze": None,
        "family_weight_prefreeze": None,
        "frozen_n": 0,
        "frozen_role_only": _regression_metrics([], []),
        "frozen_partially_pooled": _regression_metrics([], []),
        "mae_advantage_vs_role_only": _empty_pooling_advantage(),
        "deployment_role_weight": 1.0,
        "deployment_family_weight": 0.0,
        "deployment_policy": (
            "deploy only when frozen eligible n >= 20 and the athlete-clustered 90% "
            "MAE-advantage interval has lower bound > 0"
        ),
    }


def _apply_native_profile_pooling(
    heads: dict[str, dict],
    pooling_inputs: dict[str, dict],
) -> None:
    """Replace only evidence-supported native-profile heads with a blend."""
    for role_key in pooling_inputs:
        heads[role_key]["selected_model_family"] = "role_only"
        heads[role_key]["partial_pooling"] = _default_pooling_metadata(role_key)

    for family, family_role_keys_value in ROLE_FAMILIES.items():
        family_role_keys = tuple(family_role_keys_value)
        active = [key for key in family_role_keys if key in pooling_inputs]
        if not active:
            continue
        assembled = _pooling_family_frame(pooling_inputs, family_role_keys)
        if assembled is None:
            reason = (
                "fewer_than_two_fit_related_roles"
                if len(active) < 2
                else "related_roles_do_not_share_one_feature_contract"
            )
            for role_key in active:
                heads[role_key]["partial_pooling"].update(
                    {"reason": reason, "active_role_keys": active}
                )
            continue
        family_frame, features = assembled
        tau_selection = _select_family_pooling_tau(
            family_frame,
            features=features,
            family_role_keys=family_role_keys,
        )
        selected_tau = tau_selection["selected_tau"]
        for role_key in active:
            metadata = heads[role_key]["partial_pooling"]
            metadata.update(
                {
                    "family": family,
                    "active_role_keys": active,
                    "selected_tau": selected_tau,
                    "tau_selection": tau_selection,
                }
            )
            if selected_tau is None:
                metadata["reason"] = "no_usable_prefreeze_rolling_origin_fold"
                continue
            comparison = _pooling_frozen_comparison(
                family_frame,
                role_key=role_key,
                features=features,
                family_role_keys=family_role_keys,
                tau=selected_tau,
            )
            gate = pooling_gate(comparison["n"], comparison["advantage"])
            prefreeze_role_weight = comparison["role_weight"]
            metadata.update(
                {
                    "gate": gate,
                    "reason": (
                        "frozen_mae_advantage_ci90_lower_bound_above_zero"
                        if gate == "supported"
                        else "frozen_evidence_did_not_clear_deployment_gate"
                    ),
                    "effective_role_rows_prefreeze": comparison[
                        "effective_role_rows"
                    ],
                    "role_weight_prefreeze": prefreeze_role_weight,
                    "family_weight_prefreeze": (
                        1.0 - prefreeze_role_weight
                        if prefreeze_role_weight is not None
                        else None
                    ),
                    "frozen_n": comparison["n"],
                    "frozen_role_only": comparison["role_only"],
                    "frozen_partially_pooled": comparison["partially_pooled"],
                    "mae_advantage_vs_role_only": comparison["advantage"],
                }
            )
            if gate != "supported" or selected_tau <= 0:
                continue
            family_features = (
                *features,
                *(role_dummy_name(key) for key in family_role_keys),
            )
            try:
                family_model = LinearPercentileModel(family_features).fit(
                    family_frame,
                    _POOL_TARGET,
                    sample_weight=_training_weights(family_frame, _POOL_WEIGHT),
                )
            except ValueError:
                metadata.update(
                    {
                        "gate": "insufficient_frozen_evidence",
                        "reason": "final_family_model_could_not_be_fit",
                    }
                )
                continue
            role_frame = _with_bmi(pooling_inputs[role_key]["frame"])
            deployment_effective_rows = effective_sample_size(
                _training_weights(role_frame, _POOL_WEIGHT)
            )
            deployment_role_weight = role_blend_weight(
                deployment_effective_rows, selected_tau
            )
            heads[role_key]["model"] = BlendedPercentileModel(
                role_model=heads[role_key]["model"],
                family_model=family_model,
                role_weight=deployment_role_weight,
                family=family,
                role_key=role_key,
                family_role_keys=family_role_keys,
                tau=selected_tau,
                effective_rows=deployment_effective_rows,
            )
            # Real comparisons carry the paired frozen arrays needed to
            # recalibrate the selected estimator's diagnostics.  Small unit
            # fixtures may intentionally return only the public summary.
            if "_actual" in comparison and "_prediction" in comparison:
                pooled_diagnostics = _pooling_rolling_diagnostics(
                    family_frame,
                    role_key=role_key,
                    features=features,
                    family_role_keys=family_role_keys,
                    tau=selected_tau,
                )
                interval = pooled_diagnostics["prediction_interval"]
                radius = interval.get("half_width")
                actual = comparison["_actual"]
                prediction = comparison["_prediction"]
                valid = np.isfinite(actual) & np.isfinite(prediction)
                if radius is not None and valid.any():
                    covered = np.abs(actual[valid] - prediction[valid]) <= radius
                    lower = np.maximum(0.0, prediction[valid] - radius)
                    upper = np.minimum(100.0, prediction[valid] + radius)
                    interval["frozen_empirical_coverage"] = float(covered.mean())
                    interval["frozen_evaluation_n"] = int(covered.size)
                    interval["frozen_mean_clipped_width"] = float(
                        np.mean(upper - lower)
                    )
                else:
                    interval["frozen_empirical_coverage"] = None
                    interval["frozen_evaluation_n"] = int(valid.sum())
                    interval["frozen_mean_clipped_width"] = None
                percentile = _percentile_diagnostics(actual, prediction)
                top_decile = percentile.pop("top_decile")
                heads[role_key]["prediction_interval"] = interval
                heads[role_key]["selected_model_evaluation"] = {
                    "model_family": "partially_pooled",
                    "frozen": comparison["partially_pooled"],
                    "rolling_origin": pooled_diagnostics["rolling_origin"],
                    "percentile_calibration": percentile,
                    "top_decile": top_decile,
                    "athlete_disjoint_note": (
                        "The saved athlete-disjoint diagnostic belongs to the role-only base; "
                        "the pooled estimator is selected only by pre-freeze rolling tau tuning "
                        "and the frozen role-only comparison."
                    ),
                }
            heads[role_key]["selected_model_family"] = "partially_pooled"
            metadata.update(
                {
                    "status": "deployed",
                    "deployment_role_weight": float(deployment_role_weight),
                    "deployment_family_weight": float(1.0 - deployment_role_weight),
                }
            )


def train_native_profile_models(
    scored: pd.DataFrame,
    *,
    specs: dict[str, RoleSpec] | None = None,
    pairs: pd.DataFrame | None = None,
) -> dict[str, dict]:
    """Backtest the build-plus-canonical-profile contract one season forward.

    Unlike the history-rich native forecast, this family deliberately uses
    only inputs that have a declared cross-sport meaning.  Its build-only and
    profile-only ablations show whether the canonical playing profile adds
    future signal inside the athlete's own sport before it is used as an
    analogy elsewhere.
    """
    available = role_specs() if specs is None else specs
    forecast_pairs = build_native_forecast_pairs(scored) if pairs is None else pairs
    heads: dict[str, dict] = {}
    pooling_inputs: dict[str, dict] = {}
    for key, spec in available.items():
        if not spec.domains:
            heads[key] = {"status": spec.evidence_status}
            continue
        dimensions = tuple(f"dimension_{name}_percentile" for name in _dimensions(spec))
        combined_features = (*PHYSICAL_FEATURES, *dimensions)
        candidates = forecast_pairs.loc[
            forecast_pairs["sport"].eq(spec.sport)
            & forecast_pairs["prior_role"].eq(spec.role)
        ].copy()
        same_role = candidates.loc[candidates["same_role_target"]].copy()
        eligible = same_role.loc[
            same_role["target_status"].eq("eligible")
            & same_role["realized_target_status"].eq("eligible")
            & _finite_target(same_role, "target_observed_role_percentile")
        ].copy()
        trainable = same_role.loc[
            same_role["target_status"].isin(["eligible", "low_sample"])
            & same_role["realized_target_status"].isin(["eligible", "low_sample"])
            & _finite_target(same_role, "target_observed_role_percentile")
        ].copy()
        trainable["evaluation_eligible"] = (
            trainable["target_status"].eq("eligible")
            & trainable["realized_target_status"].eq("eligible")
        )
        required_inputs = ("height_cm", "weight_kg", *dimensions)
        eligible_usable = eligible.loc[
            _complete_numeric_inputs(eligible, required_inputs)
        ].copy()
        eligible_usable["season"] = eligible_usable["target_season"]
        role_pairs = trainable.loc[
            _complete_numeric_inputs(trainable, required_inputs)
        ].copy()
        role_pairs["season"] = role_pairs["target_season"]
        coverage = _coverage_summary(
            candidates,
            eligible,
            eligible_usable,
            required_inputs=required_inputs,
            extra={
                "same_role_rows": int(len(same_role)),
                "excluded_role_transition_rows": int(len(candidates) - len(same_role)),
                "training_usable_rows": int(len(role_pairs)),
                "weighted_low_sample_rows": int(
                    (~role_pairs["evaluation_eligible"]).sum()
                ),
            },
        )
        try:
            head = _fit_with_evaluation(
                role_pairs,
                features=tuple(combined_features),
                target="target_observed_role_percentile",
                sample_weight_column="pair_training_sample_weight",
                evaluation_eligible_column="evaluation_eligible",
                diagnostic_player_ids=(
                    NBA_MODEL_FACE_CHECKS.get(spec.role)
                    if spec.sport == "nba"
                    else None
                ),
            )
            build_only = _fit_with_evaluation(
                role_pairs,
                features=PHYSICAL_FEATURES,
                target="target_observed_role_percentile",
                sample_weight_column="pair_training_sample_weight",
                evaluation_eligible_column="evaluation_eligible",
            )
            profile_only = _fit_with_evaluation(
                role_pairs,
                features=dimensions,
                target="target_observed_role_percentile",
                sample_weight_column="pair_training_sample_weight",
                evaluation_eligible_column="evaluation_eligible",
            )
        except ValueError as error:
            heads[key] = {
                "status": "not_fit",
                "reason": str(error),
                "usable_coverage": coverage,
            }
            continue

        advantage, build_metrics = _frozen_feature_advantage(
            role_pairs,
            full_features=tuple(combined_features),
            baseline_features=PHYSICAL_FEATURES,
            target="target_observed_role_percentile",
            time_column="target_season",
            sample_weight_column="pair_training_sample_weight",
            evaluation_eligible_column="evaluation_eligible",
        )
        ci_low = advantage["ci90"][0]
        increment_gate = (
            "supported"
            if head["evidence_gate"] == "supported" and ci_low is not None and ci_low > 0
            else "not_supported"
            if head["evaluation"]["frozen"]["n"] >= 20
            else "insufficient_frozen_evidence"
        )
        head["profile_increment_gate"] = increment_gate
        head["deployment_support"] = (
            "supported_profile_increment"
            if increment_gate == "supported"
            else "experimental_unsupported"
        )
        head["evaluation"]["mae_advantage_vs_build_only"] = advantage
        head["evaluation"]["build_only"] = build_metrics
        head["ablations"] = {
            "build_only": {
                "features": build_only["features"],
                "status": build_only["status"],
                "evidence_gate": build_only["evidence_gate"],
                "evaluation": build_only["evaluation"],
            },
            "canonical_profile_only": {
                "features": profile_only["features"],
                "status": profile_only["status"],
                "evidence_gate": profile_only["evidence_gate"],
                "evaluation": profile_only["evaluation"],
            },
        }
        head["usable_coverage"] = coverage
        head["dimensions"] = list(_dimensions(spec))
        head["evidence_class"] = "native_forward_transferable_profile_benchmark"
        head["training_label_policy"] = (
            "same-role consecutive seasons; low-sample pairs are reliability-weighted for "
            "training and frozen evaluation remains eligible-only"
        )
        heads[key] = head
        pooling_inputs[key] = {
            "frame": role_pairs.copy(),
            "features": tuple(combined_features),
        }
    _apply_native_profile_pooling(heads, pooling_inputs)
    return heads


def train_bridge_models(
    scored: pd.DataFrame,
    *,
    specs: dict[str, RoleSpec] | None = None,
) -> dict[str, dict]:
    """Fit fixed source-role -> target-role analogy heads.

    Each bridge uses only the predeclared performance-dimension intersection.
    The exact feature contract is tested by asking whether a target athlete's
    prior-season build plus canonical profile predicts their next target-role
    season better than build alone.  Applying source-sport percentiles remains
    an unvalidated cross-sport analogy.
    """
    available = role_specs() if specs is None else specs
    pairs = build_native_forecast_pairs(scored)
    bridges: dict[str, dict] = {}
    for source_key, source_spec in available.items():
        if not source_spec.domains:
            continue
        for target_key, target_spec in available.items():
            if source_spec.sport == target_spec.sport or not target_spec.domains:
                continue
            shared = tuple(sorted(set(_dimensions(source_spec)) & set(_dimensions(target_spec))))
            bridge_key = f"{source_key}->{target_key}"
            if len(shared) < 2:
                bridges[bridge_key] = {
                    "status": "withheld_insufficient_semantic_intersection",
                    "dimensions": list(shared),
                    "minimum_dimensions": 2,
                }
                continue
            features = (*PHYSICAL_FEATURES, *(f"dimension_{name}_percentile" for name in shared))
            candidates = pairs.loc[
                pairs["sport"].eq(target_spec.sport)
                & pairs["prior_role"].eq(target_spec.role)
            ].copy()
            same_role = candidates.loc[candidates["same_role_target"]].copy()
            eligible = same_role.loc[
                same_role["target_status"].eq("eligible")
                & same_role["realized_target_status"].eq("eligible")
                & _finite_target(same_role, "target_observed_role_percentile")
            ].copy()
            trainable = same_role.loc[
                same_role["target_status"].isin(["eligible", "low_sample"])
                & same_role["realized_target_status"].isin(["eligible", "low_sample"])
                & _finite_target(same_role, "target_observed_role_percentile")
            ].copy()
            trainable["evaluation_eligible"] = (
                trainable["target_status"].eq("eligible")
                & trainable["realized_target_status"].eq("eligible")
            )
            required_inputs = (
                "height_cm",
                "weight_kg",
                *(f"dimension_{name}_percentile" for name in shared),
            )
            eligible_usable = eligible.loc[
                _complete_numeric_inputs(eligible, required_inputs)
            ].copy()
            eligible_usable["season"] = eligible_usable["target_season"]
            target_frame = trainable.loc[
                _complete_numeric_inputs(trainable, required_inputs)
            ].copy()
            target_frame["season"] = target_frame["target_season"]
            coverage = _coverage_summary(
                candidates,
                eligible,
                eligible_usable,
                required_inputs=required_inputs,
                extra={
                    "same_role_rows": int(len(same_role)),
                    "excluded_role_transition_rows": int(len(candidates) - len(same_role)),
                    "training_usable_rows": int(len(target_frame)),
                    "weighted_low_sample_rows": int(
                        (~target_frame["evaluation_eligible"]).sum()
                    ),
                },
            )
            try:
                head = _fit_with_evaluation(
                    target_frame,
                    features=tuple(features),
                    target="target_observed_role_percentile",
                    sample_weight_column="pair_training_sample_weight",
                    evaluation_eligible_column="evaluation_eligible",
                )
            except ValueError as error:
                bridges[bridge_key] = {
                    "status": "not_fit",
                    "dimensions": list(shared),
                    "reason": str(error),
                    "usable_coverage": coverage,
                }
                continue
            advantage, build_metrics = _frozen_feature_advantage(
                target_frame,
                full_features=tuple(features),
                baseline_features=PHYSICAL_FEATURES,
                target="target_observed_role_percentile",
                time_column="target_season",
                sample_weight_column="pair_training_sample_weight",
                evaluation_eligible_column="evaluation_eligible",
            )
            ci_low = advantage["ci90"][0]
            forward_gate = (
                "supported"
                if head["evidence_gate"] == "supported" and ci_low is not None and ci_low > 0
                else "not_supported"
                if head["evaluation"]["frozen"]["n"] >= 20
                else "insufficient_frozen_evidence"
            )
            head["evaluation"]["mae_advantage_vs_build_only"] = advantage
            head["evaluation"]["build_only"] = build_metrics
            head["target_role_forward_profile_gate"] = forward_gate
            # Compatibility aliases retained for the existing scorer.  Their
            # values now represent the stricter forward, incremental gate.
            head["target_proxy_reconstruction_gate"] = forward_gate
            head["target_proxy_reconstruction_status"] = head.pop("status")
            head.pop("evidence_gate", None)
            head["target_proxy_residual_mae"] = head.pop("frozen_residual_mae")
            head["dimensions"] = list(shared)
            head["source_role"] = source_key
            head["target_role"] = target_key
            head["semantic_bridge_grade"] = "moderate" if len(shared) >= 3 else "limited"
            head["evidence_class"] = "unvalidated_cross_sport_analogy"
            head["evaluation_scope"] = (
                "Forward validation inside the target role: prior-season build plus the exact "
                "shared canonical profile must improve on build alone. This is still not "
                "cross-sport validation."
            )
            head["usable_coverage"] = coverage
            head["training_label_policy"] = (
                "same-role consecutive target-sport seasons; low-sample pairs are reliability-"
                "weighted for training and frozen evaluation remains eligible-only"
            )
            bridges[bridge_key] = head
    return bridges


def train_all_role_models(
    scored: pd.DataFrame,
    *,
    specs: dict[str, RoleSpec] | None = None,
) -> tuple[dict, pd.DataFrame]:
    available = role_specs() if specs is None else specs
    physical = train_physical_models(scored, specs=available)
    native, pairs = train_native_forecast_models(scored, specs=available)
    native_profile = train_native_profile_models(scored, specs=available, pairs=pairs)
    bridges = train_bridge_models(scored, specs=available)
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "role_taxonomy_version": ROLE_TAXONOMY_VERSION,
        "target_version": TARGET_VERSION,
        "bridge_version": BRIDGE_VERSION,
        "frozen_test_season": FROZEN_TEST_SEASON,
        "physical_models": physical,
        "native_forecast_models": native,
        "native_profile_models": native_profile,
        "bridge_models": bridges,
        "claims": {
            "observed": "descriptive role-season percentile",
            "native_forecast": "next-season estimate from prior information",
            "native_profile": (
                "next-season benchmark using only build and canonical cross-sport dimensions; "
                "promotion requires incremental evidence over build alone"
            ),
            "physical": "performance association from build; not causal",
            "bridge": "exploratory analogy; not a sport-switch probability or validated outcome forecast",
            "bridge_target_proxy_reconstruction_gate": (
                "Compatibility name for a forward target-role test: prior build plus shared "
                "canonical dimensions must improve on build alone; it is not cross-sport validation."
            ),
            "training_cohort": (
                "Eligible and positive-opportunity low-sample labels may train with empirical "
                "opportunity/coverage weights. Frozen evaluation remains eligible-only, and rows "
                "must satisfy the deployed build and fixed-dimension requirements."
            ),
            "athlete_disjoint_diagnostic": (
                "A separate pre-freeze player-group diagnostic measures generalization to unseen "
                "identities. It is non-temporal and does not replace or change the frozen-season "
                "evidence gate."
            ),
            "percentile_validation": (
                "Frozen predictions receive fixed-bin percentile calibration and threshold plus "
                "cohort-ranked top-decile diagnostics; these are reported, not used to tune gates."
            ),
            "prediction_uncertainty": (
                "Nominal 90% prediction ranges use rolling-origin absolute residuals with one "
                "latest residual per athlete and a finite-sample conformal order statistic. "
                "Frozen empirical coverage is reported and cross-sport distribution shift can "
                "invalidate nominal coverage."
            ),
            "team_context": (
                "Completed-season role opportunity share and leave-one-player-out teammate "
                "strength are tested only as next-season native-forecast candidates. The base "
                "role/history model remains deployed unless the candidate beats the base model, "
                "the best history baseline, and neutral on the frozen cohort with at least 20 "
                "eligible athletes having both context fields. Team identity and future-season "
                "context are never model inputs, and context never enters cross-sport bridges."
            ),
            "partial_pooling": (
                "Native build-plus-profile heads may borrow from predeclared related-role "
                "families. Shrinkage is tuned only in pre-2025 rolling folds and deployed only "
                "when the frozen athlete-clustered 90% MAE-advantage interval over role-only has "
                "a positive lower bound with at least 20 eligible athletes."
            ),
        },
    }
    return artifact, pairs
