from pathlib import Path

import pandas as pd
import pytest

from possession_lab.all_roles_epl import _aggregate_season, _derive_rates


def test_epl_aggregate_and_rates_preserve_observed_zero(tmp_path: Path):
    source = pd.DataFrame(
        [
            {
                "element": 7,
                "name": "Player",
                "position": "MID",
                "team": "A",
                "minutes": 90,
                "goals_scored": 1,
                "assists": 0,
                "clean_sheets": 1,
                "goals_conceded": 0,
                "saves": 0,
                "yellow_cards": 1,
                "red_cards": 0,
                "penalties_saved": 0,
                "creativity": 12.0,
                "threat": 30.0,
            },
            {
                "element": 7,
                "name": "Player",
                "position": "MID",
                "team": "A",
                "minutes": 45,
                "goals_scored": 0,
                "assists": 1,
                "clean_sheets": 0,
                "goals_conceded": 1,
                "saves": 0,
                "yellow_cards": 0,
                "red_cards": 0,
                "penalties_saved": 0,
                "creativity": 8.0,
                "threat": 15.0,
            },
        ]
    )
    path = tmp_path / "merged_gw.csv"
    source.to_csv(path, index=False)
    aggregated = _aggregate_season(path, 2025).rename(columns={"minutes": "opportunity"})
    result = _derive_rates(aggregated).iloc[0]
    assert result["games"] == 2
    assert result["goals_per_90"] == pytest.approx(2 / 3)
    assert result["assists_per_90"] == pytest.approx(2 / 3)
    assert result["cards_per_90"] == pytest.approx(2 / 3)
    assert result["saves"] == 0


def test_zero_minutes_does_not_invent_per_90_rate():
    frame = pd.DataFrame(
        {
            "opportunity": [0],
            "games": [0],
            "goals_scored": [0],
            "assists": [0],
            "clean_sheets": [0],
            "goals_conceded": [0],
            "saves": [0],
            "yellow_cards": [0],
            "red_cards": [0],
            "penalties_saved": [0],
            "creativity": [0],
            "threat": [0],
        }
    )
    result = _derive_rates(frame).iloc[0]
    assert pd.isna(result["goals_per_90"])
    assert pd.isna(result["clean_sheet_rate"])


def test_epl_optional_expected_and_defensive_fields_are_engineered_when_present(tmp_path: Path):
    source = pd.DataFrame(
        [
            {
                "element": 9,
                "name": "Player",
                "position": "DEF",
                "team": "A",
                "minutes": 90,
                "goals_scored": 1,
                "assists": 0,
                "clean_sheets": 1,
                "goals_conceded": 0,
                "saves": 0,
                "yellow_cards": 0,
                "red_cards": 0,
                "penalties_saved": 0,
                "creativity": 8.0,
                "threat": 20.0,
                "expected_goals": 0.4,
                "expected_assists": 0.2,
                "expected_goal_involvements": 0.6,
                "expected_goals_conceded": 0.8,
                "influence": 30.0,
                "ict_index": 5.8,
                "starts": 1,
                "clearances_blocks_interceptions": 6,
                "defensive_contribution": 4,
                "recoveries": 5,
                "tackles": 2,
            }
        ]
    )
    path = tmp_path / "merged_gw.csv"
    source.to_csv(path, index=False)

    aggregated = _aggregate_season(path, 2025).rename(columns={"minutes": "opportunity"})
    result = _derive_rates(aggregated).iloc[0]

    assert result["expected_goals_per_90"] == pytest.approx(0.4)
    assert result["expected_assists_per_90"] == pytest.approx(0.2)
    assert result["finishing_over_expected_per_90"] == pytest.approx(0.6)
    assert result["goal_prevention_over_expected_per_90"] == pytest.approx(0.8)
    assert result["defensive_actions_per_90"] == pytest.approx(13.0)
    assert result["start_rate"] == pytest.approx(1.0)


def test_epl_optional_fields_remain_missing_for_older_sources(tmp_path: Path):
    source = pd.DataFrame(
        [
            {
                "element": 4,
                "name": "Older Player",
                "position": "MID",
                "team": "B",
                "minutes": 90,
                "goals_scored": 0,
                "assists": 0,
                "clean_sheets": 0,
                "goals_conceded": 1,
                "saves": 0,
                "yellow_cards": 0,
                "red_cards": 0,
                "penalties_saved": 0,
                "creativity": 6.0,
                "threat": 10.0,
            }
        ]
    )
    path = tmp_path / "merged_gw.csv"
    source.to_csv(path, index=False)

    aggregated = _aggregate_season(path, 2021).rename(columns={"minutes": "opportunity"})
    result = _derive_rates(aggregated).iloc[0]

    assert pd.isna(result["expected_goals_per_90"])
    assert pd.isna(result["defensive_actions_per_90"])
