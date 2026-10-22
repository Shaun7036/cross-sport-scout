import numpy as np
import pandas as pd

from possession_lab.all_roles_models import LinearPercentileModel
from possession_lab.all_roles_score import score_all_roles_profile


def _head(features, frame):
    model = LinearPercentileModel(tuple(features)).fit(frame, "target")
    return {
        "model": model,
        "features": list(features),
        "status": "beats_neutral_baseline",
        "evidence_gate": "supported",
        "reference": {
            feature: {
                "median": float(frame[feature].median()),
                "iqr": float(frame[feature].quantile(.75) - frame[feature].quantile(.25)),
                "p01": float(frame[feature].min() - 5),
                "p99": float(frame[feature].max() + 5),
            }
            for feature in features
        },
        "frozen_residual_mae": 8.0,
        "dimensions": ["scoring_finishing", "creation_distribution"],
        "semantic_bridge_grade": "limited",
    }


def test_score_contract_keeps_observed_physical_and_transfer_separate():
    count = 40
    training = pd.DataFrame(
        {
            "height_cm": range(165, 165 + count),
            "weight_kg": range(65, 65 + count),
            "bmi": [24.5] * count,
            "age": [20 + value % 20 for value in range(count)],
            "dimension_scoring_finishing_percentile": np.linspace(10, 90, count),
            "dimension_creation_distribution_percentile": np.linspace(15, 95, count),
            "observed_role_percentile": np.linspace(10, 90, count),
            "availability_percentile": [60] * count,
            "sustained_3y_percentile": np.linspace(10, 90, count),
            "target": np.linspace(10, 90, count),
        }
    )
    physical_features = ["height_cm", "weight_kg", "bmi", "age"]
    bridge_features = physical_features + [
        "dimension_scoring_finishing_percentile",
        "dimension_creation_distribution_percentile",
    ]
    native_features = physical_features + [
        "observed_role_percentile",
        "availability_percentile",
        "sustained_3y_percentile",
        "dimension_scoring_finishing_percentile",
        "dimension_creation_distribution_percentile",
    ]
    physical_head = _head(physical_features, training)
    native_head = _head(native_features, training)
    native_head["forecast_support"] = "supported_over_history_baselines"
    native_profile_head = _head(bridge_features, training)
    native_profile_head["profile_increment_gate"] = "supported"
    bridge_head = _head(bridge_features, training)
    bridge_head["target_proxy_reconstruction_gate"] = bridge_head.pop("evidence_gate")
    bridge_head["target_proxy_residual_mae"] = bridge_head.pop("frozen_residual_mae")
    artifact = {
        "bridge_version": "fixture",
        "claims": {},
        "physical_models": {"nba:guard": physical_head},
        "native_forecast_models": {"nfl:QB": native_head},
        "native_profile_models": {"nfl:QB": native_profile_head},
        "bridge_models": {"nfl:QB->nba:guard": bridge_head},
    }
    profile = training.iloc[10].to_dict()
    profile.update(
        {
            "sport": "nfl",
            "role": "QB",
            "player_id": "p",
            "name": "Player",
            "season": 2025,
            "target_status": "eligible",
            "quality_percentile": 55,
            "total_impact_percentile": 58,
            "reference_athletes": 100,
        }
    )
    result = score_all_roles_profile(artifact, profile, target_sport="nba")
    assert result["native"]["observed"]["kind"] == "observed_role_percentile"
    assert result["native"]["forecast"]["kind"] == "native_forecast_percentile"
    assert (
        result["native"]["build_profile_forecast"]["kind"]
        == "native_build_profile_forecast_percentile"
    )
    assert (
        result["native"]["build_profile_forecast"]["support_status"]
        == "supported_profile_increment"
    )
    guard = result["targets"]["nba"]["roles"]["guard"]
    assert guard["physical_only"]["kind"] == "cross_sport_physical_estimate"
    assert guard["transfer_guesstimate"]["kind"] == "cross_sport_transfer_guesstimate"
    assert guard["physical_only"]["sensitivity_basis"] == "physical_model_frozen_test_mae"
    assert "physical model's frozen-test MAE" in guard["physical_only"]["range_warning"]
    assert guard["transfer_guesstimate"]["value"] is not None
    assert "analogy_sensitivity_range" in guard["transfer_guesstimate"]
    assert (
        guard["transfer_guesstimate"]["sensitivity_basis"]
        == "target_role_forward_profile_frozen_test_mae"
    )
    assert "forward-profile frozen-test MAE" in guard["transfer_guesstimate"]["range_warning"]
    assert (
        guard["transfer_guesstimate"]["support_status"]
        == "experimental_forward_profile_passed_not_cross_sport_validated"
    )
    assert guard["transfer_guesstimate"]["target_role_forward_profile_gate"] == "supported"
    assert "evidence_gate" not in guard["transfer_guesstimate"]


