from __future__ import annotations

import math

import numpy as np
import pytest

from possession_lab.ensemble_evaluation import (
    bootstrap_improvement,
    evaluate_predictions,
    finite_conformal_radius,
    fit_simplex_weights,
    inverse_career_weights,
)


def test_inverse_career_weights_are_normalized_and_athlete_balanced() -> None:
    groups = np.array(["long", "long", "long", "short"], dtype=object)
    weights = inverse_career_weights(groups)
    assert weights.mean() == pytest.approx(1.0)
    assert weights[:3].sum() == pytest.approx(weights[3])
    assert weights.tolist() == pytest.approx([2 / 3, 2 / 3, 2 / 3, 2.0])


def test_evaluation_errors_give_each_athlete_equal_total_influence() -> None:
    result = evaluate_predictions(
        y=[0.0, 0.0, 100.0],
        pred=[10.0, 20.0, 50.0],
        groups=["a", "a", "b"],
    )
    assert result["n_rows"] == 3
    assert result["n_athletes"] == 2
    assert result["mae"] == pytest.approx((15.0 + 50.0) / 2)
    assert result["rmse"] == pytest.approx(math.sqrt((250.0 + 2500.0) / 2))
    assert result["baseline_mae"] == pytest.approx(50.0)
    assert result["baseline_rmse"] == pytest.approx(50.0)
    assert result["relative_mse_improvement"] == pytest.approx(0.45)


def test_constant_inputs_never_leak_nan_metrics() -> None:
    result = evaluate_predictions(
        y=[50.0, 50.0, 50.0, 50.0],
        pred=[50.0, 50.0, 50.0, 50.0],
        groups=["a", "b", "c", "d"],
    )
    assert result["r2"] is None
    assert result["spearman"] is None
    assert result["relative_mse_improvement"] is None
    assert result["top_quartile_ap"] is None
    assert result["precision_at_top_quartile"] is None
    assert result["top_quartile_base_rate"] == pytest.approx(1.0)
    for value in result.values():
        assert not isinstance(value, float) or not math.isnan(value)


def test_cluster_bootstrap_is_deterministic_and_finite() -> None:
    arguments = {
        "y": [0.0, 0.0, 100.0, 75.0],
        "pred": [10.0, 20.0, 50.0, 75.0],
        "groups": ["a", "a", "b", "c"],
        "replicates": 500,
        "seed": 9,
    }
    first = bootstrap_improvement(**arguments)
    second = bootstrap_improvement(**arguments)
    assert first == second
    assert first["lower95"] <= first["mean"] <= first["upper95"]
    assert all(value is None or np.isfinite(value) for value in first.values())


def test_finite_conformal_radius_uses_exact_finite_sample_order_statistic() -> None:
    residuals = [1.0, -2.0, 3.0, -4.0, 5.0, np.nan, np.inf]
    # ceil((5 + 1) * .8) = 5, so this is the fifth absolute residual.
    assert finite_conformal_radius(residuals, coverage=0.8) == pytest.approx(5.0)
    # ceil((5 + 1) * .9) = 6, beyond the five finite calibration points.
    assert math.isinf(finite_conformal_radius(residuals, coverage=0.9))
    assert math.isinf(finite_conformal_radius([], coverage=0.9))


def test_simplex_fit_prefers_the_accurate_expert_and_baseline_on_a_tie() -> None:
    target = np.array([10.0, 30.0, 70.0, 90.0])
    matrix = np.column_stack([np.full(4, 50.0), target, 100.0 - target])
    fitted = fit_simplex_weights(matrix, target)
    assert fitted.sum() == pytest.approx(1.0)
    assert (fitted >= 0).all()
    assert fitted[1] > 0.999

    tied = fit_simplex_weights(np.column_stack([target, target, target]), target)
    assert tied.tolist() == pytest.approx([1.0, 0.0, 0.0], abs=1e-8)


def test_simplex_fit_handles_collinear_boundary_case_without_linesearch_failure() -> None:
    # This compact fixture made an unscaled SLSQP solve terminate with status 8
    # ("Positive directional derivative for linesearch") from the baseline
    # vertex.  It also mirrors real stack inputs: a constant baseline, two
    # exactly collinear experts, clipped 0--100 predictions, and uneven row
    # weights.
    target = np.array([100.0, 0.0, 60.45247117, 35.80575985, 38.6837677])
    matrix = np.array(
        [
            [50.0, 66.0527722, 77.55033586, 77.55033586, 58.8326163, 55.58425567],
            [50.0, 0.0, 0.0, 0.0, 0.0, 4.56773996],
            [50.0, 38.66727662, 47.08185905, 47.08185905, 56.20472063, 42.55389724],
            [50.0, 85.03516168, 100.0, 100.0, 94.21860828, 80.60148747],
            [50.0, 45.97016754, 47.53745928, 47.53745928, 43.20504604, 43.47094815],
        ]
    )
    row_weight = np.array([0.02703783, 0.24712105, 0.00044915, 0.09190047, 0.6334915])
    fitted = fit_simplex_weights(matrix, target, row_weight)
    assert np.isfinite(fitted).all()
    assert fitted.sum() == pytest.approx(1.0, abs=1e-12)
    assert (fitted >= 0).all()
    fitted_loss = np.average((matrix @ fitted - target) ** 2, weights=row_weight)
    baseline_loss = np.average((matrix[:, 0] - target) ** 2, weights=row_weight)
    assert fitted_loss < baseline_loss


def test_validation_rejects_nonfinite_model_inputs() -> None:
    with pytest.raises(ValueError, match="finite"):
        evaluate_predictions([1.0, np.nan], [1.0, 2.0], ["a", "b"])
    with pytest.raises(ValueError, match="finite"):
        fit_simplex_weights([[1.0], [np.inf]], [1.0, 2.0])
    with pytest.raises(ValueError, match="positive integer"):
        bootstrap_improvement([1.0], [1.0], ["a"], replicates=0)
