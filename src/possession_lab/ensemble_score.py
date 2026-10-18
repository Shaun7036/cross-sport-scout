"""Pure inference for the cross-sport physical efficacy ensemble.

Loading and integrity-checking model artifacts belongs to the caller.  This
module deliberately accepts an already loaded artifact so the same scoring
logic can be used by the command line, tests, and a future application.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from possession_lab.ensemble_features import validate_profile

SCHEMA = "possession_lab.cross_sport_efficacy_score"
MODEL_FEATURES = ("height_cm", "weight_kg")
EXPERT_KEYS = ("archetype", "ridge", "hist_gradient_boosting", "extra_trees")
OOD_MAHALANOBIS_SQUARED = 9.21034  # 99th percentile of chi-square(df=2).

_INTERPRETATION = (
    "Role-relative estimate of possession/disruption efficacy associated with height and mass "
    "among observed elite athletes. It is not a probability of making a roster, overall defensive "
    "quality, or evidence that an athlete can transfer successfully between sports."
)


def _spec_field(spec: object, field: str) -> str:
    if isinstance(spec, Mapping):
        value = spec.get(field)
    else:
        value = getattr(spec, field, None)
    if value is None:
        raise ValueError(f"Head spec is missing {field!r}")
    return str(value)


def _finite_vector(value: object, *, name: str, length: int) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if result.shape != (length,) or not np.isfinite(result).all():
        raise ValueError(f"{name} must contain {length} finite values")
    return result


def _finite_matrix(value: object, *, name: str, shape: tuple[int, int]) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError(f"{name} must be a finite {shape[0]}x{shape[1]} matrix")
    return result


def _one_prediction(model: object, frame: pd.DataFrame, *, label: str) -> float:
    if not hasattr(model, "predict"):
        raise ValueError(f"{label} does not provide predict()")
    values = np.asarray(model.predict(frame), dtype=float).reshape(-1)
    if values.size != 1 or not np.isfinite(values[0]):
        raise ValueError(f"{label} returned a non-finite or non-scalar prediction")
    return float(values[0])


def _summary_evidence(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the audit fields needed to interpret why a role is supported."""
    fields = (
        "train_athletes",
        "calibration_athletes",
        "test_athletes",
        "evaluation",
        "metrics",
        "evidence_grade",
        "nested_cv",
        "mse_improvement_cluster_bootstrap",
        "target_weight_sensitivity",
        "improvement_statistically_established",
        "abstention_reasons",
        "interval_diagnostic",
    )
    evidence = {field: _json_safe(summary[field]) for field in fields if field in summary}
    seasons = summary.get("target", {}).get("seasons", {})
    if seasons:
        evidence["reference_seasons"] = sorted(seasons)
        evidence["target_definition"] = _json_safe(seasons[max(seasons)])
    return evidence


def _json_safe(value: Any) -> Any:
    """Convert numpy containers and non-finite diagnostics to JSON-safe values."""
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def _body_diagnostics(body_reference: Mapping[str, Any], body: np.ndarray) -> dict[str, Any]:
    center = _finite_vector(body_reference.get("center"), name="body_reference.center", length=2)
    inverse = _finite_matrix(
        body_reference.get("inverse_covariance"),
        name="body_reference.inverse_covariance",
        shape=(2, 2),
    )
    lower = _finite_vector(body_reference.get("lower"), name="body_reference.lower", length=2)
    upper = _finite_vector(body_reference.get("upper"), name="body_reference.upper", length=2)
    if np.any(lower > upper):
        raise ValueError("body_reference.lower cannot exceed body_reference.upper")

    delta = body - center
    # A pseudo-inverse can produce a negligible negative value through floating
    # point error. A materially negative quadratic form is an invalid artifact.
    distance = float(delta @ inverse @ delta)
    if distance < -1e-8:
        raise ValueError("body_reference.inverse_covariance produced a negative squared distance")
    distance = max(distance, 0.0)
    outside_bounds = bool(np.any(body < lower) or np.any(body > upper))
    beyond_distance = distance > OOD_MAHALANOBIS_SQUARED

    reference_distances = np.asarray(body_reference.get("distances", []), dtype=float).reshape(-1)
    reference_distances = reference_distances[np.isfinite(reference_distances) & (reference_distances >= 0)]
    if reference_distances.size:
        # Survival percentile: central profiles score highly; profiles at or
        # beyond every reference distance score zero.
        cdf = np.searchsorted(np.sort(reference_distances), distance, side="right")
        physical_fit: float | None = float(100.0 * (1.0 - cdf / reference_distances.size))
    else:
        physical_fit = None

    return {
        "mahalanobis_distance_squared": distance,
        "physical_fit": physical_fit,
        "outside_training_bounds": outside_bounds,
        "beyond_distance_threshold": bool(beyond_distance),
        "out_of_domain": bool(outside_bounds or beyond_distance),
        "training_bounds": {
            "height_cm": [float(lower[0]), float(upper[0])],
            "weight_kg": [float(lower[1]), float(upper[1])],
        },
    }


