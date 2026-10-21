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
