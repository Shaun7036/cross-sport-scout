"""Score known or user-supplied athletes with the four-score contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from possession_lab.all_roles_models import PHYSICAL_FEATURES, ood_diagnostics
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
    proxy_gate = head.get(
        "target_proxy_reconstruction_gate",
        # Read compatibility for artifacts created before the semantics were renamed.
        head.get("evidence_gate"),
    )
    if enforce_target_proxy_reconstruction_gate and proxy_gate != "supported":
        return {
            "kind": kind,
            "status": "withheld_target_proxy_reconstruction_failed_gate",
            "value": None,
            "evidence_class": "unvalidated_cross_sport_analogy",
            "target_proxy_reconstruction_status": head.get(
                "target_proxy_reconstruction_status"
            ),
            "target_proxy_reconstruction_gate": proxy_gate,
            "evidence_warning": (
                "The within-target-role reconstruction did not pass its gate; this gate is "
                "not cross-sport validation."
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
    elif support_policy == "target_proxy_reconstruction":
        support_status = "experimental_target_proxy_passed_not_cross_sport_validated"
        resolved_evidence_class = (
            "unvalidated_cross_sport_analogy_target_proxy_reconstruction_only"
        )
        evidence_warning = (
            "The gate supports only within-target-role proxy reconstruction; it is not "
            "cross-sport validation."
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
    if support_policy == "target_proxy_reconstruction":
        output["target_proxy_reconstruction_gate"] = proxy_gate
        output["target_proxy_reconstruction_status"] = head.get(
            "target_proxy_reconstruction_status"
        )
    else:
        output["evidence_gate"] = evidence_gate
        output["evaluation_status"] = head.get("status")
    if support_policy == "native_forecast":
        output["forecast_support"] = forecast_support
        output["deployment_support"] = support_status
    if value <= 1.0 or value >= 99.0:
        output["saturation_warning"] = (
            "Estimate is at or near the bounded 0–100 output limit and may reflect model "
            "clipping; differences beyond the boundary are not measurable."
        )
    residual = _number(
        head.get("target_proxy_residual_mae")
        if support_policy == "target_proxy_reconstruction"
        else head.get("frozen_residual_mae")
    )
    if residual is not None and "cross_sport" in kind:
        output["analogy_sensitivity_range"] = [
            max(0.0, value - residual),
            min(100.0, value + residual),
        ]
        if support_policy == "target_proxy_reconstruction":
            output["sensitivity_basis"] = "target_proxy_frozen_test_mae"
            output["range_warning"] = (
                "Sensitivity band from target-proxy frozen-test MAE; not a calibrated "
                "confidence interval."
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
                        support_policy="target_proxy_reconstruction",
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
        "native": {"observed": observed, "forecast": native_forecast},
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
    path = Path(root) / "data" / "processed" / "all_roles" / "observed_scores.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Build observed all-role scores first: {path}")
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