def _stack_predictions(
    artifact: Mapping[str, Any],
    head: Mapping[str, Any],
    frame: pd.DataFrame,
    body: np.ndarray,
) -> tuple[float, float, dict[str, float], dict[str, float]]:
    experts = head.get("experts")
    if not isinstance(experts, Mapping):
        raise ValueError("Fitted head is missing its experts mapping")
    missing = [name for name in EXPERT_KEYS if name not in experts]
    if missing:
        raise ValueError(f"Fitted head is missing experts: {missing}")

    predictions = {"baseline50": 50.0}
    for name in EXPERT_KEYS:
        predictions[name] = float(
            np.clip(_one_prediction(experts[name], frame, label=f"expert {name}"), 0.0, 100.0)
        )

    shared = artifact.get("shared_expert")
    center = _finite_vector(head.get("shared_center"), name="shared_center", length=2)
    scale = _finite_vector(head.get("shared_scale"), name="shared_scale", length=2)
    if np.any(scale <= 0):
        raise ValueError("shared_scale must contain two positive values")
    z = (body - center) / scale
    predictions["shared"] = float(
        np.clip(
            _one_prediction(
                shared,
                pd.DataFrame([z], columns=MODEL_FEATURES),
                label="shared_expert",
            ),
            0.0,
            100.0,
        )
    )

    supplied_weights = head.get("stack_weights")
    if not isinstance(supplied_weights, Mapping):
        raise ValueError("Fitted head is missing stack_weights")
    if "shared" not in supplied_weights and "shared_expert" in supplied_weights:
        supplied_weights = {**supplied_weights, "shared": supplied_weights["shared_expert"]}
    component_names = ("baseline50", *EXPERT_KEYS, "shared")
    weights = np.asarray([supplied_weights.get(name, 0.0) for name in component_names], dtype=float)
    if not np.isfinite(weights).all() or np.any(weights < -1e-10):
        raise ValueError("stack_weights must be finite and non-negative")
    weights = np.maximum(weights, 0.0)
    if weights.sum() <= 0:
        raise ValueError("stack_weights must have positive total weight")
    weights /= weights.sum()
    normalized_weights = dict(zip(component_names, weights.tolist()))
    stack_estimate = float(sum(normalized_weights[name] * predictions[name] for name in component_names))
    stack_estimate = float(np.clip(stack_estimate, 0.0, 100.0))

    selected_method = str(head.get("selected_method", ""))
    if selected_method == "stack":
        selected_estimate = stack_estimate
    elif selected_method == "baseline":
        selected_estimate = 50.0
    else:
        raise ValueError("selected_method must be 'stack' or 'baseline'")
    return selected_estimate, stack_estimate, predictions, normalized_weights


def _interval(estimate: float, radius_value: object) -> tuple[list[float], float | None, bool]:
    try:
        radius = float(radius_value)
    except (TypeError, ValueError) as error:
        raise ValueError("calibration_radius must be a non-negative number") from error
    if radius < 0 or np.isnan(radius):
        raise ValueError("calibration_radius must be a non-negative number")
    if np.isinf(radius):
        return [0.0, 100.0], None, True
    return (
        [float(np.clip(estimate - radius, 0.0, 100.0)), float(np.clip(estimate + radius, 0.0, 100.0))],
        radius,
        False,
    )


def _unsupported_role(role: str, summary: Mapping[str, Any]) -> dict[str, Any]:
    status = str(summary.get("status", "insufficient_support"))
    return {
        "role": role,
        "status": status,
        "score_label": "unsupported: no fitted efficacy model",
        "efficacy_rating": None,
        "experimental_estimate": None,
        "interval": None,
        "physical_fit": None,
        "mahalanobis_distance_squared": None,
        "out_of_domain": None,
        "archetype": None,
        "expert_weights": None,
        "explanation": (
            "This role did not have enough eligible athlete evidence to fit and evaluate a model; "
            "no estimate was generated."
        ),
        "evidence": _summary_evidence(summary),
    }


