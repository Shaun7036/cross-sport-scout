import json

import numpy as np
import pandas as pd
import pytest

from possession_lab.all_roles_models import (
    PHYSICAL_FEATURES,
    LinearPercentileModel,
    _apply_native_profile_pooling,
    _pooling_family_frame,
    _select_family_pooling_tau,
    build_native_forecast_pairs,
)
from possession_lab.all_roles_pooling import (
    BlendedPercentileModel,
    effective_sample_size,
    pooling_gate,
    role_blend_weight,
    role_dummy_name,
)
from possession_lab.all_roles_registry import role_specs


def test_effective_sample_size_and_blend_weight_are_monotonic():
    assert effective_sample_size([1, 1, 1, 1]) == pytest.approx(4.0)
    assert effective_sample_size([1, 0.1, 0.1, 0.1]) < 4.0
    assert role_blend_weight(10, 25) < role_blend_weight(100, 25)
    assert role_blend_weight(10, 0) == 1.0


def test_blended_model_uses_fixed_target_role_dummy_and_combines_predictions():
    rows = 30
    frame = pd.DataFrame(
        {
            "height_cm": np.linspace(170, 200, rows),
            "weight_kg": np.linspace(65, 110, rows),
            "pool_role__nba__guard": [1.0] * 15 + [0.0] * 15,
            "pool_role__nba__forward": [0.0] * 15 + [1.0] * 15,
        }
    )
    frame["target"] = np.linspace(10, 90, rows)
    role = LinearPercentileModel(("height_cm", "weight_kg")).fit(frame, "target")
    family = LinearPercentileModel(
        (
            "height_cm",
            "weight_kg",
            role_dummy_name("nba:guard"),
            role_dummy_name("nba:forward"),
        )
    ).fit(frame, "target")
    model = BlendedPercentileModel(
        role_model=role,
        family_model=family,
        role_weight=0.75,
        family="nba:skill_roles",
        role_key="nba:guard",
        family_role_keys=("nba:guard", "nba:forward"),
        tau=25.0,
        effective_rows=75.0,
    )
    row = pd.DataFrame({"height_cm": [185.0], "weight_kg": [85.0]})

    expected_family_row = row.assign(
        pool_role__nba__guard=1.0,
        pool_role__nba__forward=0.0,
    )
    expected = 0.75 * role.predict(row)[0] + 0.25 * family.predict(expected_family_row)[0]

    assert model.predict(row)[0] == pytest.approx(expected)
    assert set(model.features) == {"height_cm", "weight_kg"}
    assert model.metadata()["family_weight"] == pytest.approx(0.25)
    assert all(not item["feature"].startswith("pool_role__") for item in model.explain(row)[0])


def test_pooling_gate_requires_sample_size_and_positive_ci_lower_bound():
    positive = {"ci90": [0.01, 2.0]}
    crosses_zero = {"ci90": [-0.01, 2.0]}

    assert pooling_gate(19, positive) == "insufficient_frozen_evidence"
    assert pooling_gate(20, positive) == "supported"
    assert pooling_gate(20, crosses_zero) == "not_supported"
    assert pooling_gate(20, {"ci90": [None, None]}) == "insufficient_frozen_evidence"


def _synthetic_nba_panel() -> pd.DataFrame:
    specs = role_specs()
    dimensions = specs["nba:guard"].dimensions
    rows = []
    for role in ("guard", "forward"):
        for athlete_index, ability in enumerate(np.linspace(10.0, 90.0, 36)):
            for season in range(2021, 2026):
                target = ability
                if role == "guard" and season <= 2022:
                    target = 100.0 - ability
                row = {
                    "sport": "nba",
                    "player_id": f"{role}-{athlete_index}",
                    "player_name": f"{role.title()} {athlete_index}",
                    "season": season,
                    "role": role,
                    "height_cm": 175.0 + 0.12 * ability,
                    "weight_kg": 68.0 + 0.25 * ability,
                    "age": 22.0 + season - 2021,
                    "observed_role_percentile": target,
                    "target_status": "eligible",
                    "training_sample_weight": 1.0,
                    "opportunity_reliability": 1.0,
                }
                row.update(
                    {
                        f"dimension_{dimension}_percentile": ability
                        for dimension in dimensions
                    }
                )
                rows.append(row)
    return pd.DataFrame(rows)


