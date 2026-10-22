"""Leakage-aware native forecasts and exploratory cross-sport role bridges."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import RidgeCV

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
        rolling.append(
            {
                "season": season,
                **_regression_metrics(fold_test[target], model.predict(fold_test)),
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
        },
        "evidence_gate": evidence_gate,
        "frozen_residual_mae": residual_mae,
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
        heads[key] = head
    return heads, pairs


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
        },
    }
    return artifact, pairs