def _score_role(
    artifact: Mapping[str, Any],
    key: str,
    head: Mapping[str, Any],
    frame: pd.DataFrame,
    body: np.ndarray,
) -> tuple[dict[str, Any], list[str]]:
    spec = head.get("spec")
    role = _spec_field(spec, "role")
    summary = head.get("summary", {})
    if not isinstance(summary, Mapping):
        raise ValueError(f"{key} summary must be a mapping")
    status = str(summary.get("status", "insufficient_support"))
    if status == "insufficient_support" or "experts" not in head:
        return _unsupported_role(role, summary), []
    if status not in {"evidence_supported", "no_evidence"}:
        raise ValueError(f"{key} has unrecognized summary status {status!r}")

    reference = head.get("body_reference")
    if not isinstance(reference, Mapping):
        raise ValueError(f"{key} is missing body_reference")
    physical = _body_diagnostics(reference, body)
    selected, stack_estimate, expert_predictions, expert_weights = _stack_predictions(
        artifact, head, frame, body
    )
    interval, radius, unbounded = _interval(selected, head.get("calibration_radius"))

    archetype_model = head["experts"]["archetype"]
    if not hasattr(archetype_model, "describe"):
        raise ValueError(f"{key} archetype expert does not provide describe()")
    descriptions = archetype_model.describe(frame)
    if not isinstance(descriptions, list) or len(descriptions) != 1:
        raise ValueError(f"{key} archetype describe() must return one explanation")

    publishable = status == "evidence_supported" and not physical["out_of_domain"]
    role_warnings: list[str] = []
    if physical["out_of_domain"]:
        reasons = []
        if physical["outside_training_bounds"]:
            reasons.append("outside the observed height/weight bounds")
        if physical["beyond_distance_threshold"]:
            reasons.append("beyond the 99% body-profile distance threshold")
        reason = " and ".join(reasons)
        role_warnings.append(
            f"{key}: profile is {reason}; the estimate is an unsupported extrapolation and the "
            "primary efficacy rating is withheld."
        )
    if status == "no_evidence":
        role_warnings.append(
            f"{key}: predictive-evidence or independent-sample checks failed; "
            "the primary efficacy rating is withheld."
        )
        role_warnings.extend(f"{key}: {reason}" for reason in summary.get("abstention_reasons", []))
    bootstrap = summary.get("mse_improvement_cluster_bootstrap", {})
    lower = bootstrap.get("lower95")
    if lower is not None and lower <= 0:
        role_warnings.append(
            f"{key}: bootstrap 95% improvement interval includes zero; efficacy is not statistically established."
        )
    coverage = summary.get("metrics", {}).get("interval_90_empirical_coverage")
    if coverage is not None and coverage < 0.8:
        role_warnings.append(
            f"{key}: nominal 90% interval covered only {100 * coverage:.1f}% of test athletes. Treat the displayed interval as poorly calibrated."
        )

    if publishable:
        score_label = "provisional role-relative estimate"
        explanation = (
            "Exploratory held-out point checks passed and the profile is within the body domain. "
            "This does not establish improvement statistically or validate sport switching; inspect bootstrap evidence and interval coverage."
        )
    elif physical["out_of_domain"]:
        score_label = "experimental out-of-domain estimate"
        explanation = (
            "The experimental estimate and interval are shown for transparency, but extrapolation "
            "outside the observed body domain is not promoted as an efficacy rating."
        )
    else:
        score_label = "experimental estimate; evidence gate failed"
        explanation = (
            "The estimate and interval are shown for transparency, but held-out evaluation did not "
            "establish predictive evidence beyond the neutral 50 baseline."
        )

    result = {
        "role": role,
        "status": status,
        "score_label": score_label,
        "efficacy_rating": selected if publishable else None,
        "experimental_estimate": selected,
        "interval": interval,
        "calibration_radius": radius,
        "interval_is_unbounded": unbounded,
        "stack_estimate": stack_estimate,
        "physical_fit": physical["physical_fit"],
        "mahalanobis_distance_squared": physical["mahalanobis_distance_squared"],
        "out_of_domain": physical["out_of_domain"],
        "outside_training_bounds": physical["outside_training_bounds"],
        "beyond_distance_threshold": physical["beyond_distance_threshold"],
        "training_bounds": physical["training_bounds"],
        "archetype": _json_safe(descriptions[0]),
        "expert_weights": expert_weights,
        "expert_predictions": {name: float(value) for name, value in expert_predictions.items()},
        "selected_method": str(head["selected_method"]),
        "explanation": explanation,
        "evidence": _summary_evidence(summary),
    }
    return result, role_warnings