def _nba_pooling_selection(panel: pd.DataFrame) -> dict:
    specs = role_specs()
    pairs = build_native_forecast_pairs(panel)
    inputs = {}
    for role_key in ("nba:guard", "nba:forward"):
        spec = specs[role_key]
        dimensions = tuple(
            f"dimension_{dimension}_percentile" for dimension in spec.dimensions
        )
        role_pairs = pairs.loc[
            pairs["sport"].eq("nba")
            & pairs["prior_role"].eq(spec.role)
            & pairs["same_role_target"]
        ].copy()
        role_pairs["evaluation_eligible"] = (
            role_pairs["target_status"].eq("eligible")
            & role_pairs["realized_target_status"].eq("eligible")
        )
        inputs[role_key] = {
            "frame": role_pairs,
            "features": (*PHYSICAL_FEATURES, *dimensions),
        }
    family_role_keys = ("nba:guard", "nba:forward", "nba:center")
    family_frame, features = _pooling_family_frame(inputs, family_role_keys)
    return _select_family_pooling_tau(
        family_frame,
        features=features,
        family_role_keys=family_role_keys,
    )


def test_tau_selection_never_uses_frozen_2025_labels():
    original = _synthetic_nba_panel()
    changed = original.copy()
    frozen = changed["season"].eq(2025)
    changed.loc[frozen, "observed_role_percentile"] = (
        100.0 - changed.loc[frozen, "observed_role_percentile"]
    )

    original_selection = _nba_pooling_selection(original)
    changed_selection = _nba_pooling_selection(changed)

    assert original_selection["selected_tau"] == changed_selection["selected_tau"]
    assert original_selection == changed_selection
    assert original_selection["rolling_folds"]
    assert all(fold["season"] < 2025 for fold in original_selection["rolling_folds"])


def _small_pooling_inputs_and_heads():
    inputs = {}
    heads = {}
    for offset, role_key in enumerate(("nba:guard", "nba:forward")):
        rows = 30
        frame = pd.DataFrame(
            {
                "player_id": [f"{role_key}-{index}" for index in range(rows)],
                "target_season": [2024] * rows,
                "evaluation_eligible": [True] * rows,
                "height_cm": np.linspace(170 + offset, 200 + offset, rows),
                "weight_kg": np.linspace(65 + offset, 110 + offset, rows),
                "pair_training_sample_weight": [1.0] * rows,
                "target_observed_role_percentile": np.linspace(10, 90, rows),
            }
        )
        role_model = LinearPercentileModel(("height_cm", "weight_kg")).fit(
            frame,
            "target_observed_role_percentile",
        )
        inputs[role_key] = {
            "frame": frame,
            "features": ("height_cm", "weight_kg"),
        }
        heads[role_key] = {"model": role_model}
    return inputs, heads


def test_supported_pooling_wraps_model_and_unsupported_preserves_role_only(monkeypatch):
    inputs, heads = _small_pooling_inputs_and_heads()
    guard_role_only = heads["nba:guard"]["model"]
    forward_role_only = heads["nba:forward"]["model"]
    selection = {
        "status": "selected_from_prefreeze_rolling_origin",
        "policy": "test fixture",
        "candidate_taus": [0.0, 25.0],
        "rolling_folds": [{"season": 2024, "n": 60, "roles": {}}],
        "scores": [
            {"tau": 0.0, "n": 60, "mae": 10.0, "rmse": 12.0, "spearman": 0.5},
            {"tau": 25.0, "n": 60, "mae": 9.0, "rmse": 11.0, "spearman": 0.6},
        ],
        "selected_tau": 25.0,
        "tuning_season_upper_bound_exclusive": 2025,
    }

    def comparison(_frame, *, role_key, **_kwargs):
        low = 0.25 if role_key == "nba:guard" else -0.25
        metrics = {"n": 20, "mae": 8.0, "rmse": 10.0, "spearman": 0.5}
        return {
            "n": 20,
            "effective_role_rows": 30.0,
            "role_weight": 30.0 / 55.0,
            "role_only": metrics,
            "partially_pooled": {**metrics, "mae": 7.0},
            "advantage": {
                "estimate": 1.0,
                "ci90": [low, 1.75],
                "clusters": 20,
                "iterations": 500,
                "comparator": "role_only",
            },
        }

    monkeypatch.setattr(
        "possession_lab.all_roles_models._select_family_pooling_tau",
        lambda *_args, **_kwargs: selection,
    )
    monkeypatch.setattr(
        "possession_lab.all_roles_models._pooling_frozen_comparison",
        comparison,
    )

    _apply_native_profile_pooling(heads, inputs)

    assert isinstance(heads["nba:guard"]["model"], BlendedPercentileModel)
    assert heads["nba:guard"]["model"].role_model is guard_role_only
    assert heads["nba:guard"]["selected_model_family"] == "partially_pooled"
    assert heads["nba:guard"]["partial_pooling"]["status"] == "deployed"
    assert heads["nba:forward"]["model"] is forward_role_only
    assert heads["nba:forward"]["selected_model_family"] == "role_only"
    assert heads["nba:forward"]["partial_pooling"]["gate"] == "not_supported"
    json.dumps(heads["nba:guard"]["partial_pooling"], allow_nan=False)
    json.dumps(heads["nba:forward"]["partial_pooling"], allow_nan=False)
