import numpy as np
import pandas as pd

from possession_lab.all_roles_models import (
    LinearPercentileModel,
    build_native_forecast_pairs,
    ood_diagnostics,
    train_bridge_models,
    train_native_forecast_models,
    train_physical_models,
)
from possession_lab.all_roles_registry import DomainSpec, MetricSpec, RoleSpec


def _spec(sport: str, dimensions: tuple[str, ...]) -> RoleSpec:
    return RoleSpec(
        sport=sport,
        role="role",
        label=f"{sport} role",
        min_opportunity=1,
        opportunity_unit="minutes",
        domains=tuple(
            DomainSpec(
                name=f"domain_{index}",
                dimension=dimension,
                weight=1.0,
                metrics=(MetricSpec(f"metric_{index}"),),
            )
            for index, dimension in enumerate(dimensions)
        ),
    )


def _scored_panel() -> pd.DataFrame:
    rows = []
    for sport, offset in [("a", 0.0), ("b", 2.0)]:
        for season in range(2021, 2026):
            for player in range(24):
                height = 175 + player * 1.5 + offset
                weight = 72 + player * 1.1 + offset
                creation = 5 + player * 3.5
                scoring = 95 - player * 3.0
                observed = np.clip(0.35 * creation + 0.35 * scoring + 0.3 * (height - 170), 0, 100)
                rows.append(
                    {
                        "sport": sport,
                        "player_id": f"{sport}{player}",
                        "name": f"{sport} {player}",
                        "season": season,
                        "role": "role",
                        "height_cm": height,
                        "weight_kg": weight,
                        "age": 20 + player % 12 + season - 2021,
                        "observed_role_percentile": observed,
                        "target_status": "eligible",
                        "availability_percentile": 50 + player,
                        "sustained_3y_percentile": observed,
                        "dimension_creation_distribution_percentile": creation,
                        "dimension_scoring_finishing_percentile": scoring,
                        "dimension_possession_security_percentile": 40 + player,
                    }
                )
    return pd.DataFrame(rows)


def test_linear_model_handles_missing_and_explains_contributions():
    frame = pd.DataFrame(
        {
            "height_cm": [180, 185, 190, np.nan] * 4,
            "weight_kg": [75, 80, 90, 85] * 4,
            "target": [20, 40, 80, 50] * 4,
        }
    )
    model = LinearPercentileModel(("height_cm", "weight_kg")).fit(frame, "target")
    prediction = model.predict(frame.iloc[[0]])
    explanation = model.explain(frame.iloc[[0]])[0]
    assert 0 <= prediction[0] <= 100
    assert {item["feature"] for item in explanation} == {"height_cm", "weight_kg"}
    assert model.metadata()["training_rows"] == 16


def test_native_pairs_never_use_same_season_target():
    panel = _scored_panel().query("sport == 'a'")
    pairs = build_native_forecast_pairs(panel)
    assert (pairs["target_season"] == pairs["feature_season"] + 1).all()
    assert pairs["target_season"].min() == 2022
    assert pairs["target_season"].max() == 2025
    assert pairs["realized_target_status"].eq("eligible").all()
    assert pairs["target_eligible"].all()