def score_ensemble(artifact: dict, profile: dict, sport: str = "all") -> dict:
    """Score one unit-labelled physical profile across fitted sport-role heads.

    Primary ratings are intentionally withheld for unsupported, unvalidated, or
    out-of-domain heads. Experimental estimates remain visible so users can
    audit what the fitted ensemble produced without mistaking extrapolation for
    evidence.
    """
    if not isinstance(artifact, Mapping):
        raise TypeError("artifact must be a loaded ensemble artifact dictionary")
    if "version" not in artifact:
        raise ValueError("artifact is missing version")
    features = tuple(artifact.get("features", ()))
    if features != MODEL_FEATURES:
        raise ValueError(
            "This scorer requires the v1 feature contract ['height_cm', 'weight_kg']; "
            f"artifact declared {list(features)!r}"
        )
    heads = artifact.get("heads")
    if not isinstance(heads, Mapping):
        raise ValueError("artifact is missing its heads mapping")

    validated = validate_profile(profile)
    used = {name: float(validated["features"][name]) for name in MODEL_FEATURES}
    body = np.asarray([used[name] for name in MODEL_FEATURES], dtype=float)
    frame = pd.DataFrame([used], columns=MODEL_FEATURES)

    grouped: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for key, head in heads.items():
        if not isinstance(head, Mapping):
            raise ValueError(f"Head {key!r} must be a mapping")
        head_sport = _spec_field(head.get("spec"), "sport").lower()
        grouped.setdefault(head_sport, []).append((str(key), head))

    requested = str(sport).lower()
    if requested == "all":
        selected_sports = sorted(grouped)
    elif requested in grouped:
        selected_sports = [requested]
    else:
        available = ", ".join(sorted(grouped)) or "none"
        raise ValueError(f"Unknown or unavailable sport {sport!r}; available sports: {available}")

    unused: dict[str, Any] = {
        "age": {
            "value": validated["features"]["age"],
            "reason": "recorded for provenance but unused by the v1 height/mass ensemble",
        },
        "bmi": {
            "value": float(validated["features"]["bmi"]),
            "reason": "derived for provenance but excluded to avoid duplicating height and mass",
        },
    }
    for name, value in validated["provided_extra_measurements"].items():
        unused[name] = {
            "value": float(value),
            "reason": "recognized measurement without consistent cross-sport training coverage in v1",
        }
    for name in validated["unsupported_features"]:
        unused[name] = {"value": None, "reason": "unrecognized input field"}

    warnings = list(validated["warnings"])
    if validated["features"]["age"] is not None:
        warnings.append("Age was recorded but is not used by the v1 efficacy ensemble.")
    if validated["provided_extra_measurements"]:
        names = ", ".join(sorted(validated["provided_extra_measurements"]))
        warnings.append(f"Recognized measurements not used by v1: {names}.")
    if validated["unsupported_features"]:
        names = ", ".join(validated["unsupported_features"])
        warnings.append(f"Unrecognized profile fields were ignored: {names}.")
    if artifact.get("fast_development_fit"):
        warnings.append(
            "This artifact is a fast development fit with reduced expert training; "
            "its scores are for pipeline checks, not substantive use."
        )

    sport_results: dict[str, Any] = {}
    for sport_name in selected_sports:
        role_results = []
        for key, head in sorted(
            grouped[sport_name], key=lambda item: _spec_field(item[1].get("spec"), "role")
        ):
            role_result, role_warnings = _score_role(artifact, key, head, frame, body)
            role_results.append(role_result)
            warnings.extend(role_warnings)

        ranked = sorted(
            (role for role in role_results if role["efficacy_rating"] is not None),
            key=lambda role: (-role["efficacy_rating"], role["role"]),
        )
        best = ranked[0] if ranked else None
        # Physical fit is diagnostic only and is deliberately absent from this
        # ordering; it must not turn body similarity into a success estimate.
        role_results.sort(
            key=lambda role: (
                role["efficacy_rating"] is None,
                -(role["efficacy_rating"] if role["efficacy_rating"] is not None else -1.0),
                role["role"],
            )
        )
        sport_results[sport_name] = {
            "best_role": best["role"] if best else None,
            "efficacy_rating": best["efficacy_rating"] if best else None,
            "status": "scored" if best else "no_evidence_supported_in_domain_role",
            "roles": role_results,
        }

    return {
        "schema": SCHEMA,
        "version": _json_safe(artifact["version"]),
        "interpretation": _INTERPRETATION,
        "sport_selection": "Highest supported in-domain role estimate; this maximum has no separate sport-level calibration and is not a validated cross-sport ranking.",
        "measurement_timing": "Reference height/weight are often undated/current snapshots; this is descriptive association, not a historical or preseason forecast.",
        "interval_interpretation": "Provisional 90% individual activity-target prediction interval, not a confidence interval on the mean or a success probability; not simultaneous across roles.",
        "trained_at": _json_safe(artifact.get("trained_at")),
        "features_used": used,
        "features_unused": unused,
        "warnings": warnings,
        "sports": sport_results,
    }
