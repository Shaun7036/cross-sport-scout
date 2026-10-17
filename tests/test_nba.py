from __future__ import annotations

import numpy as np
import pandas as pd

from possession_lab.sports.nba import (
    COUNT_COLUMNS,
    _appearance_fields,
    _build_player_season,
    _filter_regular_box,
    map_role,
)


def test_role_mapping_uses_stable_broad_families() -> None:
    assert map_role("PG") == "guard"
    assert map_role("SG") == "guard"
    assert map_role("SF") == "forward"
    assert map_role("PF") == "forward"
    assert map_role("C") == "center"
    assert map_role(None) == "unknown"


def test_regular_filter_removes_all_star_playoffs_and_cup_final() -> None:
    rows = []
    for game_id, season_type, teams in [
        ("regular", 2, [1, 2]),
        ("all-star", 2, [31, 32]),
        ("401607495", 2, [11, 13]),
        ("playoff", 3, [1, 2]),
    ]:
        for team_id in teams:
            rows.append({"game_id": game_id, "season_type": season_type, "team_id": team_id})
    regular, excluded, qa = _filter_regular_box(pd.DataFrame(rows), 2023)
    assert set(regular.game_id) == {"regular"}
    assert set(excluded.game_id) == {"all-star", "401607495"}
    assert qa["exhibition_rows_excluded"] == 2
    assert qa["cup_final_rows_excluded"] == 2


def _game(
    player_id: str,
    game_id: str,
    team_id: int,
    team: str,
    minutes: float,
    steals: float,
    blocks: float,
    did_not_play: bool = False,
) -> dict:
    row = {
        "player_id": player_id,
        "game_id": game_id,
        "team_id": team_id,
        "team": team,
        "name": f"Player {player_id}",
        "role": "guard",
        "position": "G",
        "game_date": pd.Timestamp("2022-01-01"),
        "minutes": minutes,
        "steals": steals,
        "blocks": blocks,
        "starter": False,
        "did_not_play": did_not_play,
    }
    for column in COUNT_COLUMNS:
        row.setdefault(column, 0.0 if not did_not_play else np.nan)
    return row


def test_player_season_preserves_trade_stints_and_explicit_zero_appearance() -> None:
    raw = pd.DataFrame(
        [
            _game("1", "g1", 1, "ATL", 10.0, 1.0, 0.0),
            _game("1", "g2", 2, "BOS", 20.0, 2.0, 1.0),
            _game("2", "g1", 1, "ATL", np.nan, np.nan, np.nan, did_not_play=True),
        ]
    )
    games = _appearance_fields(raw)
    profile = pd.DataFrame(
        {
            "player_id": ["1", "2"],
            "name_profile": ["Player 1", "Player 2"],
            "position_profile": ["G", "G"],
            "role_profile": ["guard", "guard"],
        }
    )
    panel = _build_player_season(games, profile, 2021).set_index("player_id")
    assert panel.loc["1", "opportunity"] == 30.0
    assert panel.loc["1", "steals"] == 3.0
    assert panel.loc["1", "team_stint_count"] == 2
    assert bool(panel.loc["1", "traded_midseason"])
    assert panel.loc["2", "opportunity"] == 0.0
    assert panel.loc["2", "steals"] == 0.0
    assert bool(panel.loc["2", "zero_appearance_roster"])
    assert panel.loc["2", "event_total_status"] == "structural_zero_no_recorded_appearance"
