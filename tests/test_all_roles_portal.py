import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from possession_lab.all_roles_portal import (
    _body_fit,
    _body_fit_references,
    _latest_active_rows,
    _safe,
    build_all_roles_portal,
)


def _observed_rows() -> pd.DataFrame:
    shared = {
        "position": "F",
        "role": "forward",
        "team": "LAL",
        "height_cm": 203.2,
        "weight_kg": 113.4,
        "age": 40.0,
        "target_status": "eligible",
        "evidence_status": "research_proxy",
        "minimum_opportunity": 300.0,
        "rostered_weeks": 12.0,
        "observed_role_percentile": 97.5,
        "quality_percentile": 98.0,
        "availability_percentile": 70.0,
        "total_impact_percentile": 99.0,
        "sustained_3y_percentile": 96.0,
        "reference_athletes": 150.0,
        "domain_scoring_percentile": 96.0,
        "dimension_scoring_finishing_percentile": 95.0,
    }
    return pd.DataFrame(
        [
            {
                **shared,
                "sport": "nba",
                "player_id": "1966",
                "name": "LeBron James",
                "season": 2024,
                "opportunity": 1_500.0,
            },
            {
                **shared,
                "sport": "nba",
                "player_id": "1966",
                "name": "LeBron James",
                "season": 2025,
                "opportunity": 1_300.0,
            },
            {
                **shared,
                "sport": "nba",
                "player_id": "3975",
                "name": "Stephen Curry",
                "season": 2025,
                "team": "GSW",
                "role": "guard",
                "position": "G",
                "height_cm": 188.0,
                "weight_kg": 84.0,
                "opportunity": 2_000.0,
            },
            {
                **shared,
                "sport": "nba",
                "player_id": "2326307",
                "name": "Seth Curry",
                "season": 2025,
                "team": "CHA",
                "role": "guard",
                "position": "G",
                "height_cm": 185.0,
                "weight_kg": 84.0,
                "opportunity": 800.0,
            },
            {
                **shared,
                "sport": "nfl",
                "player_id": "active-unscored",
                "name": "Active Low Sample",
                "season": 2025,
                "team": "AAA",
                "role": "WR",
                "position": "WR",
                "target_status": "low_sample",
                "observed_role_percentile": np.nan,
                "opportunity": 1.0,
            },
            {
                **shared,
                "sport": "nfl",
                "player_id": "identity-only-lineman",
                "name": "Identity Only Lineman",
                "season": 2025,
                "team": "BBB",
                "role": "IOL",
                "position": "G",
                "target_status": "abstain_source_rights_and_label_limit",
                "observed_role_percentile": np.nan,
                "opportunity": np.nan,
            },
            {
                **shared,
                "sport": "nhl",
                "player_id": "roster-only",
                "name": "Roster Only",
                "season": 2025,
                "team": "AAA",
                "role": "center",
                "position": "C",
                "opportunity": 0.0,
            },
        ]
    )


def _score(profile: pd.Series) -> dict:
    value = float(profile["observed_role_percentile"]) if pd.notna(
        profile["observed_role_percentile"]
    ) else None
    return {
        "player": {
            "sport": profile["sport"],
            "player_id": str(profile["player_id"]),
            "name": profile["name"],
            "season": int(profile["season"]),
            "role": profile["role"],
            "height_cm": profile["height_cm"],
            "weight_kg": profile["weight_kg"],
            "age": profile["age"],
        },
        "native": {
            "observed": {
                "kind": "observed_role_percentile",
                "status": profile["target_status"],
                "value": value,
                "evidence_class": "observed_native_role_season",
            },
            "forecast": {
                "kind": "native_forecast_percentile",
                "status": "available" if value is not None else "withheld_no_fitted_model",
                "value": 72.0 if value is not None else None,
                "target_season": 2026,
                "top_contributions": [{"feature": "height_cm", "contribution": 2.5}],
                "ood": {"status": "in_domain", "features": []},
                "evidence_class": "prospective_native_model",
            },
        },
        "targets": {
            "nfl": {
                "roles": {
                    "WR": {
                        "label": "Wide receiver",
                        "evidence_status": "research_proxy",
                        "limitation": "Public box-score proxy.",
                        "physical_only": {
                            "kind": "cross_sport_physical_estimate",
                            "status": "available",
                            "value": 64.0,
                            "top_contributions": [
                                {"feature": "height_cm", "contribution": 4.0, "imputed": False}
                            ],
                            "ood": {"status": "in_domain", "features": []},
                            "evidence_class": "physical_association_only",
                        },
                        "transfer_guesstimate": {
                            "kind": "cross_sport_transfer_guesstimate",
                            "status": "available",
                            "value": 68.0,
                            "top_contributions": [
                                {
                                    "feature": "dimension_scoring_finishing_percentile",
                                    "contribution": 6.0,
                                    "imputed": False,
                                }
                            ],
                            "ood": {"status": "in_domain", "features": []},
                            "analogy_sensitivity_range": [57.0, 79.0],
                            "range_warning": "Not a calibrated confidence interval.",
                            "dimensions": ["scoring_finishing"],
                            "semantic_bridge_grade": "limited",
                            "mapping_version": "fixture-bridge",
                            "evidence_class": "unvalidated_cross_sport_analogy",
                        },
                    }
                }
            }
        },
        "claims": {"cross_sport": "Exploratory analogy only."},
    }


