"""Build a small, deterministic, portfolio-safe export for the Astro site.

The full portal snapshot is intentionally local.  This module reads that frozen
presentation export—not raw data or saved estimators—and creates an explicit
allowlist of compact, derived player profiles for a public static site.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

PUBLIC_SITE_SCHEMA_VERSION = 1
GENERATED_MARKER = ".athlete-translation-public-export"
MAX_PLAYER_BYTES = 30_000

FEATURED_CASES: tuple[dict[str, str], ...] = (
    {
        "player_id": "nhl:8478402",
        "target_sport": "nba",
        "target_role": "guard",
        "story": "Elite native performance and a high cross-sport profile analogy.",
    },
    {
        "player_id": "nba:3975",
        "target_sport": "nhl",
        "target_role": "right_wing",
        "story": "An elite scoring dimension inside a broader all-around guard rating.",
    },
    {
        "player_id": "nba:1966",
        "target_sport": "nfl",
        "target_role": "EDGE",
        "story": "A strong native validation case with an elite creation profile.",
    },
    {
        "player_id": "nba:5104157",
        "target_sport": "nfl",
        "target_role": "TE",
        "story": "Shows why an unusual build can trigger a responsible model warning.",
    },
    {
        "player_id": "nfl:00-0034796",
        "target_sport": "nba",
        "target_role": "guard",
        "story": "Demonstrates how playing profile can change a body-only comparison.",
    },
    {
        "player_id": "nfl:00-0033886",
        "target_sport": "nhl",
        "target_role": "defense",
        "story": "Connects the broader project to its possession-winning origin.",
    },
    {
        "player_id": "epl:fpl:223094",
        "target_sport": "nfl",
        "target_role": "TE",
        "story": "A productive forward with a distinctive build comparison.",
    },
    {
        "player_id": "epl:fpl:97032",
        "target_sport": "nba",
        "target_role": "forward",
        "story": "Shows that a typical target-role build is not the same as ability.",
    },
    {
        "player_id": "nhl:8477960",
        "target_sport": "nhl",
        "target_role": "right_wing",
        "story": "Uses the only native profile head that passed the partial-pooling gate.",
    },
)

FEATURE_LABELS = {
    "height_cm": "height",
    "weight_kg": "weight",
    "bmi": "height-to-weight balance",
    "age": "age",
    "observed_role_percentile": "observed home-role result",
    "availability_percentile": "availability",
    "sustained_3y_percentile": "sustained three-season performance",
    "dimension_scoring_finishing_percentile": "scoring and finishing",
    "dimension_creation_distribution_percentile": "creation and distribution",
    "dimension_possession_security_percentile": "possession security",
    "dimension_defensive_disruption_percentile": "defensive disruption",
    "dimension_progression_territory_percentile": "progression and territory gain",
    "dimension_discipline_efficiency_percentile": "discipline and efficiency",
    "dimension_recovery_rebounding_percentile": "recovery and rebounding",
}


def _json_bytes(value: Any) -> bytes:
    cleaned = _clean_json(value)
    return (
        json.dumps(cleaned, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _clean_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _clean_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_json(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _pick(source: Mapping[str, Any] | None, *keys: str) -> dict[str, Any]:
    source = source or {}
    return {key: source.get(key) for key in keys if key in source}


def _compact_range(estimate: Mapping[str, Any]) -> dict[str, Any] | None:
    interval = estimate.get("prediction_range_90")
    if isinstance(interval, Mapping):
        return _pick(
            interval,
            "lower",
            "upper",
            "half_width",
            "nominal_coverage",
            "calibration_athletes",
            "frozen_empirical_coverage",
        )
    sensitivity = estimate.get("analogy_sensitivity_range")
    if isinstance(sensitivity, list) and len(sensitivity) == 2:
        return {
            "lower": sensitivity[0],
            "upper": sensitivity[1],
            "method": "frozen_test_mae_sensitivity",
        }
    return None


def _compact_contributions(estimate: Mapping[str, Any]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for contribution in (estimate.get("top_contributions") or [])[:3]:
        if not isinstance(contribution, Mapping):
            continue
        compact.append(_pick(contribution, "feature", "contribution", "imputed"))
    return compact


def _compact_estimate(
    source: Mapping[str, Any] | None,
    *,
    include_decision: bool = False,
) -> dict[str, Any]:
    source = source or {}
    result = _pick(
        source,
        "kind",
        "status",
        "value",
        "reference_rows",
        "target_season",
    )
    if include_decision:
        result.update(_pick(source, "evidence_class", "support_status"))
    result["top_contributions"] = _compact_contributions(source)
    result["ood_status"] = (source.get("ood") or {}).get("status")
    prediction_range = _compact_range(source)
    if prediction_range:
        result["range"] = prediction_range
    if isinstance(source.get("team_context"), Mapping):
        result["team_context"] = _pick(
            source["team_context"], "selected", "increment_gate", "selection_reason"
        )
    if isinstance(source.get("partial_pooling"), Mapping):
        result["partial_pooling"] = _pick(
            source["partial_pooling"],
            "status",
            "family",
            "gate",
            "selected_tau",
            "role_weight",
            "family_weight",
            "reason",
        )
    return result


def _compact_body_fit(source: Mapping[str, Any] | None) -> dict[str, Any]:
    return _pick(
        source,
        "status",
        "value",
        "reference_athletes",
        "outside_1_99_reference",
    )


def _compact_profile(source: Mapping[str, Any] | None) -> dict[str, Any]:
    source = source or {}

    def rows(key: str) -> list[dict[str, Any]]:
        return [
            _pick(row, "key", "label", "value")
            for row in source.get(key, [])
            if isinstance(row, Mapping)
        ]

    return {
        "domains": rows("domains"),
        "dimensions": rows("transferable_dimensions"),
        **_pick(source, "target_status", "evidence_status", "minimum_opportunity"),
    }


def _compact_targets(source: Mapping[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for sport_id, sport in sorted((source or {}).items()):
        if not isinstance(sport, Mapping):
            continue
        roles: dict[str, Any] = {}
        for role_id, role in sorted((sport.get("roles") or {}).items()):
            if not isinstance(role, Mapping):
                continue
            roles[str(role_id)] = {
                "body_fit": _compact_body_fit(role.get("body_fit")),
                "physical": _compact_estimate(role.get("physical_only")),
                "transfer": _compact_estimate(role.get("transfer_guesstimate")),
            }
        result[str(sport_id)] = {"roles": roles}
    return result


def compact_player_detail(source: Mapping[str, Any]) -> dict[str, Any]:
    """Select only derived fields displayed by the public portfolio explorer."""
    player = _pick(
        source.get("player"),
        "id",
        "player_id",
        "name",
        "sport",
        "sport_label",
        "season",
        "role",
        "position",
        "team",
        "height_cm",
        "weight_kg",
        "age",
    )
    native = source.get("native") or {}
    observed = _pick(
        native.get("observed"),
        "kind",
        "status",
        "value",
        "quality_percentile",
        "availability_percentile",
        "total_impact_percentile",
        "sustained_3y_percentile",
        "reference_athletes",
        "opportunity_reliability",
        "evidence_class",
    )
    return {
        "schema_version": PUBLIC_SITE_SCHEMA_VERSION,
        "player": player,
        "native": {
            "observed": observed,
            "forecast": _compact_estimate(native.get("forecast"), include_decision=True),
            "build_profile_forecast": _compact_estimate(
                native.get("build_profile_forecast"), include_decision=True
            ),
        },
        "profile": _compact_profile(source.get("native_profile")),
        "targets": _compact_targets(source.get("targets")),
    }


def _compact_sports(source: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sports: list[dict[str, Any]] = []
    for sport in source:
        roles = [
            _pick(role, "id", "key", "label", "evidence_status", "limitation")
            for role in sport.get("roles", [])
            if isinstance(role, Mapping)
        ]
        sports.append({**_pick(sport, "id", "label"), "roles": roles})
    return sports


def _write(path: Path, value: Any) -> bytes:
    payload = _json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def export_public_site(
    root: Path | str,
    output_dir: Path | str,
    *,
    featured_cases: Iterable[Mapping[str, str]] = FEATURED_CASES,
) -> dict[str, Any]:
    """Export an allowlisted, content-hashed static dataset and return its summary."""
    root = Path(root).resolve()
    output = Path(output_dir).resolve()
    portal = root / "portal-all-roles"
    manifest_path = portal / "data" / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            "The frozen all-role portal export is missing. Run build-all-roles-portal first."
        )
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_players = source_manifest.get("players") or []
    by_id: dict[str, Mapping[str, Any]] = {}
    for player in source_players:
        player_id = str(player.get("id", ""))
        if player_id in by_id:
            raise ValueError(f"Duplicate player in source manifest: {player_id}")
        by_id[player_id] = player

    cases = [dict(case) for case in featured_cases]
    requested_ids = [str(case["player_id"]) for case in cases]
    if len(requested_ids) != len(set(requested_ids)):
        raise ValueError("Featured player IDs must be unique")
    missing = [player_id for player_id in requested_ids if player_id not in by_id]
    if missing:
        raise ValueError(f"Featured players missing from source export: {', '.join(missing)}")

    with tempfile.TemporaryDirectory(prefix="athlete-site-export-", dir=output.parent) as temporary:
        staged = Path(temporary) / "data"
        player_entries: list[dict[str, Any]] = []
        detail_bytes = 0
        for player_id in requested_ids:
            source_entry = by_id[player_id]
            relative_detail = Path(str(source_entry.get("detail_path", "")))
            if relative_detail.is_absolute() or ".." in relative_detail.parts:
                raise ValueError(f"Unsafe detail path for {player_id}: {relative_detail}")
            source_path = portal / relative_detail
            if not source_path.is_file():
                raise FileNotFoundError(f"Missing player detail for {player_id}: {source_path}")
            source_detail = json.loads(source_path.read_text(encoding="utf-8"))
            compact = compact_player_detail(source_detail)
            payload = _json_bytes(compact)
            if len(payload) > MAX_PLAYER_BYTES:
                raise ValueError(
                    f"Public detail for {player_id} is {len(payload):,} bytes; budget is "
                    f"{MAX_PLAYER_BYTES:,}"
                )
            digest = hashlib.sha256(payload).hexdigest()[:20]
            detail_path = f"data/players/{digest}.json"
            (staged / "players").mkdir(parents=True, exist_ok=True)
            (staged / "players" / f"{digest}.json").write_bytes(payload)
            detail_bytes += len(payload)
            player_entries.append(
                {
                    **_pick(
                        source_entry,
                        "id",
                        "player_id",
                        "name",
                        "sport",
                        "sport_label",
                        "season",
                        "role",
                        "position",
                        "team",
                        "height_cm",
                        "weight_kg",
                        "age",
                    ),
                    "detail_path": detail_path,
                }
            )

        model_metadata = {
            "schema_version": PUBLIC_SITE_SCHEMA_VERSION,
            "model": source_manifest.get("model"),
            "claims": source_manifest.get("claims"),
            "limitations": source_manifest.get("limitations"),
            "feature_labels": FEATURE_LABELS,
            "release_boundary": (
                "Curated derived model outputs only. Raw data, processed rows, saved estimators, "
                "provider assets, and league or team marks are not included."
            ),
            "attribution": [
                {
                    "source": "nflverse",
                    "url": "https://nflverse.nflverse.com/",
                    "note": "NFL research data; individual upstream obligations remain documented in the repository.",
                },
                {
                    "source": "MoneyPuck",
                    "url": "https://moneypuck.com/data.htm",
                    "note": "NHL research data; attribution and non-commercial conditions apply.",
                },
                {
                    "source": "Wikidata",
                    "url": "https://www.wikidata.org/wiki/Wikidata:Licensing",
                    "note": "CC0 profile enrichment used only where strict identity matching succeeded.",
                },
            ],
        }
        _write(staged / "model-metadata.json", model_metadata)

        by_sport: dict[str, int] = {}
        for player in player_entries:
            sport = str(player.get("sport", "unknown"))
            by_sport[sport] = by_sport.get(sport, 0) + 1
        public_manifest = {
            "schema_version": PUBLIC_SITE_SCHEMA_VERSION,
            "generated_at": source_manifest.get("generated_at"),
            "title": "Athlete Translation Lab — Portfolio Edition",
            "portfolio_edition": True,
            "snapshot": source_manifest.get("snapshot"),
            "sports": _compact_sports(source_manifest.get("sports") or []),
            "players": sorted(player_entries, key=lambda item: str(item.get("name", ""))),
            "featured_cases": cases,
            "defaults": {
                "player_id": "nhl:8478402",
                "target_sport": "nba",
                "target_role": "guard",
            },
            "counts": {"players": len(player_entries), "by_sport": by_sport},
            "model_metadata_path": "data/model-metadata.json",
            "public_notice": (
                "This curated static edition contains derived research outputs for demonstration. "
                "Cross-sport results are analogies, not probabilities of successful transfer."
            ),
        }
        manifest_payload = _write(staged / "manifest.json", public_manifest)
        (staged / GENERATED_MARKER).write_text(
            "Generated by possession_lab.public_site_export.\n", encoding="utf-8"
        )

        if output.exists():
            marker = output / GENERATED_MARKER
            if not marker.is_file():
                raise ValueError(f"Refusing to replace unmarked directory: {output}")
            shutil.rmtree(output)
        shutil.copytree(staged, output)

    return {
        "players": len(player_entries),
        "manifest_bytes": len(manifest_payload),
        "player_detail_bytes": detail_bytes,
        "output": str(output),
    }

