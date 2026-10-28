"""Score known or user-supplied athletes with the native and transfer contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from possession_lab.all_roles_models import PHYSICAL_FEATURES, ood_diagnostics
from possession_lab.all_roles_paths import (
    observed_scores_missing_message,
    observed_scores_path,
)
from possession_lab.all_roles_pipeline import load_all_role_models
from possession_lab.all_roles_registry import role_specs


def _frame(profile: dict[str, Any] | pd.Series | pd.DataFrame) -> pd.DataFrame:
    if isinstance(profile, pd.DataFrame):
        if len(profile) != 1:
            raise ValueError("Score one athlete profile at a time")
        result = profile.copy()
    elif isinstance(profile, pd.Series):
        result = profile.to_frame().T
    elif isinstance(profile, dict):
        result = pd.DataFrame([profile])
    else:
        raise TypeError("profile must be a dictionary, Series or one-row DataFrame")
    for column in ["height_cm", "weight_kg", "age"]:
        if column not in result:
            result[column] = np.nan
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["bmi"] = result["weight_kg"] / (result["height_cm"] / 100.0) ** 2
    result.loc[~np.isfinite(result["bmi"]) | result["bmi"].le(0), "bmi"] = np.nan
    return result


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _model_score(
    head: dict,
    row: pd.DataFrame,
    *,
    kind: str,
    evidence_class: str,
    require_dimensions: bool = False,
    support_policy: str = "evidence_gate",
    enforce_target_proxy_reconstruction_gate: bool = False,
) -> dict:
    model = head.get("model")
    if model is None:
        return {
            "kind": kind,
            "status": "withheld_no_fitted_model",
            "value": None,
            "evidence_class": evidence_class,
            "reason": head.get("reason") or head.get("status"),
        }
    if row[list(PHYSICAL_FEATURES[:2])].isna().any(axis=None):
        return {
            "kind": kind,
            "status": "withheld_missing_height_or_weight",
            "value": None,
            "evidence_class": evidence_class,
        }
    dimension_features = [
        feature
        for feature in head["features"]
        if feature.startswith("dimension_") and feature.endswith("_percentile")
    ]
    if require_dimensions:
        missing = [feature for feature in dimension_features if _number(row.iloc[0].get(feature)) is None]
        if missing:
            return {
                "kind": kind,
                "status": "withheld_missing_required_dimensions",
                "value": None,
                "evidence_class": evidence_class,
                "missing_dimensions": missing,
            }
    forward_profile_gate = head.get(
        "target_role_forward_profile_gate",
        # Read compatibility for artifacts created before the semantics were renamed.
        head.get("target_proxy_reconstruction_gate", head.get("evidence_gate")),
    )
    if enforce_target_proxy_reconstruction_gate and forward_profile_gate != "supported":
        return {
            "kind": kind,
            "status": "withheld_target_role_forward_profile_failed_gate",
            "value": None,
            "evidence_class": "unvalidated_cross_sport_analogy",
            "target_role_forward_profile_status": head.get(
                "target_proxy_reconstruction_status"
            ),
            "target_role_forward_profile_gate": forward_profile_gate,
            # Compatibility aliases for older portal clients and saved exports.
            "target_proxy_reconstruction_status": head.get(
                "target_proxy_reconstruction_status"
            ),
            "target_proxy_reconstruction_gate": forward_profile_gate,
            "evidence_warning": (
                "Prior-season build plus the shared target-role profile did not pass its "
                "forward test against build alone; this gate is not cross-sport validation."
            ),
        }

    diagnostic = ood_diagnostics(row, head.get("reference", {}))
    if diagnostic["status"] == "out_of_domain":
        return {
            "kind": kind,
            "status": "withheld_out_of_domain",
            "value": None,
            "evidence_class": evidence_class,
            "ood": diagnostic,
            "features_used": list(head["features"]),
        }

    value = float(model.predict(row)[0])
    explanation = model.explain(row)[0]
    evidence_gate = head.get("evidence_gate")
    forecast_support = head.get("forecast_support")
    if support_policy == "native_forecast":
        supported = (
            evidence_gate == "supported"
            and forecast_support == "supported_over_history_baselines"
        )
        support_status = (
            "supported_over_neutral_and_history_baselines"
            if supported
            else "experimental_unsupported"
        )
        resolved_evidence_class = (
            "prospective_native_model_supported_over_neutral_and_history_baselines"
            if supported
            else "experimental_unsupported_native_forecast"
        )
        evidence_warning = (
            "Supported against both the neutral and declared history comparators."
            if supported
            else "The numeric estimate is experimental because it did not clear both the "
            "neutral and declared history comparison gates."
        )
    elif support_policy == "native_profile":
        profile_increment_gate = head.get("profile_increment_gate")
        supported = (
            evidence_gate == "supported" and profile_increment_gate == "supported"
        )
        support_status = (
            "supported_profile_increment" if supported else "experimental_unsupported"
        )
        resolved_evidence_class = (
            "native_forward_profile_supported_over_build_only"
            if supported
            else "experimental_native_forward_profile"
        )
        evidence_warning = (
            "The canonical playing profile improved next-season prediction over build alone."
            if supported
            else "This build-plus-profile estimate is experimental because the playing-profile "
            "increment did not clear, or lacked evidence for, the build-only comparison gate."
        )
    elif support_policy == "target_role_forward_profile":
        support_status = "experimental_forward_profile_passed_not_cross_sport_validated"
        resolved_evidence_class = (
            "unvalidated_cross_sport_analogy_forward_target_role_profile_only"
        )
        evidence_warning = (
            "The gate supports only a within-target-role next-season profile test over "
            "build alone; it is not cross-sport validation."
        )
    else:
        supported = evidence_gate == "supported"
        support_status = (
            "association_gate_supported" if supported else "experimental_unsupported"
        )
        resolved_evidence_class = (
            "physical_association_supported_against_neutral_baseline_only"
            if supported
            else "experimental_unsupported_physical_association"
        )
        evidence_warning = (
            "This supports a target-role physical association only; it is not cross-sport "
            "validation."
            if supported
            else "The numeric estimate is experimental because the physical association "
            "did not pass, or lacked evidence for, its baseline gate."
        )
    output = {
        "kind": kind,
        "status": "available",
        "value": value,
        "evidence_class": resolved_evidence_class,
        "support_status": support_status,
        "evidence_warning": evidence_warning,
        "features_used": list(head["features"]),
        "top_contributions": explanation[:5],
        "ood": diagnostic,
        "reference_rows": int(model.training_rows),
    }
    if support_policy == "target_role_forward_profile":
        output["target_role_forward_profile_gate"] = forward_profile_gate
        output["target_role_forward_profile_status"] = head.get(
            "target_proxy_reconstruction_status"
        )
        # Compatibility aliases for older portal clients and saved exports.
        output["target_proxy_reconstruction_gate"] = forward_profile_gate
        output["target_proxy_reconstruction_status"] = head.get(
            "target_proxy_reconstruction_status"
        )
    else:
        output["evidence_gate"] = evidence_gate
        output["evaluation_status"] = head.get("status")
    if support_policy == "native_forecast":
        output["forecast_support"] = forecast_support
        output["deployment_support"] = support_status
        output["selected_model_family"] = head.get("selected_model_family")
        output["team_context"] = {
            "selected": bool(head.get("context_model_selected", False)),
            "version": head.get("context_version"),
            "features": list(head.get("context_features", [])),
            "increment_gate": head.get("context_increment_gate"),
            "selection_reason": head.get("context_selection_reason"),
            "coverage": head.get("context_coverage", {}),
        }
    elif support_policy == "native_profile":
        output["profile_increment_gate"] = head.get("profile_increment_gate")
        output["deployment_support"] = support_status
        pooling = head.get("partial_pooling", {})
        output["selected_model_family"] = head.get("selected_model_family")
        output["partial_pooling"] = {
            "status": pooling.get("status"),
            "family": pooling.get("family"),
            "gate": pooling.get("gate"),
            "selected_tau": pooling.get("selected_tau"),
            "role_weight": pooling.get("deployment_role_weight"),
            "family_weight": pooling.get("deployment_family_weight"),
            "reason": pooling.get("reason"),
        }
    if value <= 1.0 or value >= 99.0:
        output["saturation_warning"] = (
            "Estimate is at or near the bounded 0–100 output limit and may reflect model "
            "clipping; differences beyond the boundary are not measurable."
        )
    interval = head.get("prediction_interval", {})
    interval_radius = _number(interval.get("half_width"))
    output["prediction_range_status"] = interval.get(
        "status", "unavailable_in_saved_model"
    )
    if interval_radius is not None and interval_radius >= 0:
        empirical_coverage = _number(interval.get("frozen_empirical_coverage"))
        output["prediction_range_90"] = {
            "lower": max(0.0, value - interval_radius),
            "upper": min(100.0, value + interval_radius),
            "half_width": interval_radius,
            "nominal_coverage": _number(interval.get("nominal_coverage")),
            "method": interval.get("method"),
            "calibration_athletes": interval.get("calibration_athletes"),
            "frozen_empirical_coverage": empirical_coverage,
        }
        output["uncertainty_warning"] = (
            "This rolling-origin residual range describes target-role forecast error. It is "
            "not a probability that an athlete will successfully change sports and may not "
            "retain its nominal coverage under distribution shift."
        )
        if empirical_coverage is not None and empirical_coverage < 0.80:
            output["interval_calibration_warning"] = (
                "The nominal 90% range covered fewer than 80% of frozen-test outcomes; "
                "treat it as poorly calibrated for this model head."
            )
    residual = _number(
        head.get("target_proxy_residual_mae")
        if support_policy == "target_role_forward_profile"
        else head.get("frozen_residual_mae")
    )
    if residual is not None and "cross_sport" in kind:
        output["analogy_sensitivity_range"] = [
            max(0.0, value - residual),
            min(100.0, value + residual),
        ]
        if support_policy == "target_role_forward_profile":
            output["sensitivity_basis"] = "target_role_forward_profile_frozen_test_mae"
            output["range_warning"] = (
                "Sensitivity band from the target role's forward-profile frozen-test MAE; "
                "not a calibrated confidence interval."
            )
        else:
            output["sensitivity_basis"] = "physical_model_frozen_test_mae"
            output["range_warning"] = (
                "Sensitivity band from the target-role physical model's frozen-test MAE; "
                "not a calibrated confidence interval."
            )
    return output


def score_all_roles_profile(
    artifact: dict,
    profile: dict[str, Any] | pd.Series | pd.DataFrame,
    *,
    target_sport: str | None = None,
) -> dict:
    row = _frame(profile)
    source_sport = str(row.iloc[0].get("sport") or "")
    source_role = str(row.iloc[0].get("role") or "")
    source_key = f"{source_sport}:{source_role}" if source_sport and source_role else None
    season = _number(row.iloc[0].get("season"))
    name = row.iloc[0].get("name")
    player_id = row.iloc[0].get("player_id")
    raw_target_status = row.iloc[0].get("target_status")
    source_target_status = (
        "unknown" if pd.isna(raw_target_status) else str(raw_target_status)
    )

    observed = None
    if source_key:
        observed = {
            "kind": "observed_role_percentile",
            "status": source_target_status,
            "value": _number(row.iloc[0].get("observed_role_percentile")),
            "quality_percentile": _number(row.iloc[0].get("quality_percentile")),
            "availability_percentile": _number(row.iloc[0].get("availability_percentile")),
            "total_impact_percentile": _number(row.iloc[0].get("total_impact_percentile")),
            "sustained_3y_percentile": _number(row.iloc[0].get("sustained_3y_percentile")),
            "reference_athletes": _number(row.iloc[0].get("reference_athletes")),
            "opportunity_reliability": _number(
                row.iloc[0].get("opportunity_reliability")
            ),
            "component_coverage_fraction": _number(
                row.iloc[0].get("component_coverage_fraction")
            ),
            "domain_coverage_fraction": _number(
                row.iloc[0].get("domain_coverage_fraction")
            ),
            "evidence_class": "observed_native_role_season",
        }

    native_forecast = None
    if source_key:
        head = artifact["native_forecast_models"].get(source_key, {})
        if source_target_status != "eligible":
            native_forecast = {
                "kind": "native_forecast_percentile",
                "status": "withheld_source_performance_not_eligible",
                "value": None,
                "evidence_class": "prospective_native_model",
                "source_target_status": source_target_status,
                "reason": "Native forecast training requires an eligible prior-season row.",
            }
        else:
            native_forecast = _model_score(
                head,
                row,
                kind="native_forecast_percentile",
                evidence_class="prospective_native_model",
                require_dimensions=True,
                support_policy="native_forecast",
            )
        native_forecast["target_season"] = int(season + 1) if season is not None else None
        native_forecast["forecast_support"] = head.get("forecast_support")

    native_profile_forecast = None
    if source_key and "native_profile_models" in artifact:
        profile_head = artifact["native_profile_models"].get(source_key, {})
        if source_target_status != "eligible":
            native_profile_forecast = {
                "kind": "native_build_profile_forecast_percentile",
                "status": "withheld_source_performance_not_eligible",
                "value": None,
                "evidence_class": "native_forward_transferable_profile_benchmark",
                "source_target_status": source_target_status,
                "reason": (
                    "The forward build-plus-profile benchmark requires an eligible "
                    "prior-season row."
                ),
            }
        else:
            native_profile_forecast = _model_score(
                profile_head,
                row,
                kind="native_build_profile_forecast_percentile",
                evidence_class="native_forward_transferable_profile_benchmark",
                require_dimensions=True,
                support_policy="native_profile",
            )
        native_profile_forecast["target_season"] = (
            int(season + 1) if season is not None else None
        )
        native_profile_forecast["profile_increment_gate"] = profile_head.get(
            "profile_increment_gate"
        )

    targets: dict[str, dict] = {}
    specs = role_specs()
    sports = [target_sport] if target_sport else ["nfl", "nba", "nhl", "epl"]
    for sport in sports:
        role_results = {}
        for target_key, spec in specs.items():
            if spec.sport != sport:
                continue
            physical = _model_score(
                artifact["physical_models"].get(target_key, {}),
                row,
                kind="cross_sport_physical_estimate",
                evidence_class="physical_association_only",
            )
            transfer = {
                "kind": "cross_sport_transfer_guesstimate",
                "status": "not_applicable_without_source_performance",
                "value": None,
                "evidence_class": "unvalidated_cross_sport_analogy",
            }
            if source_key and source_sport != sport:
                bridge_key = f"{source_key}->{target_key}"
                head = artifact["bridge_models"].get(bridge_key, {})
                if source_target_status != "eligible":
                    transfer = {
                        "kind": "cross_sport_transfer_guesstimate",
                        "status": "withheld_source_performance_not_eligible",
                        "value": None,
                        "evidence_class": "unvalidated_cross_sport_analogy",
                        "source_target_status": source_target_status,
                        "reason": (
                            "Transfer dimensions require an eligible observed source-season."
                        ),
                    }
                else:
                    transfer = _model_score(
                        head,
                        row,
                        kind="cross_sport_transfer_guesstimate",
                        evidence_class="unvalidated_cross_sport_analogy",
                        require_dimensions=True,
                        support_policy="target_role_forward_profile",
                        enforce_target_proxy_reconstruction_gate=True,
                    )
                transfer["dimensions"] = head.get("dimensions", [])
                transfer["semantic_bridge_grade"] = head.get("semantic_bridge_grade")
                transfer["mapping_version"] = artifact.get("bridge_version")
            role_results[spec.role] = {
                "label": spec.label,
                "evidence_status": spec.evidence_status,
                "limitation": spec.limitation,
                "physical_only": physical,
                "transfer_guesstimate": transfer,
            }
        targets[sport] = {"roles": role_results}

    return {
        "player": {
            "sport": source_sport or None,
            "player_id": str(player_id) if player_id is not None else None,
            "name": str(name) if name is not None else "Custom athlete",
            "season": int(season) if season is not None else None,
            "role": source_role or None,
            "height_cm": _number(row.iloc[0].get("height_cm")),
            "weight_kg": _number(row.iloc[0].get("weight_kg")),
            "age": _number(row.iloc[0].get("age")),
        },
        "native": {
            "observed": observed,
            "forecast": native_forecast,
            "build_profile_forecast": native_profile_forecast,
        },
        "targets": targets,
        "claims": artifact["claims"],
    }


def load_known_player(
    root: Path | str,
    sport: str,
    player_id: str,
    *,
    season: int | None = None,
) -> pd.Series:
    path = observed_scores_path(root)
    if not path.exists():
        raise FileNotFoundError(observed_scores_missing_message(root, path))
    source = pd.read_parquet(path)
    rows = source.loc[
        source["sport"].eq(sport) & source["player_id"].astype(str).eq(str(player_id))
    ]
    if season is not None:
        rows = rows.loc[rows["season"].eq(int(season))]
    if rows.empty:
        raise ValueError(f"Unknown player-season: {sport}:{player_id}:{season or 'latest'}")
    return rows.sort_values("season").iloc[-1]


def score_known_player(
    root: Path | str,
    sport: str,
    player_id: str,
    *,
    season: int | None = None,
    target_sport: str | None = None,
) -> dict:
    root = Path(root)
    artifact = load_all_role_models(root)
    player = load_known_player(root, sport, player_id, season=season)
    return score_all_roles_profile(artifact, player, target_sport=target_sport)