@pytest.fixture
def portal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    observed_path = tmp_path / "data" / "processed" / "all_roles" / "observed_scores.parquet"
    observed_path.parent.mkdir(parents=True)
    _observed_rows().to_parquet(observed_path, index=False)
    model_path = tmp_path / "models" / "all_roles" / "all_roles_v1.joblib"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"fixture model artifact")
    artifact = {
        "schema_version": "fixture-schema",
        "role_taxonomy_version": "fixture-roles",
        "target_version": "fixture-target",
        "bridge_version": "fixture-bridge",
        "frozen_test_season": 2025,
        "physical_models": {"nfl:WR": {"model": object(), "status": "beats_neutral_baseline"}},
        "native_forecast_models": {
            "nba:forward": {
                "model": object(),
                "forecast_support": "supported_over_history_baselines",
            }
        },
        "bridge_models": {"nba:forward->nfl:WR": {"model": object(), "status": "beats_neutral_baseline"}},
        "claims": {"cross_sport": "Exploratory analogy only."},
    }
    monkeypatch.setattr(
        "possession_lab.all_roles_portal.load_all_role_models", lambda root: artifact
    )
    monkeypatch.setattr("possession_lab.all_roles_portal.score_all_roles_profile", lambda _, row: _score(row))
    return tmp_path


def test_build_portal_exports_latest_active_players_and_four_score_contract(portal_root: Path):
    output = portal_root / "site"
    manifest = build_all_roles_portal(portal_root, output)

    assert manifest["counts"]["players"] == 5
    assert manifest["defaults"] == {"player_id": "nba:1966", "target_sport": "nba"}
    assert {player["id"] for player in manifest["players"]} == {
        "nba:1966",
        "nba:3975",
        "nba:2326307",
        "nfl:active-unscored",
        "nfl:identity-only-lineman",
    }
    assert "nhl:roster-only" not in {player["id"] for player in manifest["players"]}
    assert [player["season"] for player in manifest["players"] if player["id"] == "nba:1966"] == [
        2025
    ]
    assert [player["name"] for player in manifest["players"] if player["id"] == "nba:3975"] == [
        "Stephen Curry"
    ]
    assert [player["name"] for player in manifest["players"] if player["id"] == "nba:2326307"] == [
        "Seth Curry"
    ]

    written = json.loads((output / "data" / "manifest.json").read_text())
    lebron = next(player for player in written["players"] if player["id"] == "nba:1966")
    detail = json.loads((output / lebron["detail_path"]).read_text(), parse_constant=None)
    assert detail["native"]["observed"]["kind"] == "observed_role_percentile"
    assert detail["native"]["forecast"]["kind"] == "native_forecast_percentile"
    wr = detail["targets"]["nfl"]["roles"]["WR"]
    assert wr["physical_only"]["kind"] == "cross_sport_physical_estimate"
    assert wr["transfer_guesstimate"]["kind"] == "cross_sport_transfer_guesstimate"
    assert wr["body_fit"]["kind"] == "target_role_body_centrality"
    assert wr["body_fit"]["status"] == "withheld_insufficient_reference"
    assert detail["native_profile"]["domains"][0]["value"] == 96.0
    assert detail["native_profile"]["transferable_dimensions"][0]["value"] == 95.0
    assert written["model"]["sha256"]
    assert written["snapshot"]["source_sha256"]


def test_latest_active_rows_rejects_duplicate_player_season():
    frame = _observed_rows()
    duplicate = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate sport-player-season"):
        _latest_active_rows(duplicate)


def test_safe_produces_strict_json_scalars():
    value = _safe({"nan": np.nan, "int": np.int64(4), "bool": np.bool_(True)})
    assert value == {"nan": None, "int": 4, "bool": True}
    assert json.dumps(value, allow_nan=False)


def test_body_fit_is_descriptive_centrality_separate_from_outcome_models():
    athletes = pd.DataFrame(
        {
            "sport": ["nba"] * 24,
            "role": ["guard"] * 24,
            "player_id": [str(index) for index in range(24)],
            "height_cm": np.linspace(180.0, 196.0, 24),
            "weight_kg": np.linspace(75.0, 99.0, 24) + np.sin(np.arange(24)),
        }
    )
    reference = _body_fit_references(athletes)["nba:guard"]
    center = _body_fit(
        {"height_cm": reference["center"][0], "weight_kg": reference["center"][1]},
        reference,
    )
    extreme = _body_fit({"height_cm": 215.0, "weight_kg": 135.0}, reference)

    assert center["status"] == "available"
    assert center["value"] > extreme["value"]
    assert center["kind"] == "target_role_body_centrality"
    assert center["features_used"] == ["height_cm", "weight_kg"]
    assert "ability" in center["note"]
    assert _body_fit({"height_cm": None, "weight_kg": 90.0}, reference)["value"] is None


