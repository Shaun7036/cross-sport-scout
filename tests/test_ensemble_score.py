from __future__ import annotations

import numpy as np
import pytest

from possession_lab.ensemble_score import SCHEMA, score_ensemble
from possession_lab.ensemble_targets import HeadSpec


class ConstantModel:
    def __init__(self, value):
        self.value = value

    def predict(self, frame):
        return np.full(len(frame), self.value, dtype=float)


class ConstantArchetype(ConstantModel):
    def describe(self, frame):
        return [
            {
                "prediction": self.value,
                "nearest_archetype": 0,
                "probabilities": {"0": 1.0},
                "effective_support": 40.0,
            }
            for _ in range(len(frame))
        ]


def _head(
    role: str,
    values=(10.0, 20.0, 30.0, 40.0),
    *,
    status="evidence_supported",
    selected_method="stack",
    center=(180.0, 80.0),
    bounds=((160.0, 55.0), (220.0, 130.0)),
    radius=8.0,
):
    spec = HeadSpec("nba", role, 300, {})
    if status == "insufficient_support":
        return {
            "spec": spec,
            "summary": {
                "status": status,
                "train_athletes": 8,
                "calibration_athletes": 0,
                "test_athletes": 0,
                "evaluation": spec.evaluation,
                "metrics": {},
            },
        }
    names = ("archetype", "ridge", "hist_gradient_boosting", "extra_trees")
    experts = {
        name: ConstantArchetype(value) if name == "archetype" else ConstantModel(value)
        for name, value in zip(names, values)
    }
    return {
        "spec": spec,
        "experts": experts,
        "target": object(),
        "stack_weights": {
            "baseline50": 0.0,
            "archetype": 0.2,
            "ridge": 0.2,
            "hist_gradient_boosting": 0.2,
            "extra_trees": 0.2,
            "shared": 0.2,
        },
        "selected_method": selected_method,
        "shared_center": [180.0, 80.0],
        "shared_scale": [10.0, 10.0],
        "body_reference": {
            "center": list(center),
            "inverse_covariance": [[0.01, 0.0], [0.0, 0.01]],
            "distances": [0.0, 1.0, 4.0, 9.0],
            "lower": list(bounds[0]),
            "upper": list(bounds[1]),
        },
        "calibration_radius": radius,
        "summary": {
            "status": status,
            "train_athletes": 100,
            "calibration_athletes": 30,
            "test_athletes": 25,
            "evaluation": spec.evaluation,
            "metrics": {"stack_mae": np.float64(7.5)},
        },
    }


def _artifact(heads):
    return {
        "version": "test-v1",
        "features": ["height_cm", "weight_kg"],
        "shared_expert": ConstantModel(50.0),
        "heads": heads,
    }


def test_scores_supported_roles_and_ranks_only_on_efficacy():
    # Forward has the less central body reference but the higher efficacy model;
    # physical fit must not be multiplied into the ranking.
    guard = _head("guard", values=(10, 20, 30, 40))
    forward = _head("forward", values=(70, 80, 90, 100), center=(195, 95))
    result = score_ensemble(
        _artifact({"nba:guard": guard, "nba:forward": forward}),
        {"height_inches": 180 / 2.54, "weight_lb": 80 / 0.45359237, "age": 24},
    )

    assert result["schema"] == SCHEMA
    assert result["version"] == "test-v1"
    assert result["features_used"] == pytest.approx({"height_cm": 180, "weight_kg": 80})
    assert result["features_unused"]["age"]["value"] == 24
    assert "not a probability" in result["interpretation"]
    nba = result["sports"]["nba"]
    assert nba["best_role"] == "forward"
    assert nba["efficacy_rating"] == pytest.approx(78.0)
    roles = {row["role"]: row for row in nba["roles"]}
    assert roles["guard"]["efficacy_rating"] == pytest.approx(30.0)
    assert roles["guard"]["interval"] == pytest.approx([22.0, 38.0])
    assert roles["guard"]["physical_fit"] == pytest.approx(75.0)
    assert roles["guard"]["archetype"]["nearest_archetype"] == 0
    assert roles["forward"]["physical_fit"] < roles["guard"]["physical_fit"]
    assert any("Age was recorded" in warning for warning in result["warnings"])