def _fixture_artifact(
    *,
    physical_gate="supported",
    native_gate="supported",
    forecast_support="supported_over_history_baselines",
):
    count = 40
    training = pd.DataFrame(
        {
            "height_cm": range(165, 165 + count),
            "weight_kg": range(65, 65 + count),
            "bmi": [24.5] * count,
            "age": [20 + value % 20 for value in range(count)],
            "dimension_scoring_finishing_percentile": np.linspace(10, 90, count),
            "dimension_creation_distribution_percentile": np.linspace(15, 95, count),
            "observed_role_percentile": np.linspace(10, 90, count),
            "availability_percentile": [60] * count,
            "sustained_3y_percentile": np.linspace(10, 90, count),
            "target": np.linspace(10, 90, count),
        }
    )
    physical_features = ["height_cm", "weight_kg", "bmi", "age"]
    bridge_features = physical_features + [
        "dimension_scoring_finishing_percentile",
        "dimension_creation_distribution_percentile",
    ]
    native_features = physical_features + [
        "observed_role_percentile",
        "availability_percentile",
        "sustained_3y_percentile",
        "dimension_scoring_finishing_percentile",
        "dimension_creation_distribution_percentile",
    ]
    physical = _head(physical_features, training)
    physical["evidence_gate"] = physical_gate
    native = _head(native_features, training)
    native["evidence_gate"] = native_gate
    native["forecast_support"] = forecast_support
    native_profile = _head(bridge_features, training)
    native_profile["profile_increment_gate"] = "supported"
    bridge = _head(bridge_features, training)
    bridge["target_proxy_reconstruction_gate"] = bridge.pop("evidence_gate")
    bridge["target_proxy_residual_mae"] = bridge.pop("frozen_residual_mae")
    artifact = {
        "bridge_version": "fixture",
        "claims": {},
        "physical_models": {"nba:guard": physical},
        "native_forecast_models": {"nfl:QB": native},
        "native_profile_models": {"nfl:QB": native_profile},
        "bridge_models": {"nfl:QB->nba:guard": bridge},
    }
    profile = training.iloc[10].to_dict()
    profile.update(
        {
            "sport": "nfl",
            "role": "QB",
            "player_id": "p",
            "name": "Player",
            "season": 2025,
            "target_status": "eligible",
            "quality_percentile": 55,
            "total_impact_percentile": 58,
            "reference_athletes": 100,
        }
    )
    return artifact, profile


def test_unsupported_physical_and_native_estimates_are_explicitly_experimental():
    artifact, profile = _fixture_artifact(
        physical_gate="not_supported",
        forecast_support="history_baseline_preferred_or_insufficient",
    )

    result = score_all_roles_profile(artifact, profile, target_sport="nba")
    physical = result["targets"]["nba"]["roles"]["guard"]["physical_only"]
    native = result["native"]["forecast"]

    assert physical["value"] is not None
    assert physical["support_status"] == "experimental_unsupported"
    assert physical["evidence_class"] == "experimental_unsupported_physical_association"
    assert native["value"] is not None
    assert native["support_status"] == "experimental_unsupported"
    assert native["evidence_class"] == "experimental_unsupported_native_forecast"


def test_native_forecast_requires_both_neutral_and_history_support():
    artifact, profile = _fixture_artifact(
        native_gate="not_supported",
        forecast_support="supported_over_history_baselines",
    )

    native = score_all_roles_profile(artifact, profile, target_sport="nba")["native"]["forecast"]

    assert native["value"] is not None
    assert native["support_status"] == "experimental_unsupported"
    assert native["deployment_support"] == "experimental_unsupported"
    assert "both" in native["evidence_warning"]


def test_low_sample_source_keeps_observed_but_withholds_forecasts_and_transfer():
    artifact, profile = _fixture_artifact()
    profile["target_status"] = "low_sample"

    result = score_all_roles_profile(artifact, profile, target_sport="nba")
    guard = result["targets"]["nba"]["roles"]["guard"]

    assert result["native"]["observed"]["status"] == "low_sample"
    assert result["native"]["observed"]["value"] is not None
    assert result["native"]["forecast"]["status"] == "withheld_source_performance_not_eligible"
    assert (
        result["native"]["build_profile_forecast"]["status"]
        == "withheld_source_performance_not_eligible"
    )
    assert guard["transfer_guesstimate"]["status"] == "withheld_source_performance_not_eligible"
    assert guard["physical_only"]["value"] is not None


def test_native_build_profile_forecast_requires_increment_over_build_only():
    artifact, profile = _fixture_artifact()
    profile_head = artifact["native_profile_models"]["nfl:QB"]
    profile_head["profile_increment_gate"] = "not_supported"

    result = score_all_roles_profile(artifact, profile, target_sport="nba")
    forecast = result["native"]["build_profile_forecast"]

    assert forecast["value"] is not None
    assert forecast["support_status"] == "experimental_unsupported"
    assert forecast["profile_increment_gate"] == "not_supported"
    assert "build-only" in forecast["evidence_warning"]


def test_failed_target_role_forward_profile_gate_is_named_and_withheld():
    artifact, profile = _fixture_artifact()
    bridge = artifact["bridge_models"]["nfl:QB->nba:guard"]
    bridge["target_proxy_reconstruction_gate"] = "not_supported"

    result = score_all_roles_profile(artifact, profile, target_sport="nba")
    transfer = result["targets"]["nba"]["roles"]["guard"]["transfer_guesstimate"]

    assert transfer["value"] is None
    assert transfer["status"] == "withheld_target_role_forward_profile_failed_gate"
    assert transfer["target_role_forward_profile_gate"] == "not_supported"
    assert transfer["target_proxy_reconstruction_gate"] == "not_supported"
    assert "evidence_gate" not in transfer


def test_saturated_model_output_has_boundary_warning():
    artifact, profile = _fixture_artifact()
    physical = artifact["physical_models"]["nba:guard"]
    physical["model"].coefficients = np.zeros_like(physical["model"].coefficients)
    physical["model"].intercept = 100.0

    result = score_all_roles_profile(artifact, profile, target_sport="nba")
    score = result["targets"]["nba"]["roles"]["guard"]["physical_only"]

    assert score["value"] == 100.0
    assert "saturation_warning" in score
