"""Leakage-safe evaluation utilities for the cross-sport ensemble.

The common efficacy target is on a 0--100 scale, so a constant prediction of
50 is the deliberately simple reference model.  Repeated player-seasons are
weighted so that every athlete contributes the same total mass.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import ceil

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import rankdata
from sklearn.metrics import average_precision_score

BASELINE_SCORE = 50.0
_SCORE_SCALE = 100.0
_SIMPLEX_RIDGE = 1e-8
_SIMPLEX_FEASIBILITY_TOLERANCE = 1e-7


def _one_dimensional(values: object, *, name: str, dtype: object = float) -> np.ndarray:
    array = np.asarray(values, dtype=dtype)
    if array.ndim == 2 and array.shape[1] == 1:
        array = array[:, 0]
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return array


def _group_codes(groups: object, *, expected_length: int | None = None) -> tuple[np.ndarray, int]:
    values = _one_dimensional(groups, name="groups", dtype=object)
    if expected_length is not None and len(values) != expected_length:
        raise ValueError("groups must have the same number of rows as y")
    if not len(values):
        raise ValueError("groups must contain at least one athlete")
    if np.asarray(pd.isna(values), dtype=bool).any():
        raise ValueError("groups must not contain missing athlete identifiers")
    try:
        codes, uniques = pd.factorize(values, sort=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("groups must contain hashable athlete identifiers") from exc
    if (codes < 0).any():
        raise ValueError("groups must not contain missing athlete identifiers")
    return codes.astype(int, copy=False), int(len(uniques))


def inverse_career_weights(groups: object) -> np.ndarray:
    """Return row weights with mean one and equal total weight per athlete."""
    codes, n_athletes = _group_codes(groups)
    counts = np.bincount(codes, minlength=n_athletes).astype(float)
    weights = 1.0 / counts[codes]
    weights *= len(weights) / weights.sum()
    if not np.isfinite(weights).all() or not np.isclose(weights.mean(), 1.0):
        raise RuntimeError("Could not construct finite normalized athlete weights")
    return weights


def _evaluation_inputs(
    y: object, predicted: object, groups: object
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    target = _one_dimensional(y, name="y")
    estimate = _one_dimensional(predicted, name="predicted")
    if not len(target):
        raise ValueError("y must contain at least one observation")
    if len(estimate) != len(target):
        raise ValueError("predicted must have the same number of rows as y")
    if not np.isfinite(target).all() or not np.isfinite(estimate).all():
        raise ValueError("y and predicted must contain only finite values")
    codes, n_athletes = _group_codes(groups, expected_length=len(target))
    weights = inverse_career_weights(groups)
    return target, estimate, codes, weights, n_athletes


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.dot(values, weights) / weights.sum())


def _weighted_correlation(left: np.ndarray, right: np.ndarray, weights: np.ndarray) -> float | None:
    left_centered = left - _weighted_mean(left, weights)
    right_centered = right - _weighted_mean(right, weights)
    left_variance = _weighted_mean(left_centered**2, weights)
    right_variance = _weighted_mean(right_centered**2, weights)
    if left_variance <= 1e-24 or right_variance <= 1e-24:
        return None
    value = _weighted_mean(left_centered * right_centered, weights) / np.sqrt(
        left_variance * right_variance
    )
    return float(np.clip(value, -1.0, 1.0)) if np.isfinite(value) else None


def _weighted_upper_quartile(values: np.ndarray, weights: np.ndarray) -> float:
    """Return a deterministic cutoff whose strictly higher mass is at most 25%."""
    order = np.argsort(values, kind="mergesort")
    ordered_values = values[order]
    cumulative = np.cumsum(weights[order])
    index = int(np.searchsorted(cumulative, 0.75 * cumulative[-1], side="right"))
    index = min(index, len(ordered_values) - 1)
    return float(ordered_values[index])


def _safe_number(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def evaluate_predictions(y: object, pred: object, groups: object) -> dict[str, int | float | None]:
    """Evaluate 0--100 efficacy predictions with equal total athlete influence.

    Error, rank, and retrieval metrics use inverse-career row weights.  The
    top-quartile labels and selections include all observations tied at their
    weighted quartile cutoffs.  Undefined constant-target quantities are
    represented by ``None`` rather than NaN.
    """
    target, estimate, _, weights, n_athletes = _evaluation_inputs(y, pred, groups)
    error = estimate - target
    absolute_error = np.abs(error)
    squared_error = error**2
    baseline_error = BASELINE_SCORE - target
    baseline_squared_error = baseline_error**2

    mae = _weighted_mean(absolute_error, weights)
    mse = _weighted_mean(squared_error, weights)
    baseline_mae = _weighted_mean(np.abs(baseline_error), weights)
    baseline_mse = _weighted_mean(baseline_squared_error, weights)

    target_centered = target - _weighted_mean(target, weights)
    target_variance = _weighted_mean(target_centered**2, weights)
    r2 = None if target_variance <= 1e-24 else _safe_number(1.0 - mse / target_variance)
    spearman = _weighted_correlation(rankdata(target), rankdata(estimate), weights)
    relative_improvement = None if baseline_mse <= 1e-24 else _safe_number(1.0 - mse / baseline_mse)

    target_cutoff = _weighted_upper_quartile(target, weights)
    positive = target >= target_cutoff
    base_rate = _weighted_mean(positive.astype(float), weights)
    if positive.all() or not positive.any():
        average_precision = None
    else:
        average_precision = _safe_number(
            average_precision_score(positive.astype(int), estimate, sample_weight=weights)
        )

    predicted_cutoff = _weighted_upper_quartile(estimate, weights)
    selected = estimate >= predicted_cutoff
    selected_weight = float(weights[selected].sum())
    precision = (
        _safe_number(float(weights[selected & positive].sum()) / selected_weight)
        if selected_weight > 0 and positive.any() and not positive.all()
        else None
    )

    return {
        "n_rows": int(len(target)),
        "n_athletes": n_athletes,
        "mae": mae,
        "rmse": float(np.sqrt(mse)),
        "r2": r2,
        "spearman": spearman,
        "baseline_mae": baseline_mae,
        "baseline_rmse": float(np.sqrt(baseline_mse)),
        "relative_mse_improvement": relative_improvement,
        "top_quartile_ap": average_precision,
        "top_quartile_base_rate": base_rate,
        "precision_at_top_quartile": precision,
    }


def bootstrap_improvement(
    y: object,
    pred: object,
    groups: object,
    replicates: int = 300,
    seed: int = 42,
) -> dict[str, float | None]:
    """Cluster-bootstrap relative MSE improvement over the constant-50 model.

    Whole athlete careers are resampled.  Taking the mean error within each
    sampled career preserves the same equal-athlete estimand as
    :func:`evaluate_predictions`.
    """
    if isinstance(replicates, bool) or not isinstance(replicates, (int, np.integer)):
        raise ValueError("replicates must be a positive integer")
    if replicates < 1:
        raise ValueError("replicates must be a positive integer")
    target, estimate, codes, _, n_athletes = _evaluation_inputs(y, pred, groups)
    group_counts = np.bincount(codes, minlength=n_athletes).astype(float)
    model_mse = np.bincount(codes, weights=(estimate - target) ** 2, minlength=n_athletes)
    baseline_mse = np.bincount(
        codes, weights=(BASELINE_SCORE - target) ** 2, minlength=n_athletes
    )
    model_mse /= group_counts
    baseline_mse /= group_counts

    generator = np.random.default_rng(seed)
    draws = generator.integers(0, n_athletes, size=(int(replicates), n_athletes))
    sampled_model = model_mse[draws].mean(axis=1)
    sampled_baseline = baseline_mse[draws].mean(axis=1)
    valid = sampled_baseline > 1e-24
    improvements = 1.0 - sampled_model[valid] / sampled_baseline[valid]
    improvements = improvements[np.isfinite(improvements)]
    if not len(improvements):
        return {"mean": None, "lower95": None, "upper95": None}
    lower, upper = np.quantile(improvements, [0.025, 0.975])
    return {
        "mean": float(improvements.mean()),
        "lower95": float(lower),
        "upper95": float(upper),
    }


def finite_conformal_radius(residuals: object, coverage: float = 0.9) -> float:
    """Return the split-conformal absolute-residual radius at finite-sample rank.

    Non-finite calibration residuals are excluded.  The radius is infinite
    when ``ceil((n + 1) * coverage)`` lies beyond the available calibration
    observations, which honestly signals insufficient calibration support.
    """
    if not np.isfinite(coverage) or not 0.0 < coverage < 1.0:
        raise ValueError("coverage must be finite and strictly between zero and one")
    values = _one_dimensional(residuals, name="residuals")
    values = np.abs(values[np.isfinite(values)])
    rank = ceil((len(values) + 1) * float(coverage))
    if not len(values) or rank > len(values):
        return float("inf")
    return float(np.partition(values, rank - 1)[rank - 1])


def fit_simplex_weights(
    matrix: object,
    y: object,
    sample_weight: Sequence[float] | np.ndarray | None = None,
) -> np.ndarray:
    """Fit deterministic non-negative ensemble weights constrained to sum to one."""
    predictions = np.asarray(matrix, dtype=float)
    if predictions.ndim != 2 or not predictions.shape[0] or not predictions.shape[1]:
        raise ValueError("matrix must be a non-empty two-dimensional array")
    target = _one_dimensional(y, name="y")
    if len(target) != len(predictions):
        raise ValueError("y must have the same number of rows as matrix")
    if not np.isfinite(predictions).all() or not np.isfinite(target).all():
        raise ValueError("matrix and y must contain only finite values")

    if sample_weight is None:
        weights = np.ones(len(target), dtype=float)
    else:
        weights = _one_dimensional(sample_weight, name="sample_weight")
        if len(weights) != len(target):
            raise ValueError("sample_weight must have the same number of rows as matrix")
        if not np.isfinite(weights).all() or (weights < 0).any() or weights.sum() <= 0:
            raise ValueError("sample_weight must be finite, non-negative, and have positive total weight")
    weights = weights / weights.sum()

    n_experts = predictions.shape[1]
    if n_experts == 1:
        return np.ones(1, dtype=float)
    # The target contract is a 0--100 score.  Optimizing on a unit-scale copy
    # prevents SLSQP's line search from being dominated by a large quadratic
    # gradient when the solution lies on a simplex boundary.  Returned weights
    # are invariant to this common scaling (apart from the deliberately tiny
    # tie-breaking ridge below).
    scaled_predictions = predictions / _SCORE_SCALE
    scaled_target = target / _SCORE_SCALE
    baseline = np.zeros(n_experts, dtype=float)
    baseline[0] = 1.0

    def objective(simplex: np.ndarray) -> float:
        error = scaled_predictions @ simplex - scaled_target
        return float(np.dot(weights, error**2) + _SIMPLEX_RIDGE * np.sum((simplex - baseline) ** 2))

    def gradient(simplex: np.ndarray) -> np.ndarray:
        error = scaled_predictions @ simplex - scaled_target
        return 2.0 * (scaled_predictions.T @ (weights * error)) + 2.0 * _SIMPLEX_RIDGE * (
            simplex - baseline
        )

    constraint = {
        "type": "eq",
        "fun": lambda value: float(value.sum() - 1.0),
        "jac": lambda _: np.ones(n_experts),
    }

    def solve(start: np.ndarray):
        return minimize(
            objective,
            start,
            jac=gradient,
            method="SLSQP",
            bounds=[(0.0, 1.0)] * n_experts,
            constraints=constraint,
            options={"ftol": 1e-12, "maxiter": 1000, "disp": False},
        )

    def feasible_candidate(result: object) -> np.ndarray | None:
        if not result.success:
            return None
        candidate = np.asarray(result.x, dtype=float)
        if candidate.shape != (n_experts,) or not np.isfinite(candidate).all():
            return None
        tolerance = _SIMPLEX_FEASIBILITY_TOLERANCE
        if (
            candidate.min() < -tolerance
            or candidate.max() > 1.0 + tolerance
            or abs(candidate.sum() - 1.0) > tolerance
            or not np.isfinite(objective(candidate))
        ):
            return None
        # Remove harmless solver-sized bound violations, then verify the
        # actually returned vector rather than trusting an optimizer flag.
        candidate = np.clip(candidate, 0.0, 1.0)
        candidate /= candidate.sum()
        if (
            not np.isfinite(candidate).all()
            or (candidate < 0).any()
            or (candidate > 1).any()
            or not np.isclose(candidate.sum(), 1.0, atol=1e-12, rtol=0.0)
        ):
            return None
        return candidate

    uniform = np.full(n_experts, 1.0 / n_experts)
    primary_starts = [baseline.copy(), uniform]
    attempts: list[object] = []
    candidates: list[tuple[float, int, np.ndarray]] = []
    for start in primary_starts:
        result = solve(start)
        attempts.append(result)
        candidate = feasible_candidate(result)
        if candidate is not None:
            candidates.append((objective(candidate), len(attempts), candidate))

    # Collinear experts can still make one line-search start unhelpful.  Retry
    # from every remaining simplex vertex only if both primary starts failed.
    if not candidates:
        for expert_index in range(1, n_experts):
            start = np.zeros(n_experts, dtype=float)
            start[expert_index] = 1.0
            result = solve(start)
            attempts.append(result)
            candidate = feasible_candidate(result)
            if candidate is not None:
                candidates.append((objective(candidate), len(attempts), candidate))

    if not candidates:
        diagnostics = "; ".join(
            f"status={result.status}: {result.message}" for result in attempts
        )
        raise RuntimeError(f"Simplex optimization failed from all deterministic starts: {diagnostics}")
    # SLSQP is solving a convex quadratic here.  Selecting the lowest verified
    # objective also makes the result stable if both deterministic starts land
    # within slightly different numerical tolerances of the same optimum.
    return min(candidates, key=lambda item: (item[0], item[1]))[2]
