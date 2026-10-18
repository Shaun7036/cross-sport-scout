import math

import numpy as np
import pandas as pd
import pytest

from possession_lab.ensemble_features import (
    CORE_FEATURES,
    prepare_profile_features,
    validate_profile,
)


@pytest.mark.parametrize("height", [1e-300, 1e300])
def test_unrepresentable_body_arithmetic_is_a_validation_error(height):
    with pytest.raises(ValueError, match="finite"):
        validate_profile({"height_cm": height, "weight_kg": 95})


def test_prepare_profile_features_copies_and_derives_numeric_bmi():
    source = pd.DataFrame({
        "player_id": ["a", "b"],
        "height_cm": ["180", "200"],
        "weight_kg": [81, "100"],
        "age": [25, "30"],
        "role": ["one", "two"],
        "bmi": [999, 999],
    })

    result = prepare_profile_features(source)

    assert CORE_FEATURES == ["height_cm", "weight_kg", "age", "bmi"]
    assert result is not source
    assert source["height_cm"].dtype == object
    assert source["bmi"].tolist() == [999, 999]
    assert result["role"].tolist() == ["one", "two"]
    assert result["height_cm"].dtype.kind == "f"
    assert result.loc[0, "bmi"] == pytest.approx(25.0)
    assert result.loc[1, "bmi"] == pytest.approx(25.0)


def test_prepare_profile_features_adds_missing_core_columns_and_safe_bmi():
    result = prepare_profile_features(pd.DataFrame({
        "player_id": ["a", "b", "c"],
        "height_cm": [0, np.inf, 180],
        "weight_kg": [80, 90, "bad"],
    }))

    assert result["age"].isna().all()
    assert result["bmi"].isna().all()
    assert result.loc[1, "height_cm"] != np.inf


def test_validate_profile_metric_units_extras_and_unsupported_mental_input():
    result = validate_profile({
        "height_cm": 190,
        "weight_kg": 90,
        "age": 27,
        "wingspan_cm": 203,
        "forty_seconds": 4.55,
        "reaction_speed": 0.18,
        "spatial_awareness": 92,
    })

    assert result["features"] == {
        "height_cm": 190.0,
        "weight_kg": 90.0,
        "age": 27.0,
        "bmi": pytest.approx(90 / 1.9**2),
    }
    assert result["provided_extra_measurements"] == {
        "wingspan_cm": 203.0,
        "forty_seconds": 4.55,
    }
    assert result["warnings"] == []
    assert result["unsupported_features"] == ["reaction_speed", "spatial_awareness"]


def test_validate_profile_normalizes_imperial_and_allows_missing_age():
    result = validate_profile({"height_ft": 6, "height_in": 2, "weight_lb": 200})

    assert result["features"]["height_cm"] == pytest.approx(187.96)
    assert result["features"]["weight_kg"] == pytest.approx(90.718474)
    assert result["features"]["age"] is None
    assert result["features"]["bmi"] == pytest.approx(25.678, abs=0.001)


def test_validate_profile_accepts_consistent_redundant_aliases():
    result = validate_profile({
        "height_cm": 187.96,
        "height_inches": 74,
        "height_ft": 6,
        "height_in": 2,
        "weight_kg": 90.72,
        "weight_lb": 200,
        "bmi": 25.68,
        "age": 30,
    })

    assert result["features"]["height_cm"] == pytest.approx(187.96)
    assert result["features"]["weight_kg"] == pytest.approx(90.72)


@pytest.mark.parametrize(
    "profile, message",
    [
        ({"height_cm": 180, "height_inches": 80, "weight_kg": 80}, "Contradictory height"),
        ({"height_cm": 180, "weight_kg": 80, "weight_lb": 250}, "Contradictory weight"),
        ({"height_cm": 180, "weight_kg": 80, "bmi": 40}, "Contradictory bmi"),
    ],
)
def test_validate_profile_rejects_contradictory_aliases(profile, message):
    with pytest.raises(ValueError, match=message):
        validate_profile(profile)


@pytest.mark.parametrize(
    "key, value, message",
    [
        ("height_cm", 0, "height_cm must be positive"),
        ("height_cm", -180, "height_cm must be positive"),
        ("height_cm", np.inf, "height_cm must be finite"),
        ("weight_kg", 0, "weight_kg must be positive"),
        ("weight_kg", np.nan, "weight_kg must be finite"),
        ("weight_kg", True, "not a boolean"),
    ],
)
def test_validate_profile_rejects_invalid_core_measurements(key, value, message):
    profile = {"height_cm": 180, "weight_kg": 80}
    profile[key] = value
    with pytest.raises(ValueError, match=message):
        validate_profile(profile)


def test_validate_profile_enforces_adult_age_contract():
    with pytest.raises(ValueError, match="Adult-only model"):
        validate_profile({"height_cm": 180, "weight_kg": 80, "age": 17})
    with pytest.raises(ValueError, match="over 100"):
        validate_profile({"height_cm": 180, "weight_kg": 80, "age": 101})


def test_validate_profile_warns_without_clipping_extreme_body_values():
    result = validate_profile({"height_cm": 250, "weight_kg": 210, "age": 70})

    assert result["features"]["height_cm"] == 250
    assert result["features"]["weight_kg"] == 210
    assert result["features"]["age"] == 70
    assert len(result["warnings"]) == 3
    assert all("not clipped" in warning for warning in result["warnings"])


def test_validate_profile_rejects_incomplete_or_invalid_feet_inches():
    with pytest.raises(ValueError, match="supplied together"):
        validate_profile({"height_ft": 6, "weight_kg": 80})
    with pytest.raises(ValueError, match="0-to-under-12"):
        validate_profile({"height_ft": 5, "height_in": 12, "weight_kg": 80})


def test_validate_profile_requires_explicit_height_and_weight_units():
    with pytest.raises(ValueError, match="height is required"):
        validate_profile({"weight_kg": 80})
    with pytest.raises(ValueError, match="weight is required"):
        validate_profile({"height_cm": 180})
    with pytest.raises(TypeError, match="dictionary"):
        validate_profile(None)


def test_core_outputs_are_finite_for_valid_profile():
    result = validate_profile({"height_cm": "182.5", "weight_kg": "84.2", "age": None})
    assert all(
        value is None or math.isfinite(value) for value in result["features"].values()
    )
