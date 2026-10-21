"""Static export for the all-role athlete explorer.

The browser never loads a model or performs inference.  This module reads the
saved observed-score panel and model artifact, scores each athlete's latest
active season once, and writes strict JSON for the framework-free frontend.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from possession_lab.all_roles_pipeline import load_all_role_models
from possession_lab.all_roles_registry import role_specs
from possession_lab.all_roles_score import score_all_roles_profile
from possession_lab.io import sha256

SPORT_LABELS = {
    "nfl": "NFL",
    "nba": "NBA",
    "nhl": "NHL",
    "epl": "Premier League",
}

BODY_FIT_FEATURES = ("height_cm", "weight_kg")
BODY_FIT_MIN_REFERENCE_ATHLETES = 20
BODY_FIT_COVARIANCE_SHRINKAGE = 0.10


def _safe(value: Any) -> Any:
    """Convert pandas/numpy values into strict JSON-compatible values."""
    if value is pd.NA or value is pd.NaT or value is None:
        return None
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime, Path)):
        return str(value)
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_safe(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        + "\n"
    )


def _latest_active_rows(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"sport", "player_id", "name", "season", "role", "opportunity"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Observed all-role scores are missing columns: {missing}")
    source = frame.copy()
    source["sport"] = source["sport"].astype("string").str.lower()
    source["player_id"] = source["player_id"].astype("string")
    source["season"] = pd.to_numeric(source["season"], errors="raise").astype(int)
    source["opportunity"] = pd.to_numeric(source["opportunity"], errors="coerce")
    if source.duplicated(["sport", "player_id", "season"]).any():
        raise ValueError("Observed all-role scores contain duplicate sport-player-season rows")
    latest = (
        source.sort_values(["sport", "player_id", "season"])
        .groupby(["sport", "player_id"], sort=False, as_index=False)
        .tail(1)
    )
    # Performance roles need positive source-sport opportunity. Registered
    # abstention roles (currently NFL OT/IOL/LS) remain searchable when weekly
    # roster evidence exists, even though the project deliberately withholds a
    # performance label for them. Generic zero-opportunity listings stay out.
    abstention = latest["target_status"].astype("string").str.startswith("abstain", na=False)
    rostered_weeks = latest.get(
        "rostered_weeks", pd.Series(np.nan, index=latest.index, dtype=float)
    )
    rostered = pd.to_numeric(rostered_weeks, errors="coerce").gt(0)
    return latest.loc[latest["opportunity"].gt(0) | (abstention & rostered)].copy()


def _profile_values(row: pd.Series, prefix: str) -> list[dict]:
    suffix = "_percentile"
    result = []
    for column in sorted(str(name) for name in row.index if str(name).startswith(prefix)):
        value = _safe(row.get(column))
        if value is None:
            continue
        label = column.removeprefix(prefix).removesuffix(suffix).replace("_", " ")
        result.append({"key": column, "label": label, "value": value})
    return result


def _catalog_player(row: pd.Series) -> dict:
    identity = f"{row['sport']}:{row['player_id']}"
    digest = hashlib.sha256(identity.encode()).hexdigest()[:20]
    team = row.get("team")
    if pd.isna(team) or str(team).strip() == "":
        team = row.get("teams")
    return _safe(
        {
            "id": identity,
            "player_id": str(row["player_id"]),
            "name": row["name"],
            "sport": row["sport"],
            "sport_label": SPORT_LABELS.get(str(row["sport"]), str(row["sport"]).upper()),
            "season": int(row["season"]),
            "role": row["role"],
            "position": row.get("position"),
            "team": team,
            "opportunity": row["opportunity"],
            "rostered_weeks": row.get("rostered_weeks"),
            "height_cm": row.get("height_cm"),
            "weight_kg": row.get("weight_kg"),
            "age": row.get("age"),
            "detail_path": f"data/players/{digest}.json",
        }
    )


def _preferred_default(players: list[dict]) -> dict | None:
    by_id = {player["id"]: player for player in players}
    for identity in ("nba:1966", "nba:3975"):
        if identity in by_id:
            return by_id[identity]
    return players[0] if players else None


def _sport_manifest() -> list[dict]:
    specs = role_specs()
    result = []
    for sport, label in SPORT_LABELS.items():
        roles = [
            {
                "id": spec.role,
                "key": key,
                "label": spec.label,
                "evidence_status": spec.evidence_status,
                "limitation": spec.limitation,
            }
            for key, spec in specs.items()
            if spec.sport == sport
        ]
        result.append({"id": sport, "label": label, "roles": roles})
    return result


def _body_fit_references(snapshot: pd.DataFrame) -> dict[str, dict]:
    """Build descriptive role-body references from one latest row per athlete.

    This is deliberately separate from every learned outcome head.  The
    empirical survival percentile answers only how central a height/weight
    profile is in a target-role cohort; it is not an efficacy estimate.
    """
    required = {"sport", "role", "player_id", *BODY_FIT_FEATURES}
    missing = sorted(required.difference(snapshot.columns))
    if missing:
        raise ValueError(f"Body-fit reference is missing columns: {missing}")
    references: dict[str, dict] = {}
    source = snapshot.copy()
    for feature in BODY_FIT_FEATURES:
        source[feature] = pd.to_numeric(source[feature], errors="coerce")
    source = source.drop_duplicates(["sport", "player_id"], keep="last")
    for (sport, role), group in source.groupby(["sport", "role"], dropna=False, sort=True):
        key = f"{sport}:{role}"
        valid = group.loc[
            group[list(BODY_FIT_FEATURES)].notna().all(axis=1)
            & group[list(BODY_FIT_FEATURES)].gt(0).all(axis=1),
            list(BODY_FIT_FEATURES),
        ]
        values = valid.to_numpy(dtype=float)
        reference_athletes = int(len(values))
        if reference_athletes < BODY_FIT_MIN_REFERENCE_ATHLETES:
            references[key] = {
                "status": "insufficient_reference",
                "reference_athletes": reference_athletes,
            }
            continue
        center = values.mean(axis=0)
        covariance = np.atleast_2d(np.cov(values, rowvar=False, ddof=1))
        diagonal = np.diag(np.diag(covariance))
        covariance = (
            (1.0 - BODY_FIT_COVARIANCE_SHRINKAGE) * covariance
            + BODY_FIT_COVARIANCE_SHRINKAGE * diagonal
        )
        inverse = np.linalg.pinv(covariance, hermitian=True)
        deltas = values - center
        distances = np.einsum("ij,jk,ik->i", deltas, inverse, deltas)
        distances = np.maximum(distances, 0.0)
        references[key] = {
            "status": "available",
            "reference_athletes": reference_athletes,
            "center": center,
            "inverse_covariance": inverse,
            "distances": np.sort(distances),
            "lower": np.quantile(values, 0.01, axis=0),
            "upper": np.quantile(values, 0.99, axis=0),
        }
    return references


def _body_fit(profile: Mapping[str, Any], reference: Mapping[str, Any] | None) -> dict:
    """Return a role-relative build-centrality percentile, never a talent score."""
    base = {
        "kind": "target_role_body_centrality",
        "value": None,
        "evidence_class": "descriptive_height_weight_centrality",
        "method": "empirical_mahalanobis_survival_percentile_height_weight",
        "features_used": list(BODY_FIT_FEATURES),
        "reference_athletes": int(reference.get("reference_athletes", 0)) if reference else 0,
        "note": (
            "Height/weight centrality within the latest target-role cohort; higher means a more "
            "typical build, not greater ability or sport-switch success."
        ),
    }
    values = []
    for feature in BODY_FIT_FEATURES:
        value = profile.get(feature)
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = np.nan
        values.append(number)
    body = np.asarray(values, dtype=float)
    if not np.isfinite(body).all() or np.any(body <= 0):
        return {**base, "status": "withheld_missing_height_or_weight"}
    if not reference or reference.get("status") != "available":
        return {**base, "status": "withheld_insufficient_reference"}

    center = np.asarray(reference["center"], dtype=float)
    inverse = np.asarray(reference["inverse_covariance"], dtype=float)
    delta = body - center
    distance = max(float(delta @ inverse @ delta), 0.0)
    distances = np.asarray(reference["distances"], dtype=float)
    cdf = int(np.searchsorted(distances, distance, side="right"))
    value = float(100.0 * (1.0 - cdf / len(distances)))
    lower = np.asarray(reference["lower"], dtype=float)
    upper = np.asarray(reference["upper"], dtype=float)
    return _safe(
        {
            **base,
            "status": "available",
            "value": value,
            "mahalanobis_distance_squared": distance,
            "outside_1_99_reference": bool(np.any(body < lower) or np.any(body > upper)),
            "reference_center": dict(zip(BODY_FIT_FEATURES, center.tolist())),
            "reference_bounds": {
                feature: [float(lower[index]), float(upper[index])]
                for index, feature in enumerate(BODY_FIT_FEATURES)
            },
        }
    )


def _attach_body_fit(score: dict, profile: Mapping[str, Any], references: Mapping[str, dict]) -> None:
    for sport, target in score.get("targets", {}).items():
        for role, payload in target.get("roles", {}).items():
            payload["body_fit"] = _body_fit(profile, references.get(f"{sport}:{role}"))


def _evidence_counts(artifact: Mapping[str, Any]) -> dict:
    physical = artifact.get("physical_models", {})
    native = artifact.get("native_forecast_models", {})
    bridges = artifact.get("bridge_models", {})
    return {
        "physical_models_fit": sum(isinstance(head, Mapping) and "model" in head for head in physical.values()),
        "physical_models_beating_neutral": sum(
            isinstance(head, Mapping) and head.get("status") == "beats_neutral_baseline"
            for head in physical.values()
        ),
        "physical_models_supported": sum(
            isinstance(head, Mapping) and head.get("evidence_gate") == "supported"
            for head in physical.values()
        ),
        "native_models_fit": sum(isinstance(head, Mapping) and "model" in head for head in native.values()),
        "native_models_beating_history": sum(
            isinstance(head, Mapping)
            and head.get("forecast_support") == "supported_over_history_baselines"
            for head in native.values()
        ),
        "native_models_deployment_supported": sum(
            isinstance(head, Mapping)
            and head.get("deployment_support")
            == "supported_over_neutral_and_history_baselines"
            for head in native.values()
        ),
        "bridge_models_fit": sum(isinstance(head, Mapping) and "model" in head for head in bridges.values()),
        "bridge_target_proxy_heads_passing_gate": sum(
            isinstance(head, Mapping)
            and head.get("target_proxy_reconstruction_gate") == "supported"
            for head in bridges.values()
        ),
    }


def build_all_roles_portal(root: Path | str, output_dir: Path | str | None = None) -> dict:
    """Export the latest active athlete snapshot and all four score types."""
    root = Path(root).resolve()
    output = Path(output_dir).resolve() if output_dir is not None else root / "portal-all-roles"
    observed_path = root / "data" / "processed" / "all_roles" / "observed_scores.parquet"
    model_path = root / "models" / "all_roles" / "all_roles_v1.joblib"
    if not observed_path.exists():
        raise FileNotFoundError(f"Build observed all-role scores first: {observed_path}")
    if not model_path.exists():
        raise FileNotFoundError(f"Train all-role models first: {model_path}")

    observed = pd.read_parquet(observed_path)
    snapshot = _latest_active_rows(observed)
    body_fit_references = _body_fit_references(snapshot)
    artifact = load_all_role_models(root)
    players: list[dict] = []
    sport_counts: Counter[str] = Counter()
    for _, row in snapshot.sort_values(["sport", "name", "player_id"]).iterrows():
        player = _catalog_player(row)
        score = score_all_roles_profile(artifact, row)
        _attach_body_fit(score, row, body_fit_references)
        score["player"] = {**score["player"], **player}
        score["native_profile"] = {
            "domains": _profile_values(row, "domain_"),
            "transferable_dimensions": _profile_values(row, "dimension_"),
            "target_status": _safe(row.get("target_status")),
            "evidence_status": _safe(row.get("evidence_status")),
            "minimum_opportunity": _safe(row.get("minimum_opportunity")),
        }
        _write_json(output / player["detail_path"], score)
        players.append(player)
        sport_counts[player["sport"]] += 1

    default = _preferred_default(players)
    seasons = sorted(int(value) for value in snapshot["season"].unique()) if len(snapshot) else []
    manifest = _safe(
        {
            "schema_version": 3,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "title": "Athlete Translation Lab — All Roles",
            "model": {
                "schema_version": artifact.get("schema_version"),
                "role_taxonomy_version": artifact.get("role_taxonomy_version"),
                "target_version": artifact.get("target_version"),
                "bridge_version": artifact.get("bridge_version"),
                "frozen_test_season": artifact.get("frozen_test_season"),
                "sha256": sha256(model_path),
                "evidence": _evidence_counts(artifact),
            },
            "snapshot": {
                "latest_seasons": seasons,
                "rule": "Latest season per sport-athlete identity with positive observed opportunity, plus registered abstention roles with roster evidence",
                "source_sha256": sha256(observed_path),
            },
            "sports": _sport_manifest(),
            "players": players,
            "defaults": {
                "player_id": default["id"] if default else None,
                "target_sport": default["sport"] if default else "nba",
            },
            "counts": {"players": len(players), "by_sport": dict(sorted(sport_counts.items()))},
            "claims": artifact.get("claims", {}),
            "limitations": [
                "Observed scores are retrospective role-season percentiles, not model predictions.",
                "Native forecasts use prior information and may be withheld or trail a history baseline.",
                "Physical-only estimates are associations with build, not causal effects or talent grades.",
                "Cross-sport transfer results are exploratory analogies, never probabilities of switching successfully.",
                "A bridge gate tests only within-target-role proxy reconstruction; it is not evidence that performance transfers between sports.",
                "Low-sample native scores remain descriptive but are excluded from supervised labels and cross-sport performance transfer.",
                "A percentile is relative to one target role and cohort; equal numbers in different roles do not imply equal sporting value.",
                "Undated profile measurements and public-stat proxies limit historical and tactical interpretation.",
            ],
        }
    )
    _write_json(output / "data" / "manifest.json", manifest)
    return manifest
