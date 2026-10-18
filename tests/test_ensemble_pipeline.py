from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possession_lab.ensemble import (
    EXPERTS,
    athlete_partition,
    crossfit,
    eligible_rows,
    fit_experts,
    group_folds,
    predict_experts,
)
from possession_lab.ensemble_targets import (
    HeadSpec,
    SeasonalRoleTarget,
    athlete_weights,
)


def _one_metric_spec(sport: str, role: str, metric: str) -> HeadSpec:
    return HeadSpec(
        sport=sport,
        role=role,
        min_opportunity=100,
        domains={"activity": {"weight": 1.0, "metrics": {metric: 1.0}}},
    )


def _integration_panel() -> tuple[pd.DataFrame, dict[str, HeadSpec]]:
    rng = np.random.default_rng(2025)
    specs = {
        "nba:guard": _one_metric_spec("nba", "guard", "steals"),
        "nhl:wing": _one_metric_spec("nhl", "wing", "takeaways"),
    }
    rows: list[dict] = []
    for sport, role, metric, base_height, base_weight in [
        ("nba", "guard", "steals", 184.0, 82.0),
        ("nhl", "wing", "takeaways", 180.0, 87.0),
    ]:
        for athlete in range(24):
            height = base_height + (athlete - 11.5) * 0.55 + rng.normal(0, 0.35)
            weight = base_weight + (athlete - 11.5) * 0.8 + rng.normal(0, 0.5)
            rate = max(0.002, 0.012 + 0.0007 * (height - base_height) + 0.0004 * (weight - base_weight))
            for season, multiplier in [(2024, 1.0), (2025, 2.0)]:
                opportunity = 1000.0
                row = {
                    "sport": sport,
                    "role": role,
                    "head": f"{sport}:{role}",
                    "athlete_id": f"{sport}:athlete-{athlete:02d}",
                    "player_id": f"athlete-{athlete:02d}",
                    "season": season,
                    "opportunity": opportunity,
                    "height_cm": height,
                    "weight_kg": weight,
                    "age": 22.0 + athlete % 10,
                    metric: opportunity * rate * multiplier,
                }
                rows.append(row)
    panel = pd.DataFrame(rows).sample(frac=1, random_state=17).reset_index(drop=True)
    panel["row_id"] = np.arange(len(panel))
    return panel, specs


def test_athlete_partition_is_stable_across_seasons_and_row_order():
    frame = pd.DataFrame({
        "athlete_id": np.repeat([f"athlete-{index}" for index in range(30)], 3),
        "season": np.tile([2023, 2024, 2025], 30),
    })
    frame["partition"] = frame["athlete_id"].map(athlete_partition)
    shuffled = frame.sample(frac=1, random_state=11).copy()
    shuffled["recomputed"] = shuffled["athlete_id"].map(athlete_partition)

    assert frame.groupby("athlete_id")["partition"].nunique().eq(1).all()
    assert (shuffled["partition"] == shuffled["recomputed"]).all()
    expected = frame.drop_duplicates("athlete_id").set_index("athlete_id")["partition"].to_dict()
    observed = shuffled.drop_duplicates("athlete_id").set_index("athlete_id")["recomputed"].to_dict()
    assert observed == expected


def test_group_folds_keep_every_season_and_role_of_an_athlete_together():
    frame = pd.DataFrame({
        "athlete_id": np.repeat([f"athlete-{index}" for index in range(12)], 3),
        "season": np.tile([2023, 2024, 2025], 12),
        "role": np.tile(["role-a", "role-b", "role-a"], 12),
    })
    validation_rows: set[int] = set()
    validation_athletes: set[str] = set()

    for train_indices, validation_indices in group_folds(frame, n_splits=3):
        train_ids = set(frame.iloc[train_indices]["athlete_id"])
        validation_ids = set(frame.iloc[validation_indices]["athlete_id"])
        assert train_ids.isdisjoint(validation_ids)
        for athlete in validation_ids:
            all_rows = set(frame.index[frame["athlete_id"].eq(athlete)])
            assert all_rows.issubset(set(validation_indices))
        validation_rows.update(validation_indices)
        validation_athletes.update(validation_ids)

    assert validation_rows == set(frame.index)
    assert validation_athletes == set(frame["athlete_id"])


def test_epl_eligibility_excludes_unobserved_or_unsupported_rows():
    spec = HeadSpec(
        "epl",
        "DEF",
        450,
        {"tackling": {"weight": 1.0, "metrics": {"tackles_won": 1.0}}},
    )
    rows = [
        ("valid-adult", 2025, 600, 185, 82, 25, 30),
        ("valid-missing-age", 2025, 600, 185, 82, np.nan, 30),
        ("historic-unlabelled", 2024, 600, 185, 82, 25, 30),
        ("missing-event", 2025, 600, 185, 82, 25, np.nan),
        ("missing-height", 2025, 600, np.nan, 82, 25, 30),
        ("missing-weight", 2025, 600, 185, np.nan, 25, 30),
        ("under-threshold", 2025, 449, 185, 82, 25, 30),
        ("underage", 2025, 600, 185, 82, 17, 30),
    ]
    frame = pd.DataFrame(
        rows,
        columns=[
            "athlete_id",
            "season",
            "opportunity",
            "height_cm",
            "weight_kg",
            "age",
            "tackles_won",
        ],
    )
    frame["sport"] = "epl"
    frame["role"] = "DEF"

    result = eligible_rows(frame, spec)

    assert set(result["athlete_id"]) == {"valid-adult", "valid-missing-age"}
    assert result["season"].eq(2025).all()
    assert result["opportunity"].ge(450).all()