def test_static_portal_names_four_scores_and_uses_local_assets_only():
    portal = Path(__file__).parents[1] / "portal-all-roles"
    html = (portal / "index.html").read_text()
    script = (portal / "app.js").read_text()
    for label in (
        "Native observed",
        "Native next-season forecast",
        "Target-role physical-only estimate",
        "Cross-sport transfer guesstimate",
    ):
        assert label in html or label in script
    assert "not a probability" in html.lower() or "not a probability" in script.lower()
    assert "https://" not in html
    assert "http://" not in html
    assert "innerHTML" not in script
    assert "textContent" in script


def test_compact_portal_is_single_role_and_uses_shared_export_safely():
    portal = Path(__file__).parents[1] / "portal-all-roles" / "compact"
    html = (portal / "index.html").read_text()
    script = (portal / "app.js").read_text()
    assert "Body fit" in html or "Body fit" in script
    assert 'select.id = "target-role"' in script
    for label in (
        "Native observed",
        "Next-season forecast",
        "Physical-only estimate",
        "Transfer efficacy guesstimate",
    ):
        assert label in script
    assert "not a probability" in html.lower() or "not a probability" in script.lower()
    assert 'new URL("../data/", document.baseURI)' in script
    assert "innerHTML" not in script
    assert "https://" not in html
    assert "http://" not in html


def test_friendly_portal_explains_each_single_role_result_in_plain_language():
    portal = Path(__file__).parents[1] / "portal-all-roles" / "friendly"
    html = (portal / "index.html").read_text()
    script = (portal / "app.js").read_text()

    assert 'sportSelect.id = "target-sport"' in script
    assert 'roleSelect.id = "target-role"' in script
    assert 'input.type = "radio"' in script
    assert "Body + playing style" in script
    assert "Body + age only" in script
    assert "Why did the model say that?" in script
    assert "explanationSentences(score, payload, state.basis)" in script
    plain_copy = f"{html}\n{script}".lower()
    assert "not a probability" in plain_copy or "not the probability" in plain_copy
    assert "no score shown is not zero" in html.lower() or "no score shown is not zero" in script.lower()
    assert 'new URL("../data/", document.baseURI)' in script
    assert "innerHTML" not in script
    assert "https://" not in html
    assert "http://" not in html


def test_profile_portal_leads_with_observed_native_result_before_secondary_models():
    portal = Path(__file__).parents[1] / "portal-all-roles" / "profile"
    html = (portal / "index.html").read_text()
    script = (portal / "app.js").read_text()

    for label in (
        "Home-role anchor",
        "What has this player already shown?",
        "Experimental forecast",
        "Secondary models",
        "Now explore other roles",
    ):
        assert label in html or label in script

    render = script.split("function renderResult", maxsplit=1)[1].split(
        "function announceResult", maxsplit=1
    )[0]
    assert render.index("observedAnchor()") < render.index("forecastSection()")
    assert render.index("forecastSection()") < render.index("comparisonSection()")
    assert 'state.players.find((item) => item.id === "nhl:8478402")' in script
    assert "observed.reference_athletes" in script
    assert "not a prediction" in script.lower()
    assert "does not re-grade" in script.lower()
    assert "not a sport-switch probability" in script.lower()
    assert 'new URL("../data/", document.baseURI)' in script
    assert "innerHTML" not in script
    assert "https://" not in html
    assert "http://" not in html


def test_stories_portal_uses_six_live_results_without_hardcoded_scores():
    portal = Path(__file__).parents[1] / "portal-all-roles" / "stories"
    html = (portal / "index.html").read_text()
    script = (portal / "app.js").read_text()
    story_config = script.split("const storyConfig = [", maxsplit=1)[1].split("];", maxsplit=1)[0]

    assert re.findall(r'playerId: "([^"]+)"', story_config) == [
        "nhl:8478402",
        "nba:3975",
        "nfl:00-0034796",
        "epl:fpl:223094",
        "epl:fpl:97032",
        "nba:5104157",
    ]
    assert re.findall(r'target: \{ sport: "([^"]+)", role: "([^"]+)" \}', story_config) == [
        ("nba", "guard"),
        ("epl", "FWD"),
        ("nhl", "left_wing"),
        ("nfl", "WR"),
        ("nba", "guard"),
        ("nfl", "WR"),
    ]
    assert "score:" not in story_config
    assert "value:" not in story_config
    assert "fetchJson(player.detail_path)" in script
    for live_value in ("transfer.value", "body.value", "native.value"):
        assert live_value in script
    assert "not the probability" in html.lower() or "not a probability" in script.lower()
    assert "not that the athlete scored zero" in html.lower() or "no score is not zero" in script.lower()
    assert 'new URL("../data/", document.baseURI)' in script
    assert "innerHTML" not in script
    assert "https://" not in html
    assert "http://" not in html
