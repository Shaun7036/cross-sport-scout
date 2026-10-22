"""Small, deterministic exports for the plain-language model report.

The browser pages intentionally consume aggregate, versioned evidence rather
than row-level player data.  Re-run this module after rebuilding either model
family so the report and the saved artifacts stay in sync.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from possession_lab.all_roles_context import CONTEXT_FEATURES, CONTEXT_VERSION

SPORTS = {
    "nfl": "NFL",
    "nba": "NBA",
    "nhl": "NHL",
    "epl": "Premier League",
}

DIMENSIONS = {
    "scoring_finishing": (
        "Scoring and finishing",
        "Turning chances or possessions into points and goals.",
    ),
    "creation_distribution": (
        "Creation and distribution",
        "Creating useful chances or moving possession to teammates.",
    ),
    "possession_security": (
        "Possession security",
        "Avoiding costly losses and protecting possession or field position.",
    ),
    "defensive_disruption": (
        "Defensive disruption",
        "Interrupting an opponent through pressure, stops, takeaways or prevention.",
    ),
    "recovery_rebounding": (
        "Recovery and rebounding",
        "Regaining control after a contest, shot or loose-ball event.",
    ),
    "progression_territory": (
        "Progression and territory",
        "Moving play toward a valuable area or improving field position.",
    ),
    "discipline_efficiency": (
        "Discipline and efficiency",
        "Producing useful outcomes while limiting avoidable errors or penalties.",
    ),
}

CONTEXT_FIELD_GUIDE = {
    "context_role_opportunity_share_percentile": {
        "label": "Share of the team's role opportunity",
        "description": (
            "The player's share of opportunity among teammates in the same broad role, "
            "then ranked against the same role and season. It describes workload and role "
            "share, not how well the player performed."
        ),
    },
    "context_team_peer_strength_percentile": {
        "label": "Strength of the other teammates",
        "description": (
            "The reliability-weighted role percentiles of the player's other teammates, "
            "then ranked within the same role and season. The player is left out of their "
            "own team-strength calculation."
        ),
    },
}


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _words(value: str) -> str:
    return value.replace("_", " ").strip().title()


def _context_coverage_rows(root: Path) -> list[dict[str, Any]]:
    path = root / "reports" / "all_roles" / "context_coverage.csv"
    if not path.exists():
        return []
    integer_fields = {"total_rows", "context_available_rows"}
    integer_fields.update(f"{feature}_available_rows" for feature in CONTEXT_FEATURES)
    float_fields = {"context_available_fraction"}
    float_fields.update(f"{feature}_coverage" for feature in CONTEXT_FEATURES)
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for source in csv.DictReader(handle):
            row: dict[str, Any] = dict(source)
            for field in integer_fields:
                if row.get(field) not in (None, ""):
                    row[field] = int(row[field])
            for field in float_fields:
                if row.get(field) not in (None, ""):
                    row[field] = float(row[field])
            rows.append(row)
    return rows


def build_feature_payload(root: Path) -> dict[str, Any]:
    registry = _read_json(root / "metadata" / "all_roles_metric_registry.json")
    data_build = _read_json(root / "reports" / "all_roles" / "data_build.json")
    evaluation = _read_json(root / "reports" / "all_roles" / "model_evaluation.json")
    sport_roles: dict[str, list[dict[str, Any]]] = defaultdict(list)
    used_dimensions: set[str] = set()

    for key, role in registry["roles"].items():
        domains = []
        for domain in role["domains"]:
            used_dimensions.add(domain["dimension"])
            metrics = []
            for metric in domain["metrics"]:
                metrics.append(
                    {
                        "id": metric["column"],
                        "label": _words(metric["column"]),
                        "weight": metric["weight"],
                        "higher_is_better": metric["higher_is_better"],
                        "direction": (
                            "Higher values support this domain."
                            if metric["higher_is_better"]
                            else "Lower values support this domain."
                        ),
                    }
                )
            domains.append(
                {
                    "id": domain["name"],
                    "label": _words(domain["name"]),
                    "weight": domain["weight"],
                    "dimension": domain["dimension"],
                    "dimension_label": DIMENSIONS[domain["dimension"]][0],
                    "metrics": metrics,
                }
            )
        sport_roles[role["sport"]].append(
            {
                "key": key,
                "role": role["role"],
                "label": role["label"],
                "minimum_opportunity": role["min_opportunity"],
                "opportunity_unit": role["opportunity_unit"],
                "evidence_status": role["evidence_status"],
                "limitation": role["limitation"],
                "domains": domains,
            }
        )

    sports = []
    for sport_id, sport_label in SPORTS.items():
        sports.append(
            {
                "id": sport_id,
                "label": sport_label,
                "source_scope": data_build["rights_and_scope"].get(sport_id, ""),
                "roles": sport_roles.get(sport_id, []),
            }
        )

    training_claim = evaluation.get("claims", {}).get(
        "training_cohort", "No saved training-cohort statement is available."
    )
    reliability_weighting_saved = "opportunity/coverage weight" in training_claim.lower()
    context_coverage = _context_coverage_rows(root)
    context_head_count = evaluation.get("counts", {}).get(
        "heads_fit_with_complete_team_context", 0
    )
    pooling_records = [
        head["partial_pooling"]
        for head in evaluation.get("native_profile_models", {}).values()
        if isinstance(head.get("partial_pooling"), dict)
    ]
    pooling_status_counts = {
        status: sum(record.get("status") == status for record in pooling_records)
        for status in ("deployed", "role_only_retained", "not_applicable")
    }
    pooling_families = sorted(
        {
            str(record["family"])
            for record in pooling_records
            if record.get("family")
        }
    )

    return {
        "schema_version": "plain-language-features-v3",
        "registry": {
            "schema_version": registry["schema_version"],
            "role_taxonomy_version": registry["role_taxonomy_version"],
            "target_version": registry["target_version"],
            "bridge_version": registry["bridge_version"],
            "frozen_test_season": registry["frozen_test_season"],
        },
        "score_contract": registry["score_contract"],
        "role_count": len(registry["roles"]),
        "dimensions": [
            {"id": key, "label": DIMENSIONS[key][0], "description": DIMENSIONS[key][1]}
            for key in DIMENSIONS
            if key in used_dimensions
        ],
        "sports": sports,
        "reliability_weighting": {
            "status": (
                "saved_in_current_artifact"
                if reliability_weighting_saved
                else "awaiting_model_rebuild"
            ),
            "training_cohort_claim": training_claim,
            "fields": [
                {
                    "id": "opportunity_reliability",
                    "label": "Opportunity reliability",
                    "description": (
                        "How much evidence the player's playing time supplies, from 0 to 1. "
                        "It rises as opportunity grows."
                    ),
                    "formula": "opportunity / (opportunity + prior exposure)",
                },
                {
                    "id": "component_coverage_fraction",
                    "label": "Statistic coverage",
                    "description": (
                        "The declared share of the role score whose source statistics are "
                        "actually present for this player-season."
                    ),
                    "formula": "available weighted metrics / declared weighted metrics",
                },
                {
                    "id": "domain_coverage_fraction",
                    "label": "Role-area coverage",
                    "description": (
                        "The declared share of broad role areas with at least one usable "
                        "source statistic."
                    ),
                    "formula": "available weighted role areas / declared weighted role areas",
                },
                {
                    "id": "training_sample_weight",
                    "label": "Season training weight",
                    "description": (
                        "The influence a positive-opportunity player-season receives during "
                        "training; weaker opportunity or coverage reduces that influence."
                    ),
                    "formula": (
                        "opportunity reliability x statistic coverage, limited to 0.05-1.00"
                    ),
                },
            ],
            "next_season_pair": (
                "For next-season models, the pair weight is the geometric mean of the prior- "
                "and next-season training weights. Frozen evaluation still uses eligible rows only."
            ),
        },
        "team_context": {
            "version": CONTEXT_VERSION,
            "status": (
                "used_by_saved_model_heads"
                if context_head_count
                else (
                    "available_in_scored_panel_not_used_by_saved_heads"
                    if context_coverage
                    else "awaiting_scored_panel_rebuild"
                )
            ),
            "model_heads_using_both_fields": context_head_count,
            "summary": (
                "Two completed-season descriptors add workload and teammate context without "
                "changing the player's observed role score."
            ),
            "fields": [
                {"id": feature, **CONTEXT_FIELD_GUIDE[feature]}
                for feature in CONTEXT_FEATURES
            ],
            "leakage_rule": (
                "A season's context may be used only to predict the next season. The model "
                "does not use a future team, target-season team totals or the player's own "
                "score inside the teammate-strength input."
            ),
            "withholding_rule": (
                "Multi-team seasons and rows without positive opportunity are withheld when "
                "stint-level context cannot be calculated consistently across all four sports."
            ),
            "coverage_file": "reports/all_roles/context_coverage.csv",
            "coverage": context_coverage,
        },
        "partial_pooling": {
            "status": (
                "reported_by_saved_native_profile_heads"
                if pooling_records
                else "awaiting_model_rebuild"
            ),
            "reported_heads": len(pooling_records),
            "status_counts": pooling_status_counts,
            "families": pooling_families,
            "summary": (
                "A native build-plus-playing-profile head can blend its role-specific model "
                "slightly toward a predeclared family of related roles when frozen evidence "
                "supports the blend."
            ),
            "selection_rule": (
                "The role-only model remains the default. Pooling is deployed only when the "
                "held-out comparison supports it; otherwise the saved head stays role-only."
            ),
            "interpretation": (
                "This is cautious statistical borrowing for thin role samples, not a claim "
                "that related positions are interchangeable. Unique roles remain unpooled."
            ),
        },
        "boundaries": [
            "Metric and domain weights are declared research choices; they are not learned truths.",
            "Mental labels such as awareness, reaction speed and game IQ are not inferred from box scores.",
            "A shared dimension means the ideas are comparable enough to form a hypothesis, not identical across sports.",
        ],
    }


def _baseline(model: dict[str, Any], family: str) -> tuple[str, float | None]:
    evaluation = model.get("evaluation", {})
    if family == "physical":
        return "Neutral 50", evaluation.get("neutral_50", {}).get("mae")
    if family == "native_profile":
        return "Build only", evaluation.get("build_only", {}).get("mae")
    comparison = evaluation.get("mae_advantage_vs_best_history_baseline", {}).get("comparator")
    if comparison == "rolling_3y":
        return "Sustained three-year history", evaluation.get("rolling_3y_baseline", {}).get("mae")
    if comparison == "prior_season":
        return "Previous season", evaluation.get("prior_season_baseline", {}).get("mae")
    candidates = [
        ("Previous season", evaluation.get("prior_season_baseline", {}).get("mae")),
        ("Sustained three-year history", evaluation.get("rolling_3y_baseline", {}).get("mae")),
    ]
    finite = [(label, value) for label, value in candidates if isinstance(value, (int, float))]
    return min(finite, key=lambda item: item[1]) if finite else ("History baseline", None)


def _head_feature_names(model: dict[str, Any]) -> list[str]:
    candidates = [
        model.get("features"),
        model.get("context_features"),
        model.get("context", {}).get("features")
        if isinstance(model.get("context"), dict)
        else None,
        model.get("model", {}).get("features")
        if isinstance(model.get("model"), dict)
        else None,
    ]
    features: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, (list, tuple, set)):
            features.extend(str(feature) for feature in candidate)
    return list(dict.fromkeys(features))


def _head_context_status(model: dict[str, Any]) -> dict[str, Any]:
    declared = set(_head_feature_names(model))
    present = [feature for feature in CONTEXT_FEATURES if feature in declared]
    if len(present) == len(CONTEXT_FEATURES):
        status = "both_context_fields_used"
    elif present:
        status = "partial_context_fields_used"
    else:
        status = "not_used"
    return {"status": status, "features": present}


def _model_row(key: str, model: dict[str, Any], family: str) -> dict[str, Any]:
    sport, role = key.split(":", 1)
    evaluation = model.get("evaluation", {})
    selected_evaluation = model.get("selected_model_evaluation", evaluation)
    frozen = selected_evaluation.get("frozen", evaluation.get("frozen", {}))
    unseen = evaluation.get("unseen_history_slice", {})
    athlete_disjoint = evaluation.get("athlete_disjoint", {})
    percentile_calibration = selected_evaluation.get(
        "percentile_calibration", evaluation.get("percentile_calibration", {})
    )
    top_decile = selected_evaluation.get(
        "top_decile", evaluation.get("top_decile", {})
    )
    prediction_interval = model.get("prediction_interval", {})
    label, baseline_mae = _baseline(model, family)
    coverage = model.get("usable_coverage", {})
    evidence_gate = (
        model.get("profile_increment_gate", "not_fit")
        if family == "native_profile"
        else model.get("evidence_gate", "not_fit")
    )
    return {
        "key": key,
        "sport": sport,
        "role": role,
        "family": family,
        "status": model.get("status", "not_fit"),
        "evidence_gate": evidence_gate,
        "fit_evidence_gate": model.get("evidence_gate", "not_fit"),
        "profile_increment_gate": model.get("profile_increment_gate"),
        "deployment_support": model.get("deployment_support"),
        "forecast_support": model.get("forecast_support"),
        "test_n": frozen.get("n"),
        "mae": frozen.get("mae"),
        "rmse": frozen.get("rmse"),
        "spearman": frozen.get("spearman"),
        "baseline_label": label,
        "baseline_mae": baseline_mae,
        "unseen_history_n": unseen.get("n"),
        "athlete_disjoint": athlete_disjoint,
        "percentile_calibration": percentile_calibration,
        "top_decile": top_decile,
        "prediction_interval": prediction_interval,
        "frozen_player_face_checks": evaluation.get(
            "frozen_player_face_checks", {}
        ),
        "usable_rows": coverage.get("usable_rows"),
        "eligible_label_rows": coverage.get("eligible_label_rows"),
        "usable_fraction": coverage.get("usable_fraction_of_eligible_labels"),
        "training_label_policy": model.get("training_label_policy", ""),
        "dimensions": model.get("dimensions", []),
        "weighted_low_sample_rows": coverage.get("weighted_low_sample_rows"),
        "team_context": _head_context_status(model),
        "selected_model_family": model.get("selected_model_family", "not_reported"),
        "selected_model_evaluation": model.get("selected_model_evaluation"),
        "partial_pooling": model.get(
            "partial_pooling", {"status": "not_reported"}
        ),
    }


def _bridge_summaries(models: dict[str, Any]) -> dict[str, dict[str, Any]]:
    uses_forward_gate = any(
        "target_role_forward_profile_gate" in model for model in models.values()
    )
    summaries: dict[str, dict[str, Any]] = {
        sport: {
            "sport": sport,
            "candidates": 0,
            "heads": 0,
            "supported": 0,
            "athlete_disjoint_heads": 0,
            "interval_calibrated_heads": 0,
            "target_roles": {},
            "evidence_design": (
                "forward_profile_vs_build"
                if uses_forward_gate
                else "legacy_same_season_reconstruction"
            ),
        }
        for sport in SPORTS
    }
    values_by_role: dict[tuple[str, str], list[float]] = defaultdict(list)
    disjoint_values_by_role: dict[tuple[str, str], list[float]] = defaultdict(list)
    interval_coverage_by_role: dict[tuple[str, str], list[float]] = defaultdict(list)
    top_decile_by_role: dict[tuple[str, str], list[float]] = defaultdict(list)
    counts_by_role: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    for key, model in models.items():
        target = model.get("target_role") or key.split("->", 1)[1]
        sport, role = target.split(":", 1)
        summaries[sport]["candidates"] += 1
        counts_by_role[(sport, role)][0] += 1
        if "evaluation" not in model:
            continue
        gate = model.get(
            "target_role_forward_profile_gate",
            model.get("target_proxy_reconstruction_gate"),
        )
        supported = gate == "supported"
        summaries[sport]["heads"] += 1
        summaries[sport]["supported"] += int(supported)
        disjoint = model.get("evaluation", {}).get("athlete_disjoint", {})
        interval = model.get("prediction_interval", {})
        summaries[sport]["athlete_disjoint_heads"] += int(
            disjoint.get("status") == "available"
        )
        summaries[sport]["interval_calibrated_heads"] += int(
            interval.get("status") == "calibrated_from_rolling_origin"
        )
        counts_by_role[(sport, role)][1] += 1
        counts_by_role[(sport, role)][2] += int(supported)
        mae = model.get("evaluation", {}).get("frozen", {}).get("mae")
        if isinstance(mae, (int, float)):
            values_by_role[(sport, role)].append(float(mae))
        disjoint_mae = disjoint.get("mae")
        if isinstance(disjoint_mae, (int, float)):
            disjoint_values_by_role[(sport, role)].append(float(disjoint_mae))
        interval_coverage = interval.get("frozen_empirical_coverage")
        if isinstance(interval_coverage, (int, float)):
            interval_coverage_by_role[(sport, role)].append(float(interval_coverage))
        top_decile_precision = (
            model.get("evaluation", {})
            .get("top_decile", {})
            .get("precision_at_10_percent")
        )
        if isinstance(top_decile_precision, (int, float)):
            top_decile_by_role[(sport, role)].append(float(top_decile_precision))
    for (sport, role), counts in counts_by_role.items():
        values = values_by_role[(sport, role)]
        disjoint_values = disjoint_values_by_role[(sport, role)]
        interval_values = interval_coverage_by_role[(sport, role)]
        top_decile_values = top_decile_by_role[(sport, role)]
        summaries[sport]["target_roles"][role] = {
            "candidates": counts[0],
            "heads": counts[1],
            "supported": counts[2],
            "median_test_mae": median(values) if values else None,
            "median_athlete_disjoint_mae": (
                median(disjoint_values) if disjoint_values else None
            ),
            "median_prediction_interval_frozen_coverage": (
                median(interval_values) if interval_values else None
            ),
            "median_top_decile_precision_at_10_percent": (
                median(top_decile_values) if top_decile_values else None
            ),
        }
    return summaries


def _ensemble_rows(evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, head in evaluation["heads"].items():
        sport, role = key.split(":", 1)
        metrics = head.get("metrics", {})
        bootstrap = head.get("mse_improvement_cluster_bootstrap", {})
        rows.append(
            {
                "key": key,
                "sport": sport,
                "role": role,
                "status": head.get("status", "unknown"),
                "evidence_grade": head.get("evidence_grade"),
                "selected_method": head.get("selected_method"),
                "reason": head.get("reason"),
                "train_athletes": head.get("train_athletes"),
                "calibration_athletes": head.get("calibration_athletes"),
                "test_athletes": head.get("test_athletes"),
                "mae": metrics.get("mae"),
                "baseline_mae": metrics.get("baseline_mae"),
                "relative_mse_improvement": metrics.get("relative_mse_improvement"),
                "spearman": metrics.get("spearman"),
                "interval_coverage": metrics.get("interval_90_empirical_coverage"),
                "bootstrap_lower95": bootstrap.get("lower95"),
                "bootstrap_upper95": bootstrap.get("upper95"),
                "shared_expert_weight": head.get("expert_weights", {}).get("shared"),
                "abstention_reasons": head.get("abstention_reasons", []),
            }
        )
    return rows


def build_validation_payload(root: Path) -> dict[str, Any]:
    evaluation = _read_json(root / "reports" / "all_roles" / "model_evaluation.json")
    latest = _read_json(root / "reports" / "all_roles" / "latest_run.json")
    ensemble = _read_json(root / "reports" / "ensemble" / "evaluation.json")
    ensemble_registry = _read_json(root / "reports" / "ensemble" / "model_registry.json")

    physical = [
        _model_row(key, model, "physical")
        for key, model in evaluation["physical_models"].items()
    ]
    native = [
        _model_row(key, model, "native")
        for key, model in evaluation["native_forecast_models"].items()
    ]
    native_profile = [
        _model_row(key, model, "native_profile")
        for key, model in evaluation.get("native_profile_models", {}).items()
    ]
    model_face_checks = []
    for row in (*physical, *native, *native_profile):
        for name, check in row.get("frozen_player_face_checks", {}).items():
            model_face_checks.append(
                {
                    "name": name,
                    "model_key": row["key"],
                    "family": row["family"],
                    **check,
                }
            )
    bridges = _bridge_summaries(evaluation["bridge_models"])
    sports = []
    for sport_id, label in SPORTS.items():
        sports.append(
            {
                "id": sport_id,
                "label": label,
                "physical": [row for row in physical if row["sport"] == sport_id],
                "native": [row for row in native if row["sport"] == sport_id],
                "native_profile": [
                    row for row in native_profile if row["sport"] == sport_id
                ],
                "bridge": bridges[sport_id],
            }
        )

    return {
        "schema_version": "plain-language-validation-v3",
        "all_roles": {
            "schema_version": evaluation["schema_version"],
            "role_taxonomy_version": evaluation["role_taxonomy_version"],
            "target_version": evaluation["target_version"],
            "bridge_version": evaluation["bridge_version"],
            "frozen_test_season": evaluation["frozen_test_season"],
            "counts": evaluation["counts"],
            "data": latest["data"],
            "sports": sports,
            "claims": evaluation["claims"],
            "validation_methods": {
                "chronological_gate": (
                    "The saved evidence gates remain based on the frozen 2025 chronological "
                    "test and their declared baseline comparisons."
                ),
                "athlete_disjoint_diagnostic": (
                    "A separate pre-2025 group-fold diagnostic keeps every season for an "
                    "athlete in one fold. It measures identity generalization and does not "
                    "replace the future-season gate."
                ),
                "percentile_calibration": (
                    "Frozen predictions are compared with observed 0-100 percentiles in fixed "
                    "10-point bins and with both threshold and rank-based top-decile checks."
                ),
                "prediction_range": (
                    "The nominal 90% range uses the finite-sample absolute-residual order "
                    "statistic from rolling-origin predictions, retaining one latest residual "
                    "per athlete. Frozen coverage is reported rather than assumed."
                ),
            },
            "face_validity": {
                "observed_target_checks": latest.get("observed", {}).get(
                    "frozen_nba_sanity_checks", {}
                ),
                "frozen_model_checks": model_face_checks,
                "warning": (
                    "Named checks are predeclared diagnostics and are not used to tune model "
                    "features, weights, gates, or prediction ranges."
                ),
            },
        },
        "ensemble": {
            "separate_study": True,
            "title": "Earlier possession and disruption ensemble",
            "version": ensemble["version"],
            "trained_at": ensemble_registry["trained_at"],
            "features": ensemble["features"],
            "split": ensemble_registry["split"],
            "support_policy": ensemble_registry["support_policy"],
            "heads": _ensemble_rows(ensemble),
            "known_limitations": [
                "This is a separate possession/disruption study, not the broad all-role bridge shown above.",
                "No saved head has a 95% bootstrap improvement interval wholly above zero.",
                "The EPL defender target has a known partial-block completeness issue and remains under review.",
                "A cross-sport software component exists, but useful transfer learning has not been established.",
            ],
        },
    }


def export_report_data(root: Path) -> tuple[Path, Path]:
    output = root / "portal-all-roles" / "report" / "data"
    features_path = output / "features.json"
    validation_path = output / "validation.json"
    _write_json(features_path, build_feature_payload(root))
    _write_json(validation_path, build_validation_payload(root))
    return features_path, validation_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export aggregate report data")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    paths = export_report_data(args.root.resolve())
    print("\n".join(str(path) for path in paths))


if __name__ == "__main__":
    main()
