"""End-to-end orchestration for the independent all-role research project."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from possession_lab.all_roles_context import CONTEXT_FEATURES
from possession_lab.all_roles_epl import build_epl_all_roles_panel
from possession_lab.all_roles_models import train_all_role_models
from possession_lab.all_roles_nba import build_nba_all_roles_panel
from possession_lab.all_roles_registry import registry_payload, role_specs
from possession_lab.all_roles_targets import score_observed_panel
from possession_lab.io import collect_manifest, save_frame, write_json


def _builder(sport: str):
    if sport == "nfl":
        from possession_lab.all_roles_nfl import build_nfl_all_roles_panel

        return build_nfl_all_roles_panel
    if sport == "nba":
        return build_nba_all_roles_panel
    if sport == "nhl":
        from possession_lab.all_roles_nhl import build_nhl_all_roles_panel

        return build_nhl_all_roles_panel
    if sport == "epl":
        return build_epl_all_roles_panel
    raise ValueError(f"Unknown sport: {sport}")


def _canonicalize_panel(frame: pd.DataFrame, sport: str) -> pd.DataFrame:
    result = frame.copy()
    result["sport"] = sport
    result["player_id"] = result["player_id"].astype("string")
    result["season"] = pd.to_numeric(result["season"], errors="raise").astype(int)
    result["role"] = result["role"].astype("string")
    result["opportunity"] = pd.to_numeric(result["opportunity"], errors="coerce")
    for column in ["height_cm", "weight_kg", "age", "games"]:
        if column not in result:
            result[column] = np.nan
        result[column] = pd.to_numeric(result[column], errors="coerce")
    height_invalid = result["height_cm"].notna() & ~result["height_cm"].between(140, 230)
    weight_invalid = result["weight_kg"].notna() & ~result["weight_kg"].between(35, 230)
    result["height_cm_rejected_raw"] = result["height_cm"].where(height_invalid)
    result["weight_kg_rejected_raw"] = result["weight_kg"].where(weight_invalid)
    result["height_quality_flag"] = np.where(height_invalid, "implausible_set_missing", "as_reported")
    result["weight_quality_flag"] = np.where(weight_invalid, "implausible_set_missing", "as_reported")
    result.loc[height_invalid, "height_cm"] = np.nan
    result.loc[weight_invalid, "weight_kg"] = np.nan
    if "position" not in result:
        result["position"] = result["role"]
    if "team" not in result:
        result["team"] = pd.NA
    if result.duplicated(["player_id", "season"]).any():
        raise ValueError(f"{sport} all-role builder returned duplicate player-season rows")
    return result


def _context_coverage_table(scored: pd.DataFrame) -> pd.DataFrame:
    """Summarize role-level context availability with a stable column order."""
    required = {"sport", "role", "context_status", *CONTEXT_FEATURES}
    missing = sorted(required.difference(scored.columns))
    if missing:
        raise ValueError(f"Context coverage requires columns: {missing}")
    columns = [
        "sport",
        "role",
        "total_rows",
        "context_available_rows",
        "context_available_fraction",
    ]
    for feature in CONTEXT_FEATURES:
        columns.extend([f"{feature}_available_rows", f"{feature}_coverage"])

    rows: list[dict] = []
    grouped = scored.groupby(["sport", "role"], dropna=False, observed=True, sort=True)
    for (sport, role), cohort in grouped:
        total = int(len(cohort))
        available = int(cohort["context_status"].eq("available").sum())
        row = {
            "sport": str(sport),
            "role": str(role),
            "total_rows": total,
            "context_available_rows": available,
            "context_available_fraction": available / total if total else 0.0,
        }
        for feature in CONTEXT_FEATURES:
            values = pd.to_numeric(cohort[feature], errors="coerce")
            present = int((values.notna() & np.isfinite(values)).sum())
            row[f"{feature}_available_rows"] = present
            row[f"{feature}_coverage"] = present / total if total else 0.0
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def _write_context_coverage(root: Path, scored: pd.DataFrame) -> Path:
    path = root / "reports" / "all_roles" / "context_coverage.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    _context_coverage_table(scored).to_csv(
        path,
        index=False,
        lineterminator="\n",
        float_format="%.6f",
    )
    return path


def build_all_roles_data(
    root: Path | str,
    seasons=range(2021, 2026),
    *,
    sports=("nfl", "nba", "nhl", "epl"),
) -> tuple[pd.DataFrame, dict]:
    root = Path(root)
    seasons = sorted(set(int(season) for season in seasons))
    output_dir = root / "data" / "processed" / "all_roles"
    pieces: list[pd.DataFrame] = []
    summary: dict[str, dict] = {}
    for sport in sports:
        panel = _canonicalize_panel(_builder(sport)(root, seasons=seasons), sport)
        save_frame(panel, output_dir / f"{sport}_player_seasons.parquet")
        pieces.append(panel)
        summary[sport] = {
            "rows": int(len(panel)),
            "athletes": int(panel["player_id"].nunique()),
            "seasons": sorted(int(value) for value in panel["season"].unique()),
            "roles": {str(key): int(value) for key, value in panel["role"].value_counts().items()},
            "height_coverage": float(panel["height_cm"].notna().mean()),
            "weight_coverage": float(panel["weight_kg"].notna().mean()),
        }
    combined = pd.concat(pieces, ignore_index=True, sort=False)
    if combined.duplicated(["sport", "player_id", "season"]).any():
        raise ValueError("Combined all-role panel has duplicate sport-player-season rows")
    save_frame(combined, output_dir / "player_seasons.parquet")
    write_json(root / "metadata" / "all_roles_metric_registry.json", registry_payload())
    report = {
        "seasons": seasons,
        "sports": summary,
        "rows": int(len(combined)),
        "athletes_within_sport": int(
            combined[["sport", "player_id"]].drop_duplicates().shape[0]
        ),
        "rights_and_scope": {
            "epl": "Broad-role local research prototype; do not redistribute cached FPL/community raw data without rights review.",
            "nhl": "MoneyPuck designated downloads; non-commercial use with clear attribution.",
            "nfl": "Core nflverse data; optional PFR/community enrichment remains conditional.",
            "nba": "SportsDataverse research snapshot; preserve upstream attribution and review redistribution rights.",
        },
    }
    write_json(root / "reports" / "all_roles" / "data_build.json", report)
    return combined, report


def build_observed_scores(
    root: Path | str,
    panel: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict]:
    root = Path(root)
    if panel is None:
        path = root / "data" / "processed" / "all_roles" / "player_seasons.parquet"
        if not path.exists():
            panel, _ = build_all_roles_data(root)
        else:
            panel = pd.read_parquet(path)
    scored, audit = score_observed_panel(panel)
    save_frame(scored, root / "data" / "processed" / "all_roles" / "observed_scores.parquet")
    _write_context_coverage(root, scored)
    sanity = frozen_nba_sanity_checks(scored)
    report = {"target_audit": audit, "frozen_nba_sanity_checks": sanity}
    write_json(root / "reports" / "all_roles" / "observed_targets.json", report)
    return scored, report


def frozen_nba_sanity_checks(scored: pd.DataFrame) -> dict:
    """Predeclared face-validity checks; never used to tune target weights."""
    checks = {
        "stephen_curry": {
            "player_id": "3975",
            "metric": "domain_scoring_percentile",
            "minimum": 90.0,
        },
        "lebron_james": {
            "player_id": "1966",
            "metric": "domain_creation_percentile",
            "minimum": 90.0,
        },
    }
    nba = scored.loc[scored["sport"].eq("nba")].copy()
    output: dict[str, dict] = {}
    for name, expectation in checks.items():
        rows = nba.loc[nba["player_id"].astype(str).eq(expectation["player_id"])]
        if rows.empty:
            output[name] = {**expectation, "status": "identity_missing", "value": None}
            continue
        # Latest observed complete season in the local snapshot, not a cherry-picked year.
        row = rows.sort_values("season").iloc[-1]
        value = pd.to_numeric(pd.Series([row.get(expectation["metric"])]), errors="coerce").iloc[0]
        output[name] = {
            **expectation,
            "season": int(row["season"]),
            "value": float(value) if np.isfinite(value) else None,
            "status": (
                "pass"
                if np.isfinite(value) and value >= expectation["minimum"]
                else "audit_required"
            ),
            "interpretation": "Face-validity check for observed target construction; not cross-sport validation.",
        }
    # Explicitly protect the common Stephen/Seth collision.
    seth = nba.loc[nba["player_id"].astype(str).eq("2326307"), "name"].dropna().unique()
    output["identity_guard"] = {
        "stephen_id": "3975",
        "seth_id": "2326307",
        "seth_names": [str(value) for value in seth],
        "status": "pass" if any("Seth" in str(value) for value in seth) else "audit_required",
    }
    return output


def _model_report(artifact: dict) -> dict:
    def summarize(head: dict) -> dict:
        result = {key: value for key, value in head.items() if key != "model"}
        model = head.get("model")
        if model is not None:
            result["model"] = model.metadata()
        return result

    return {
        "schema_version": artifact["schema_version"],
        "role_taxonomy_version": artifact["role_taxonomy_version"],
        "target_version": artifact["target_version"],
        "bridge_version": artifact["bridge_version"],
        "frozen_test_season": artifact["frozen_test_season"],
        "claims": artifact["claims"],
        "physical_models": {
            key: summarize(head) for key, head in artifact["physical_models"].items()
        },
        "native_forecast_models": {
            key: summarize(head) for key, head in artifact["native_forecast_models"].items()
        },
        "native_profile_models": {
            key: summarize(head) for key, head in artifact["native_profile_models"].items()
        },
        "bridge_models": {
            key: summarize(head) for key, head in artifact["bridge_models"].items()
        },
    }


def _declared_head_features(head: dict) -> set[str]:
    """Return serializable feature names without assuming one estimator class."""
    candidates = [head.get("features")]
    model = head.get("model")
    if model is not None:
        candidates.append(getattr(model, "features", None))
        if isinstance(model, dict):
            candidates.append(model.get("features"))
    for candidate in candidates:
        if isinstance(candidate, (list, tuple, set)):
            return {str(feature) for feature in candidate}
    return set()


def _context_pooling_counts(artifact: dict) -> dict[str, int]:
    """Count only context and pooling states explicitly present in head metadata."""
    families = (
        artifact.get("physical_models", {}),
        artifact.get("native_forecast_models", {}),
        artifact.get("native_profile_models", {}),
        artifact.get("bridge_models", {}),
    )
    heads = [head for family in families for head in family.values()]
    fitted = [head for head in heads if "model" in head]
    context_sets = [_declared_head_features(head) for head in fitted]
    pooling = [
        head["partial_pooling"]
        for head in heads
        if isinstance(head.get("partial_pooling"), dict)
    ]
    counts = {
        "heads_fit_with_any_team_context": sum(
            bool(features.intersection(CONTEXT_FEATURES)) for features in context_sets
        ),
        "heads_fit_with_complete_team_context": sum(
            set(CONTEXT_FEATURES).issubset(features) for features in context_sets
        ),
        "partial_pooling_heads_reported": len(pooling),
    }
    for status in ("deployed", "role_only_retained", "not_applicable"):
        counts[f"partial_pooling_{status}_heads"] = sum(
            item.get("status") == status for item in pooling
        )
    return counts


def train_all_roles(
    root: Path | str,
    scored: pd.DataFrame | None = None,
) -> tuple[dict, dict]:
    root = Path(root)
    if scored is None:
        path = root / "data" / "processed" / "all_roles" / "observed_scores.parquet"
        if path.exists():
            scored = pd.read_parquet(path)
        else:
            scored, _ = build_observed_scores(root)
    artifact, pairs = train_all_role_models(scored)
    model_path = root / "models" / "all_roles" / "all_roles_v1.joblib"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_path)
    save_frame(
        pairs,
        root / "data" / "processed" / "all_roles" / "native_forecast_pairs.parquet",
    )
    report = _model_report(artifact)
    fitted_heads = [
        head
        for family in (
            artifact["physical_models"],
            artifact["native_forecast_models"],
            artifact["native_profile_models"],
            artifact["bridge_models"],
        )
        for head in family.values()
        if "model" in head
    ]
    report["counts"] = {
        "registered_roles": len(role_specs()),
        "physical_heads_fit": sum("model" in head for head in artifact["physical_models"].values()),
        "native_heads_fit": sum(
            "model" in head for head in artifact["native_forecast_models"].values()
        ),
        "native_profile_heads_fit": sum(
            "model" in head for head in artifact["native_profile_models"].values()
        ),
        "bridge_heads_fit": sum("model" in head for head in artifact["bridge_models"].values()),
        "forecast_pairs": int(len(pairs)),
        "athlete_disjoint_diagnostics_available": sum(
            head.get("evaluation", {}).get("athlete_disjoint", {}).get("status")
            == "available"
            for head in fitted_heads
        ),
        "rolling_origin_prediction_intervals_available": sum(
            head.get("prediction_interval", {}).get("status")
            == "calibrated_from_rolling_origin"
            for head in fitted_heads
        ),
        "top_decile_diagnostics_available": sum(
            head.get("evaluation", {}).get("top_decile", {}).get("selection_n", 0) > 0
            for head in fitted_heads
        ),
        "predeclared_frozen_player_checks": sum(
            len(head.get("evaluation", {}).get("frozen_player_face_checks", {}))
            for head in fitted_heads
        ),
    }
    report["counts"].update(_context_pooling_counts(artifact))
    write_json(root / "reports" / "all_roles" / "model_evaluation.json", report)
    return artifact, report


def load_all_role_models(root: Path | str) -> dict:
    path = Path(root) / "models" / "all_roles" / "all_roles_v1.joblib"
    if not path.exists():
        raise FileNotFoundError(f"Train all-role models first: {path}")
    return joblib.load(path)


def run_all_roles(root: Path | str, seasons=range(2021, 2026)) -> dict:
    root = Path(root)
    panel, data_report = build_all_roles_data(root, seasons)
    scored, observed_report = build_observed_scores(root, panel)
    _, model_report = train_all_roles(root, scored)
    manifest = collect_manifest(root)
    target_audit = observed_report["target_audit"]
    result = {
        "data": data_report,
        "observed": {
            "rows": target_audit["rows"],
            "scored_rows": target_audit["scored_rows"],
            "scored_cohorts": len(target_audit["cohorts"]),
            "skipped_cohorts": len(target_audit["skipped"]),
            "frozen_nba_sanity_checks": observed_report["frozen_nba_sanity_checks"],
            "full_audit": "reports/all_roles/observed_targets.json",
        },
        "models": model_report["counts"],
        "source_files": manifest["file_count"],
    }
    write_json(root / "reports" / "all_roles" / "latest_run.json", result)
    return result
