import numpy as np
import pandas as pd
import pytest

from possession_lab.ensemble_targets import HeadSpec, RoleTarget, WeightedECDF, athlete_weights, head_specs


def fixture():
    return pd.DataFrame(
        {
            "player_id": ["a", "a", "b", "c"],
            "athlete_id": ["a", "a", "b", "c"],
            "opportunity": [100.0, 200.0, 200.0, 300.0],
            "steals": [0.0, 2.0, 10.0, 20.0],
        }
    )


def test_weighted_cdf_ties_and_extremes():
    cdf = WeightedECDF().fit([1, 1, 2, 3])
    assert cdf.transform(np.array([0, 1, 2, 3, 4])).tolist() == [0, 25, 62.5, 87.5, 100]
    assert np.isnan(cdf.transform(np.array([np.nan]))[0])


def test_target_fold_reference_is_not_changed_by_future_transform():
    spec = HeadSpec("nba", "guard", 100, {"recovery": {"weight": 1.0, "metrics": {"steals": 1.0}}})
    reference = fixture()
    target = RoleTarget(spec).fit(reference)
    before = target.transform(reference).efficacy_target.to_numpy()
    future = reference.copy()
    future.steals = 10000
    target.transform(future)
    np.testing.assert_array_equal(before, target.transform(reference).efficacy_target)
    # Shrinkage depends on exposure: a short zero-event row can outrank a
    # longer near-zero row. Check ordering at equal exposure instead.
    equal = reference.copy()
    equal.opportunity = 200.0
    assert np.all(np.diff(target.transform(equal).efficacy_target) >= 0)


def test_target_missing_labels_remain_missing():
    spec = HeadSpec("nba", "guard", 100, {"recovery": {"weight": 1.0, "metrics": {"steals": 1.0}}})
    target = RoleTarget(spec).fit(fixture())
    missing = fixture()
    missing.loc[1, "steals"] = np.nan
    assert np.isnan(target.transform(missing).loc[1, "efficacy_target"])
    with pytest.raises(ValueError, match="Missing target"):
        RoleTarget(spec).fit(missing)


def test_each_athlete_has_equal_total_reference_weight():
    data = fixture()
    data["weight"] = athlete_weights(data)
    weights = data.groupby("athlete_id").weight.sum()
    assert weights.max() == weights.min()


def test_domain_definitions_cover_four_sports_without_raw_pooling():
    specs = head_specs()
    assert set(s.sport for s in specs.values()) == {"nfl", "nba", "nhl", "epl"}
    assert len(specs) == 15
    for spec in specs.values():
        assert sum(d["weight"] for d in spec.domains.values()) == pytest.approx(1.0)