def test_native_forecast_requires_eligible_same_role_and_deployable_inputs():
    panel = _scored_panel().query("sport == 'a'").copy()
    panel.loc[
        panel["player_id"].eq("a0") & panel["season"].eq(2025), "role"
    ] = "other"
    panel.loc[
        panel["player_id"].eq("a1") & panel["season"].eq(2025), "target_status"
    ] = "low_sample"
    panel.loc[
        panel["player_id"].eq("a2") & panel["season"].eq(2024), "target_status"
    ] = "low_sample"
    panel.loc[
        panel["player_id"].eq("a3") & panel["season"].eq(2024),
        "dimension_creation_distribution_percentile",
    ] = np.nan
    panel.loc[
        panel["player_id"].eq("a4") & panel["season"].eq(2024), "height_cm"
    ] = np.nan
    panel.loc[
        panel["player_id"].eq("a5") & panel["season"].eq(2024), "age"
    ] = np.nan
    specs = {
        "a:role": _spec(
            "a",
            ("creation_distribution", "scoring_finishing", "possession_security"),
        )
    }

    heads, pairs = train_native_forecast_models(panel, specs=specs)
    relevant = pairs.loc[pairs["prior_role"].eq("role")]
    dimensions = [
        "dimension_creation_distribution_percentile",
        "dimension_scoring_finishing_percentile",
        "dimension_possession_security_percentile",
    ]
    expected = relevant.loc[
        relevant["same_role_target"]
        & relevant["target_status"].eq("eligible")
        & relevant["target_eligible"]
        & relevant[["height_cm", "weight_kg", *dimensions]].notna().all(axis=1)
    ]
    head = heads["a:role"]

    assert (~relevant["same_role_target"]).sum() == 1
    assert head["model"].training_rows == len(expected)
    assert head["usable_coverage"]["usable_rows"] == len(expected)
    assert head["usable_coverage"]["excluded_role_transition_rows"] == 1
    # Missing age remains deployable and is handled by train-only median imputation.
    assert expected["age"].isna().sum() == 1


def test_physical_training_uses_only_eligible_labels_with_observed_build():
    panel = _scored_panel().query("sport == 'a'").copy()
    panel.loc[panel.index[0], "target_status"] = "low_sample"
    panel.loc[panel.index[1], "height_cm"] = np.nan
    panel.loc[panel.index[2], "age"] = np.nan
    specs = {"a:role": _spec("a", ("creation_distribution",))}

    head = train_physical_models(panel, specs=specs)["a:role"]

    assert head["usable_coverage"]["eligible_label_rows"] == len(panel) - 1
    assert head["usable_coverage"]["usable_rows"] == len(panel) - 2
    assert head["model"].training_rows == len(panel) - 2
    assert head["usable_coverage"]["missing_required_input_rows"]["height_cm"] == 1


def test_bridge_uses_fixed_dimension_intersection():
    panel = _scored_panel()
    specs = {
        "a:role": _spec(
            "a",
            ("creation_distribution", "scoring_finishing", "possession_security"),
        ),
        "b:role": _spec(
            "b",
            ("creation_distribution", "scoring_finishing", "defensive_disruption"),
        ),
    }
    bridges = train_bridge_models(panel, specs=specs)
    head = bridges["a:role->b:role"]
    assert head["dimensions"] == ["creation_distribution", "scoring_finishing"]
    assert head["semantic_bridge_grade"] == "limited"
    assert "dimension_possession_security_percentile" not in head["features"]
    assert "dimension_defensive_disruption_percentile" not in head["features"]
    assert "target_proxy_reconstruction_gate" in head
    assert "evidence_gate" not in head
    assert "not cross-sport validation" in head["evaluation_scope"]


def test_bridge_uses_only_eligible_target_rows_with_deployable_inputs():
    panel = _scored_panel()
    target_index = panel.index[panel["sport"].eq("b")]
    panel.loc[target_index[0], "target_status"] = "low_sample"
    panel.loc[target_index[1], "weight_kg"] = np.nan
    panel.loc[target_index[2], "dimension_creation_distribution_percentile"] = np.nan
    panel.loc[target_index[3], "age"] = np.nan
    specs = {
        "a:role": _spec("a", ("creation_distribution", "scoring_finishing")),
        "b:role": _spec("b", ("creation_distribution", "scoring_finishing")),
    }

    head = train_bridge_models(panel, specs=specs)["a:role->b:role"]
    expected_rows = len(target_index) - 3

    assert head["model"].training_rows == expected_rows
    assert head["usable_coverage"]["eligible_label_rows"] == len(target_index) - 1
    assert head["usable_coverage"]["usable_rows"] == expected_rows
    assert head["usable_coverage"]["missing_required_input_rows"]["weight_kg"] == 1


def test_ood_diagnostic_flags_extreme_build():
    reference = {
        "height_cm": {"median": 190.0, "iqr": 10.0, "p01": 170.0, "p99": 210.0}
    }
    result = ood_diagnostics(pd.DataFrame({"height_cm": [250.0]}), reference)
    assert result["status"] == "out_of_domain"
    assert result["features"][0]["status"] == "outside_1_99_reference"
