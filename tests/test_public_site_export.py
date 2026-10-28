import json
from pathlib import Path

import pytest

from possession_lab.public_site_export import GENERATED_MARKER, export_public_site


def _source_export(root: Path) -> None:
    data = root / "portal-all-roles" / "data"
    detail = {
        "player": {
            "id": "nba:1",
            "player_id": "1",
            "name": "Example Player",
            "sport": "nba",
            "sport_label": "NBA",
            "season": 2025,
            "role": "guard",
            "team": "EX",
            "height_cm": 190.0,
            "weight_kg": 85.0,
            "age": 25.0,
        },
        "native": {
            "observed": {"status": "eligible", "value": 91.0, "reference_athletes": 100},
            "forecast": {
                "status": "available",
                "value": 84.0,
                "features_used": ["private_repeated_feature_list"],
                "prediction_range_90": {
                    "lower": 60.0,
                    "upper": 100.0,
                    "frozen_empirical_coverage": 0.88,
                },
                "top_contributions": [
                    {"feature": "availability_percentile", "contribution": 12.0, "imputed": False}
                ],
                "ood": {"status": "in_domain", "features": [{"feature": "height_cm"}]},
            },
            "build_profile_forecast": {"status": "unavailable"},
        },
        "native_profile": {
            "domains": [{"key": "domain_scoring_percentile", "label": "scoring", "value": 95.0}],
            "transferable_dimensions": [],
            "target_status": "eligible",
        },
        "targets": {
            "nhl": {
                "roles": {
                    "center": {
                        "label": "Center",
                        "evidence_status": "research_proxy",
                        "body_fit": {"status": "available", "value": 72.0, "reference_athletes": 80},
                        "physical_only": {"status": "available", "value": 58.0},
                        "transfer_guesstimate": {"status": "available", "value": 73.0},
                    }
                }
            }
        },
        "claims": {"must_not_be_repeated": True},
    }
    detail_path = data / "players" / "source.json"
    detail_path.parent.mkdir(parents=True)
    detail_path.write_text(json.dumps(detail), encoding="utf-8")
    manifest = {
        "schema_version": 3,
        "generated_at": "2026-01-01T00:00:00Z",
        "model": {"sha256": "model"},
        "snapshot": {"source_sha256": "source"},
        "sports": [
            {
                "id": "nba",
                "label": "NBA",
                "roles": [{"id": "guard", "label": "Guard", "evidence_status": "research_proxy"}],
            }
        ],
        "players": [
            {
                "id": "nba:1",
                "player_id": "1",
                "name": "Example Player",
                "sport": "nba",
                "sport_label": "NBA",
                "season": 2025,
                "role": "guard",
                "team": "EX",
                "detail_path": "data/players/source.json",
            }
        ],
        "claims": {"bridge": "analogy only"},
        "limitations": ["Not a probability."],
    }
    (data / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_public_export_is_compact_deterministic_and_manifest_reachable(tmp_path: Path):
    _source_export(tmp_path)
    cases = [
        {
            "player_id": "nba:1",
            "target_sport": "nhl",
            "target_role": "center",
            "story": "Test case",
        }
    ]
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_summary = export_public_site(tmp_path, first, featured_cases=cases)
    export_public_site(tmp_path, second, featured_cases=cases)

    first_files = {
        path.relative_to(first): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files
    assert first_summary["players"] == 1
    assert first_summary["player_detail_bytes"] < 30_000
    assert (first / GENERATED_MARKER).is_file()

    manifest = json.loads((first / "manifest.json").read_text())
    detail_path = manifest["players"][0]["detail_path"].removeprefix("data/")
    detail = json.loads((first / detail_path).read_text())
    rendered = json.dumps(detail)
    assert "private_repeated_feature_list" not in rendered
    assert "must_not_be_repeated" not in rendered
    assert detail["native"]["forecast"]["range"]["lower"] == 60.0
    assert detail["native"]["forecast"]["ood_status"] == "in_domain"


def test_public_export_refuses_missing_featured_player(tmp_path: Path):
    _source_export(tmp_path)
    with pytest.raises(ValueError, match="missing from source export"):
        export_public_site(
            tmp_path,
            tmp_path / "output",
            featured_cases=[
                {
                    "player_id": "nba:missing",
                    "target_sport": "nhl",
                    "target_role": "center",
                    "story": "Missing",
                }
            ],
        )