def test_seasonal_target_is_train_only_and_removes_uniform_rate_scale_shift():
    spec = _one_metric_spec("nba", "guard", "steals")
    athletes = [f"athlete-{index:02d}" for index in range(16)]
    training = pd.DataFrame({
        "athlete_id": athletes * 2,
        "season": np.repeat([2024, 2025], len(athletes)),
        "opportunity": 1000.0,
        "steals": np.concatenate([np.arange(1, 17), 2 * np.arange(1, 17)]).astype(float),
    })
    target = SeasonalRoleTarget(spec).fit(training)
    before_2024 = target.transform(training.loc[training.season.eq(2024)]).efficacy_target.to_numpy()
    before_2025 = target.transform(training.loc[training.season.eq(2025)]).efficacy_target.to_numpy()
    np.testing.assert_allclose(before_2024, before_2025)

    reference = target.seasons_[2025]
    cdf_values = reference.components_["steals"]["cdf"].values_.copy()
    cdf_mass = reference.components_["steals"]["cdf"].mass_.copy()
    prior = reference.components_["steals"]["prior"]
    heldout = pd.DataFrame({
        "athlete_id": ["heldout-a", "heldout-b"],
        "season": [2025, 2025],
        "opportunity": [1000.0, 1000.0],
        "steals": [0.0, 1_000_000.0],
    })
    target.transform(heldout)

    np.testing.assert_array_equal(reference.components_["steals"]["cdf"].values_, cdf_values)
    np.testing.assert_array_equal(reference.components_["steals"]["cdf"].mass_, cdf_mass)
    assert reference.components_["steals"]["prior"] == prior
    assert reference.reference_players_ == len(athletes)
    np.testing.assert_allclose(
        target.transform(training.loc[training.season.eq(2025)]).efficacy_target,
        before_2025,
    )


def test_fold_fitted_scalers_and_target_references_exclude_validation_athletes():
    panel, specs = _integration_panel()
    train_indices, validation_indices = next(group_folds(panel, n_splits=3))
    train = panel.iloc[train_indices].copy()
    validation = panel.iloc[validation_indices].copy()
    assert set(train.athlete_id).isdisjoint(validation.athlete_id)

    bundle = fit_experts(train, specs, fast=True)
    for key, spec in specs.items():
        head_train = train.loc[train["head"].eq(key)]
        fitted = bundle["heads"][key]
        weights = athlete_weights(head_train)
        expected_center = np.average(head_train[["height_cm", "weight_kg"]], axis=0, weights=weights)
        np.testing.assert_allclose(fitted["shared_center"], expected_center)
        assert head_train.athlete_id.nunique() < panel.loc[panel["head"].eq(key)].athlete_id.nunique()

        metric = next(iter(next(iter(spec.domains.values()))["metrics"]))
        expected_target = SeasonalRoleTarget(spec).fit(head_train)
        for season, season_target in fitted["target"].seasons_.items():
            expected = expected_target.seasons_[season]
            assert season_target.reference_players_ == head_train.loc[
                head_train.season.eq(season), "athlete_id"
            ].nunique()
            np.testing.assert_allclose(
                season_target.components_[metric]["cdf"].values_,
                expected.components_[metric]["cdf"].values_,
            )


@pytest.fixture(scope="module")
def fitted_integration():
    panel, specs = _integration_panel()
    bundle = fit_experts(panel, specs, fast=True)
    out_of_fold = crossfit(panel, specs, fast=True, n_splits=3)
    return panel, specs, bundle, out_of_fold


def test_fast_two_sport_expert_pipeline_is_bounded_and_cross_fitted(fitted_integration):
    panel, _, _, predictions = fitted_integration

    assert set(EXPERTS) == {
        "baseline50",
        "archetype",
        "ridge",
        "hist_gradient_boosting",
        "extra_trees",
        "shared",
    }
    assert set(EXPERTS).issubset(predictions.columns)
    assert len(predictions) == len(panel)
    assert np.isfinite(predictions[EXPERTS].to_numpy()).all()
    assert ((predictions[EXPERTS] >= 0) & (predictions[EXPERTS] <= 100)).all(axis=None)
    assert predictions["target"].between(0, 100).all()

    for fold, (_, validation_indices) in enumerate(group_folds(panel, n_splits=3)):
        expected_ids = set(panel.iloc[validation_indices]["athlete_id"])
        observed_ids = set(predictions.loc[predictions["fold"].eq(fold), "athlete_id"])
        assert observed_ids == expected_ids


def test_inference_predictions_do_not_use_mutated_raw_outcomes(fitted_integration):
    panel, specs, bundle, _ = fitted_integration
    original = predict_experts(bundle, panel, targets=False).sort_values("row_id")
    mutated = panel.copy()
    for spec in specs.values():
        for domain in spec.domains.values():
            for metric in domain["metrics"]:
                if metric in mutated:
                    mutated[metric] = np.arange(len(mutated), dtype=float) * 1_000_000.0
    changed = predict_experts(bundle, mutated, targets=False).sort_values("row_id")

    assert "target" not in original
    pd.testing.assert_frame_equal(
        original[["row_id", *EXPERTS]].reset_index(drop=True),
        changed[["row_id", *EXPERTS]].reset_index(drop=True),
    )
