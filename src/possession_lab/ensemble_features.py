"""Shared physical-profile feature contract for the cross-sport ensemble.

``CORE_FEATURES`` is the canonical profile schema, not a promise that every field
is learned. The v1 efficacy model uses height and weight; age/BMI are retained
for reporting. Additional measurements remain provenance, not trained inputs.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

CORE_FEATURES = ["height_cm", "weight_kg", "age", "bmi"]

# Recognized physical/testing fields that callers may submit and retain.  They
# are metadata in the current ensemble, not model inputs, because their public
# coverage is not consistent across all four sports.
EXTRA_MEASUREMENTS = (
    "wingspan_cm",
    "arm_length_cm",
    "leg_length_cm",
    "hand_length_cm",
    "hand_width_cm",
    "top_speed_kmh",
    "forty_seconds",
    "ten_split_seconds",
    "vertical_jump_cm",
    "broad_jump_cm",
    "shuttle_seconds",
    "three_cone_seconds",
    "body_fat_pct",
)

_HEIGHT_KEYS = {"height_cm", "height_inches", "height_ft", "height_in"}
_WEIGHT_KEYS = {"weight_kg", "weight_lb"}
_RECOGNIZED_KEYS = _HEIGHT_KEYS | _WEIGHT_KEYS | {"age", "bmi"} | set(EXTRA_MEASUREMENTS)


def prepare_profile_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with a numeric, consistently derived core feature block.

    This helper prepares already-canonical panel data.  It deliberately does not
    apply unit guessing or silently clip implausible measurements; interactive
    profiles should go through :func:`validate_profile` first.
    """
    result = frame.copy(deep=True)
    for feature in ["height_cm", "weight_kg", "age"]:
        if feature not in result:
            result[feature] = np.nan
        result[feature] = pd.to_numeric(result[feature], errors="coerce").astype(float)
        result[feature] = result[feature].replace([np.inf, -np.inf], np.nan)

    valid_body = result["height_cm"].gt(0) & result["weight_kg"].gt(0)
    result["bmi"] = np.nan
    result.loc[valid_body, "bmi"] = (
        result.loc[valid_body, "weight_kg"]
        / (result.loc[valid_body, "height_cm"] / 100.0) ** 2
    )
    return result


def _provided(profile: dict[str, Any], key: str) -> bool:
    return key in profile and profile[key] is not None


def _finite_number(
    value: Any,
    label: str,
    *,
    positive: bool = True,
    zero_allowed: bool = False,
) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{label} must be a numeric measurement, not a boolean")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be numeric") from error
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    if positive and (number < 0 if zero_allowed else number <= 0):
        qualifier = "non-negative" if zero_allowed else "positive"
        raise ValueError(f"{label} must be {qualifier}")
    return number


def _resolve_aliases(
    candidates: list[tuple[str, float]],
    measurement: str,
    *,
    tolerance: float,
) -> float:
    if not candidates:
        raise ValueError(f"{measurement} is required with an explicit unit")
    reference_label, reference = candidates[0]
    for label, value in candidates[1:]:
        if not math.isclose(reference, value, rel_tol=0.0, abs_tol=tolerance):
            raise ValueError(
                f"Contradictory {measurement} aliases: {reference_label}={reference:g} "
                f"and {label}={value:g} after unit conversion"
            )
    # Preserve the highest-priority explicit canonical value rather than
    # averaging measurements that may merely differ through unit rounding.
    return float(reference)