def test_out_of_domain_withholds_primary_but_keeps_experimental_interval():
    result = score_ensemble(
        _artifact({"nba:guard": _head("guard", radius=float("inf"))}),
        {"height_cm": 225.0, "weight_kg": 145.0},
        sport="nba",
    )
    nba = result["sports"]["nba"]
    role = nba["roles"][0]
    assert nba["best_role"] is None
    assert nba["efficacy_rating"] is None
    assert role["efficacy_rating"] is None
    assert role["experimental_estimate"] == pytest.approx(30.0)
    assert role["interval"] == [0.0, 100.0]
    assert role["interval_is_unbounded"] is True
    assert role["out_of_domain"] is True
    assert role["outside_training_bounds"] is True
    assert role["physical_fit"] == 0.0
    assert "out-of-domain" in role["score_label"]
    assert any("unsupported extrapolation" in warning for warning in result["warnings"])


def test_no_evidence_and_insufficient_support_are_not_promoted():
    no_evidence = _head("guard", status="no_evidence", selected_method="baseline", radius=50)
    skipped = _head("center", status="insufficient_support")
    result = score_ensemble(
        _artifact({"nba:guard": no_evidence, "nba:center": skipped}),
        {"height_cm": 180, "weight_kg": 80, "top_speed_kmh": 30},
    )
    roles = {row["role"]: row for row in result["sports"]["nba"]["roles"]}
    assert roles["guard"]["efficacy_rating"] is None
    assert roles["guard"]["experimental_estimate"] == 50.0
    assert roles["guard"]["interval"] == [0.0, 100.0]
    assert roles["guard"]["selected_method"] == "baseline"
    assert roles["center"]["experimental_estimate"] is None
    assert roles["center"]["archetype"] is None
    assert roles["center"]["evidence"]["train_athletes"] == 8
    assert result["features_unused"]["top_speed_kmh"]["value"] == 30.0


def test_profile_and_artifact_contracts_are_validated():
    artifact = _artifact({"nba:guard": _head("guard")})
    with pytest.raises(ValueError, match="height is required"):
        score_ensemble(artifact, {"weight_kg": 80})
    with pytest.raises(ValueError, match="Unknown or unavailable sport"):
        score_ensemble(artifact, {"height_cm": 180, "weight_kg": 80}, sport="nhl")
    with pytest.raises(ValueError, match="v1 feature contract"):
        score_ensemble(
            {**artifact, "features": ["height_cm", "weight_kg", "age"]},
            {"height_cm": 180, "weight_kg": 80},
        )


def test_components_are_clipped_before_stacking_and_fast_fit_is_disclosed():
    head = _head("guard", values=(-100.0, 200.0, 30.0, 40.0))
    artifact = {**_artifact({"nba:guard": head}), "fast_development_fit": True}
    result = score_ensemble(artifact, {"height_cm": 180, "weight_kg": 80})
    role = result["sports"]["nba"]["roles"][0]
    # Mean of clipped components 0, 100, 30, 40, and shared 50.
    assert role["experimental_estimate"] == pytest.approx(44.0)
    assert role["expert_predictions"]["archetype"] == 0.0
    assert role["expert_predictions"]["ridge"] == 100.0
    assert any("fast development fit" in warning for warning in result["warnings"])


def test_provisional_support_and_undercoverage_are_explicit():
    head = _head("guard")
    head["summary"].update(
        {
            "mse_improvement_cluster_bootstrap": {"lower95": -0.1, "upper95": 0.2},
            "improvement_statistically_established": False,
        }
    )
    head["summary"]["metrics"]["interval_90_empirical_coverage"] = 0.52
    result = score_ensemble(_artifact({"nba:guard": head}), {"height_cm": 180, "weight_kg": 80})
    role = result["sports"]["nba"]["roles"][0]
    assert "provisional" in role["score_label"]
    assert role["evidence"]["improvement_statistically_established"] is False
    assert any("includes zero" in warning for warning in result["warnings"])
    assert any("52.0%" in warning and "poorly calibrated" in warning for warning in result["warnings"])
