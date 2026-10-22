"""Small, deterministic exports for the plain-language model report.

The browser pages intentionally consume aggregate, versioned evidence rather
than row-level player data.  Re-run this module after rebuilding either model
family so the report and the saved artifacts stay in sync.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

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


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _words(value: str) -> str:
    return value.replace("_", " ").strip().title()


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

    return {
        "schema_version": "plain-language-features-v2",
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


def _model_row(key: str, model: dict[str, Any], family: str) -> dict[str, Any]:
    sport, role = key.split(":", 1)
    evaluation = model.get("evaluation", {})
    frozen = evaluation.get("frozen", {})
    unseen = evaluation.get("unseen_history_slice", {})
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
        "usable_rows": coverage.get("usable_rows"),
        "eligible_label_rows": coverage.get("eligible_label_rows"),
        "usable_fraction": coverage.get("usable_fraction_of_eligible_labels"),
        "training_label_policy": model.get("training_label_policy", ""),
        "dimensions": model.get("dimensions", []),
        "weighted_low_sample_rows": coverage.get("weighted_low_sample_rows"),
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
        counts_by_role[(sport, role)][1] += 1
        counts_by_role[(sport, role)][2] += int(supported)
        mae = model.get("evaluation", {}).get("frozen", {}).get("mae")
        if isinstance(mae, (int, float)):
            values_by_role[(sport, role)].append(float(mae))
    for (sport, role), counts in counts_by_role.items():
        values = values_by_role[(sport, role)]
        summaries[sport]["target_roles"][role] = {
            "candidates": counts[0],
            "heads": counts[1],
            "supported": counts[2],
            "median_test_mae": median(values) if values else None,
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
        "schema_version": "plain-language-validation-v2",
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