def validate_profile(profile: dict) -> dict:
    """Normalize and validate one adult physical profile.

    Height and mass are required and must use named units. Age is optional and
    unused by the v1 body-only model; a supplied age must describe an adult.
    Multiple unit aliases are accepted only when they agree within rounding
    tolerance.  Extreme positive measurements are returned unchanged with a
    warning; values are never clipped into the training range.
    """
    if not isinstance(profile, dict):
        raise TypeError("profile must be a dictionary of explicitly unit-labelled measurements")

    height_candidates: list[tuple[str, float]] = []
    if _provided(profile, "height_cm"):
        height_candidates.append(
            ("height_cm", _finite_number(profile["height_cm"], "height_cm"))
        )
    if _provided(profile, "height_inches"):
        total_inches = _finite_number(profile["height_inches"], "height_inches")
        height_candidates.append(("height_inches", total_inches * 2.54))

    has_feet = _provided(profile, "height_ft")
    has_inch_component = _provided(profile, "height_in")
    if has_feet != has_inch_component:
        raise ValueError("height_ft and height_in must be supplied together")
    if has_feet:
        feet = _finite_number(profile["height_ft"], "height_ft")
        inches = _finite_number(
            profile["height_in"], "height_in", positive=True, zero_allowed=True
        )
        if inches >= 12:
            raise ValueError("height_in must be the 0-to-under-12 inch component")
        height_candidates.append(("height_ft+height_in", (feet * 12.0 + inches) * 2.54))
    height_cm = _resolve_aliases(height_candidates, "height", tolerance=0.51)

    weight_candidates: list[tuple[str, float]] = []
    if _provided(profile, "weight_kg"):
        weight_candidates.append(
            ("weight_kg", _finite_number(profile["weight_kg"], "weight_kg"))
        )
    if _provided(profile, "weight_lb"):
        pounds = _finite_number(profile["weight_lb"], "weight_lb")
        weight_candidates.append(("weight_lb", pounds * 0.45359237))
    weight_kg = _resolve_aliases(weight_candidates, "weight", tolerance=0.26)

    age: float | None = None
    if _provided(profile, "age"):
        age = _finite_number(profile["age"], "age")
        if age < 18:
            raise ValueError("Adult-only model: age under 18 is unsupported")
        if age > 100:
            raise ValueError("age over 100 is outside the supported adult profile range")

    try:
        bmi = weight_kg / (height_cm / 100.0) ** 2
    except (OverflowError, ZeroDivisionError) as error:
        raise ValueError("Height/weight magnitude cannot produce a finite BMI; check units") from error
    if not math.isfinite(bmi) or bmi <= 0:
        raise ValueError("Height/weight magnitude cannot produce a finite positive BMI; check units")
    if _provided(profile, "bmi"):
        supplied_bmi = _finite_number(profile["bmi"], "bmi")
        if not math.isclose(bmi, supplied_bmi, rel_tol=0.0, abs_tol=0.1):
            raise ValueError(
                f"Contradictory bmi: supplied {supplied_bmi:g}, derived {bmi:.3f} from height and weight"
            )

    extras: dict[str, float] = {}
    for measurement in EXTRA_MEASUREMENTS:
        if _provided(profile, measurement):
            extras[measurement] = _finite_number(profile[measurement], measurement)

    warnings: list[str] = []
    if height_cm < 140 or height_cm > 230:
        warnings.append(
            f"height_cm={height_cm:.2f} is outside the broad adult-athlete plausibility band (140–230); "
            "the value was not clipped"
        )
    if weight_kg < 40 or weight_kg > 200:
        warnings.append(
            f"weight_kg={weight_kg:.2f} is outside the broad adult-athlete plausibility band (40–200); "
            "the value was not clipped"
        )
    if bmi < 14 or bmi > 45:
        warnings.append(
            f"derived bmi={bmi:.2f} is extreme for the reference cohorts; the value was not clipped"
        )
    if age is not None and age > 60:
        warnings.append(
            f"age={age:g} is far outside most elite-league training observations; the value was not clipped"
        )

    unsupported = sorted(str(key) for key in profile if key not in _RECOGNIZED_KEYS)
    return {
        "features": {
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "age": age,
            "bmi": bmi,
        },
        "provided_extra_measurements": extras,
        "warnings": warnings,
        "unsupported_features": unsupported,
    }
