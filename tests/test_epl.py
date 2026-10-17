import json

import numpy as np
import pandas as pd

from possession_lab.sports.epl import (
    _age_on,
    _match_physical_profiles,
    _prepare_common_season,
    _prepare_enhanced_2025,
    recent_season_model,
)


def test_common_panel_uses_stable_fpl_code_and_preserves_missing_defense():
    players = pd.DataFrame(
        {
            "id": [10],
            "code": [12345],
            "first_name": ["Test"],
            "second_name": ["Player"],
            "element_type": [2],
            "team": [1],
        }
    )
    games = pd.DataFrame(
        {
            "element": [10],
            "fixture": [99],
            "minutes": [90],
            "kickoff_time": ["2021-08-14T12:00:00Z"],
            "position": ["DEF"],
            "team": ["Example"],
            "goals_scored": [0],
            "assists": [0],
            "clean_sheets": [1],
            "goals_conceded": [0],
            "saves": [0],
            "yellow_cards": [0],
            "red_cards": [0],
        }
    )
    teams = pd.DataFrame({"id": [1], "name": ["Example"]})

    roster, appearances = _prepare_common_season(players, games, teams, 2021)

    assert roster.loc[0, "player_id"] == "fpl:12345"
    assert appearances.loc[0, "player_id"] == "fpl:12345"
    assert np.isnan(appearances.loc[0, "tackles"])
    assert not appearances.loc[0, "defensive_counts_observed"]


def test_enhanced_panel_keeps_real_defensive_counts_and_filters_nonappearances():
    players = pd.DataFrame(
        {
            "player_id": [10, 11],
            "player_code": [12345, 54321],
            "first_name": ["Test", "Bench"],
            "second_name": ["Player", "Player"],
            "position": ["Defender", "Midfielder"],
        }
    )
    teams = pd.DataFrame({"code": [3], "name": ["Arsenal"]})
    stats = pd.DataFrame(
        {
            "player_id": [10, 11],
            "match_id": ["25-26-prem-a-vs-b", "25-26-prem-a-vs-b"],
            "minutes_played": [90, 0],
            "goals": [0, 0],
            "assists": [0, 0],
            "saves": [0, 0],
            "goals_conceded": [0, 0],
            "tackles": [4, 0],
            "tackles_won": [3, 0],
            "interceptions": [2, 0],
            "recoveries": [7, 0],
            "blocks": [1, 0],
            "defensive_contributions": [14, 0],
        }
    )
    lineups = pd.DataFrame(
        {
            "player_id": [10, 11],
            "match_id": ["25-26-prem-a-vs-b", "25-26-prem-a-vs-b"],
            "team_code": [3, 3],
            "position": ["D", "M"],
            "is_starting": [True, False],
        }
    )
    matches = pd.DataFrame(
        {
            "match_id": ["25-26-prem-a-vs-b"],
            "kickoff_time": ["2025-08-16T12:00:00+00:00"],
        }
    )

    result, qa = _prepare_enhanced_2025(players, teams, [stats], [lineups], [matches])

    assert len(result) == 1
    assert result.loc[0, "player_id"] == "fpl:12345"
    assert result.loc[0, "tackles"] == 4
    assert result.loc[0, "interceptions"] == 2
    assert result.loc[0, "recoveries"] == 7
    assert result.loc[0, "blocks"] == 1
    assert qa["appearance_rows"] == 1


def test_physical_matching_is_team_constrained_and_dated():
    fpl_players = pd.DataFrame(
        {
            "player_code": [12345],
            "first_name": ["Gabriel"],
            "second_name": ["dos Santos Magalhães"],
            "web_name": ["Gabriel"],
            "team_code": [3],
        }
    )
    teams = pd.DataFrame({"code": [3], "fotmob_name": ["Arsenal"]})
    espn = pd.DataFrame(
        {
            "espn_player_id": ["1"],
            "espn_name": ["Gabriel Magalhães"],
            "espn_display_name": ["Gabriel Magalhães"],
            "espn_short_name": ["G. Magalhães"],
            "espn_team": ["Arsenal"],
            "height_cm": [190.5],
            "weight_kg": [87.1],
            "date_of_birth": [pd.Timestamp("1997-12-19", tz="UTC")],
            "physical_source_date": ["2026-10-17"],
        }
    )

    result = _match_physical_profiles(fpl_players, teams, espn)

    assert result.loc[0, "player_id"] == "fpl:12345"
    assert result.loc[0, "height_cm"] == 190.5
    assert result.loc[0, "physical_source_date"] == "2026-10-17"
    assert "not asserted as historic" in result.loc[0, "physical_temporality"]


def test_age_is_computed_at_observation_date():
    assert _age_on(pd.Timestamp("2000-10-01"), pd.Timestamp("2025-08-01")) == 24.0
    assert _age_on(pd.Timestamp("2000-10-01"), pd.Timestamp("2025-10-01")) == 25.0


def test_recent_model_holds_out_whole_players_and_writes_evidence(tmp_path):
    size = 120
    rng = np.random.default_rng(42)
    roles = np.array(["DEF", "MID", "FWD", "GK"])[np.arange(size) % 4]
    height = rng.normal(183, 7, size)
    minutes = rng.integers(700, 3000, size).astype(float)
    role_effect = pd.Series(roles).map({"DEF": 1.8, "MID": 1.5, "FWD": 0.8, "GK": 0.1}).to_numpy()
    rate = np.maximum(0, role_effect + (height - 183) * 0.02 + rng.normal(0, 0.2, size))
    panel = pd.DataFrame(
        {
            "player_id": [f"fpl:{index}" for index in range(size)],
            "name": [f"Player {index}" for index in range(size)],
            "season": 2025,
            "role": roles,
            "opportunity": minutes,
            "age": rng.integers(19, 35, size).astype(float),
            "height_cm": height,
            "weight_kg": rng.normal(77, 8, size),
            "defensive_counts_observed": True,
        }
    )
    for column, multiplier in {
        "tackles": 1.0,
        "interceptions": 0.5,
        "recoveries": 2.0,
        "blocks": 0.25,
    }.items():
        panel[column] = np.rint(rate * multiplier * minutes / 90).astype(float)

    result = recent_season_model(panel, tmp_path, min_minutes=450, random_state=7)

    assert result["status"] == "trained"
    assert result["player_overlap"] == 0
    assert not result["same_season_event_predictors_used"]
    assert all(value["status"] == "trained" for value in result["targets"].values())
    manifest = json.loads((tmp_path / "reports/epl/recent_2025_split_manifest.json").read_text())
    assert not set(manifest["train_player_ids"]) & set(manifest["test_player_ids"])
    assert (tmp_path / "models/epl/recent_2025_tackles_per90.joblib").exists()
