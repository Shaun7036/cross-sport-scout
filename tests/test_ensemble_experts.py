from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.base import clone, is_regressor

from possession_lab.ensemble_experts import ArchetypeRegressor, make_experts


def _separated_profiles() -> tuple[pd.DataFrame, np.ndarray]:
    rng = np.random.default_rng(7)
    groups = [
        (170.0, 68.0, 22.0, 15.0),
        (190.0, 92.0, 27.0, 50.0),
        (207.0, 118.0, 31.0, 85.0),
    ]
    frames, outcomes = [], []
    for height, weight, age, outcome in groups:
        frames.append(
            pd.DataFrame(
                {
                    "height_cm": rng.normal(height, 1.5, 30),
                    "weight_kg": rng.normal(weight, 2.0, 30),
                    "age": rng.normal(age, 0.8, 30),
                }
            )
        )
        outcomes.extend(rng.normal(outcome, 1.0, 30))
    X = pd.concat(frames, ignore_index=True)
    X.loc[5, "weight_kg"] = np.nan
    X.loc[40, "age"] = np.nan
    return X, np.asarray(outcomes)


def test_archetype_regressor_learns_soft_deterministic_clusters() -> None:
    X, y = _separated_profiles()
    model = ArchetypeRegressor(min_cluster_size=10, shrinkage=5.0).fit(X, y)
    assert model.n_clusters_ == 3

    probes = pd.DataFrame(
        {
            "height_cm": [170.0, 190.0, 207.0, np.nan],
            "weight_kg": [68.0, 92.0, 118.0, np.nan],
            "age": [22.0, 27.0, 31.0, np.nan],
        }
    )
    first = model.predict(probes)
    second = model.predict(probes)
    assert np.all(np.isfinite(first))
    assert np.allclose(first, second)
    assert first[0] < first[1] < first[2]

    detail = model.describe(probes)
    assert len(detail) == len(probes)
    for row in detail:
        assert sum(row["probabilities"].values()) == pytest.approx(1.0)
        assert row["effective_support"] > 0
        assert set(row["nearest_center"]) == {"height_cm", "weight_kg", "age", "bmi"}
    assert detail[-1]["nearest_center_distance"] is None
    assert detail[-1]["observed_feature_fraction"] == 0


def test_tiny_data_and_absent_optional_age_fall_back_to_one_archetype() -> None:
    X = pd.DataFrame({"height_cm": [180.0, 185.0, np.nan], "weight_kg": [80.0, 90.0, 85.0]})
    y = np.array([1.0, 2.0, 3.0])
    model = ArchetypeRegressor(min_cluster_size=5).fit(X, y)
    assert model.n_clusters_ == 1
    prediction = model.predict(pd.DataFrame({"height_cm": [182.0], "weight_kg": [None]}))
    assert prediction.tolist() == pytest.approx([2.0])
    detail = model.describe(pd.DataFrame(index=range(1)))
    assert detail[0]["probabilities"] == {"0": 1.0}
    assert "age" in detail[0]["missing_features"]


def test_sample_weight_controls_single_archetype_mean() -> None:
    X = pd.DataFrame({"height_cm": [180.0, 181.0], "weight_kg": [80.0, 81.0]})
    model = ArchetypeRegressor(max_clusters=1, shrinkage=100.0).fit(
        X, [0.0, 10.0], sample_weight=[1.0, 3.0]
    )
    # With one archetype the raw and global weighted means agree, so shrinkage
    # cannot change the expected 7.5 result.
    assert model.predict(X).tolist() == pytest.approx([7.5, 7.5])
    assert model.cluster_support_.tolist() == pytest.approx([4.0])


def test_clone_and_validation_contract() -> None:
    model = ArchetypeRegressor(numeric_features=["height_cm", "weight_kg"], bandwidth=0.7)
    assert is_regressor(model)
    cloned = clone(model)
    assert cloned.get_params()["bandwidth"] == pytest.approx(0.7)
    with pytest.raises(TypeError, match="pandas DataFrame"):
        model.fit(np.ones((3, 2)), [1, 2, 3])
    with pytest.raises(ValueError, match="finite numeric"):
        model.fit(pd.DataFrame({"height_cm": [1, 2]}), [1, np.nan])


def test_expert_factory_models_fit_missing_and_unknown_levels() -> None:
    X, y = _separated_profiles()
    X["context"] = np.where(np.arange(len(X)) % 2, "a", "b")
    experts = make_experts(["height_cm", "weight_kg", "age"], ["context"])
    assert set(experts) == {"archetype", "ridge", "hist_gradient_boosting", "extra_trees"}

    test = X.iloc[:4].copy()
    test.loc[test.index[0], "context"] = "unseen"
    test.loc[test.index[1], "height_cm"] = np.nan
    for name, estimator in experts.items():
        fitted = clone(estimator).fit(X, y)
        predicted = fitted.predict(test)
        assert predicted.shape == (4,), name
        assert np.isfinite(predicted).all(), name

    assert experts["ridge"].named_steps["model"].alpha == pytest.approx(10.0)
    assert experts["extra_trees"].named_steps["model"].n_jobs == 1
