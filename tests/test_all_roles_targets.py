import numpy as np
import pandas as pd
import pytest

from possession_lab.all_roles_registry import (
    DomainSpec,
    MetricSpec,
    RoleSpec,
    registry_payload,
    role_specs,
)
from possession_lab.all_roles_targets import ObservedRoleTarget, add_sustained_index, score_observed_panel


def fixture_spec() -> RoleSpec:
    return RoleSpec(
        sport="test",
        role="role",
        label="Fixture role",
        min_opportunity=100,
        opportunity_unit="minutes",
        domains=(
            DomainSpec(
                name="positive",
                dimension="scoring_finishing",
                weight=0.7,
                metrics=(MetricSpec("good_rate", 1.0, True),),
            ),
            DomainSpec(
                name="negative",
                dimension="possession_security",
                weight=0.3,
                metrics=(MetricSpec("bad_rate", 1.0, False),),
            ),
        ),
    )


def fixture_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sport": "test",
            "player_id": list("abcdefg"),
            "name": [f"Player {letter}" for letter in "abcdefg"],
            "season": 2025,
            "role": "role",
            "position": "X",
            "team": "T",
            "games": 10,
            "opportunity": [100, 150, 200, 250, 300, 50, 0],
            "good_rate": [1, 2, 3, 4, 5, 100, 100],
            "bad_rate": [5, 4, 3, 2, 1, 0, 0],
            "height_cm": 190.0,
            "weight_kg": 90.0,
            "age": 25.0,
        }
    )


def test_observed_target_respects_metric_direction_and_status():
    frame = fixture_frame()
    target = ObservedRoleTarget(fixture_spec()).fit(frame)
    result = target.transform(frame)
    assert result.loc[4, "observed_role_percentile"] > result.loc[0, "observed_role_percentile"]
    assert result.loc[5, "target_status"] == "low_sample"
    assert result.loc[6, "target_status"] == "not_observed"
    assert np.isnan(result.loc[6, "observed_role_percentile"])
    assert result.loc[4, "dimension_scoring_finishing_percentile"] > 50
    assert result.loc[4, "opportunity_reliability"] > result.loc[5, "opportunity_reliability"]
    assert result.loc[5, "training_sample_weight"] < result.loc[4, "training_sample_weight"]
    assert result.loc[6, "opportunity_reliability"] == 0
    assert np.isnan(result.loc[6, "training_sample_weight"])
    assert result.loc[4, "component_coverage_fraction"] == pytest.approx(1.0)
    assert result.loc[4, "domain_coverage_fraction"] == pytest.approx(1.0)


def test_observed_target_reports_partial_component_and_domain_coverage():
    frame = fixture_frame()
    frame.loc[0, "bad_rate"] = np.nan

    result = ObservedRoleTarget(fixture_spec()).fit(frame).transform(frame)

    assert result.loc[0, "component_coverage_fraction"] == pytest.approx(0.7)
    assert result.loc[0, "domain_coverage_fraction"] == pytest.approx(0.7)
    assert result.loc[0, "training_sample_weight"] < result.loc[1, "training_sample_weight"]


def test_score_panel_keeps_abstaining_role_visible():
    scored, audit = score_observed_panel(fixture_frame(), specs={"test:role": fixture_spec()})
    assert len(scored) == 7
    assert audit["scored_rows"] == 6
    assert scored.duplicated(["sport", "player_id", "season"]).sum() == 0


def test_sustained_index_uses_current_and_prior_two_seasons_only():
    frame = pd.DataFrame(
        {
            "sport": ["x"] * 4,
            "player_id": ["p"] * 4,
            "season": [2021, 2022, 2024, 2025],
            "observed_role_percentile": [10.0, 20.0, 80.0, 100.0],
        }
    )
    result = add_sustained_index(frame).set_index("season")
    assert result.loc[2021, "sustained_3y_percentile"] == 10
    # 2021 is outside the inclusive 2022-24 window for season 2024.
    assert result.loc[2024, "sustained_3y_percentile"] == pytest.approx(
        np.average([20, 80], weights=[0.7**2, 1.0])
    )


def test_registry_exposes_five_distinct_score_kinds():
    contract = registry_payload()["score_contract"]
    assert set(contract) == {
        "observed_role_percentile",
        "native_forecast_percentile",
        "native_build_profile_forecast_percentile",
        "cross_sport_physical_estimate",
        "cross_sport_transfer_guesstimate",
    }


def test_offensive_line_roles_are_registered_abstentions():
    specs = role_specs()
    for key in ("nfl:OT", "nfl:IOL"):
        spec = specs[key]
        assert spec.domains == ()
        assert spec.evidence_status == "abstain_source_rights_and_label_limit"
        assert "no numeric target" in spec.limitation


def test_offensive_line_abstention_preserves_roster_row_and_status():
    frame = fixture_frame().iloc[[0]].copy()
    frame["sport"] = "nfl"
    frame["role"] = "OT"
    spec = role_specs()["nfl:OT"]

    scored, _ = score_observed_panel(frame, specs={"nfl:OT": spec})

    assert len(scored) == 1
    assert scored.loc[0, "player_id"] == "a"
    assert scored.loc[0, "target_status"] == "abstain_source_rights_and_label_limit"
    assert pd.isna(scored.loc[0, "observed_role_percentile"])
