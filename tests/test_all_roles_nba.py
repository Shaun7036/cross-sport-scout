from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possession_lab.all_roles_nba import (
    OUTPUT_COLUMNS,
    RAW_TOTAL_COLUMNS,
    _derive_rates,
    build_nba_all_roles_panel,
)


def test_derive_rates_uses_standard_shooting_formulas() -> None:
    totals = pd.DataFrame(
        {
            "opportunity": [30.0],
            "points": [30.0],
            "field_goals_made": [10.0],
            "field_goals_attempted": [20.0],
            "three_point_field_goals_made": [4.0],
            "three_point_field_goals_attempted": [10.0],
            "free_throws_made": [8.0],
            "free_throws_attempted": [10.0],
            "assists": [8.0],
            "turnovers": [4.0],
            "offensive_rebounds": [2.0],
            "defensive_rebounds": [6.0],
            "steals": [2.0],
            "blocks": [1.0],
            "fouls": [3.0],
            "plus_minus": [6.0],
        }
    )
    result = _derive_rates(totals).iloc[0]
    assert result.points_per_36 == pytest.approx(36.0)
    assert result.true_shooting_pct == pytest.approx(30.0 / (2.0 * (20.0 + 0.44 * 10.0)))
    assert result.effective_fg_pct == pytest.approx((10.0 + 0.5 * 4.0) / 20.0)
    assert result.three_point_pct == pytest.approx(0.4)
    assert result.three_point_attempt_rate == pytest.approx(0.5)
    assert result.free_throw_pct == pytest.approx(0.8)
    assert result.free_throw_attempt_rate == pytest.approx(0.5)
    assert result.assists_per_36 == pytest.approx(9.6)
    assert result.assist_turnover_ratio == pytest.approx(2.0)
    assert result.turnovers_per_36 == pytest.approx(4.8)
    assert result.offensive_rebounds_per_36 == pytest.approx(2.4)
    assert result.defensive_rebounds_per_36 == pytest.approx(7.2)
    assert result.steals_per_36 == pytest.approx(2.4)
    assert result.blocks_per_36 == pytest.approx(1.2)
    assert result.fouls_per_36 == pytest.approx(3.6)
    assert result.plus_minus_per_36 == pytest.approx(7.2)
    assert result.availability_minutes == 30.0


def test_derive_rates_leaves_zero_denominators_missing() -> None:
    totals = pd.DataFrame(
        {
            "opportunity": [0.0],
            "points": [0.0],
            "field_goals_made": [0.0],
            "field_goals_attempted": [0.0],
            "three_point_field_goals_made": [0.0],
            "three_point_field_goals_attempted": [0.0],
            "free_throws_made": [0.0],
            "free_throws_attempted": [0.0],
            "assists": [2.0],
            "turnovers": [0.0],
            "offensive_rebounds": [0.0],
            "defensive_rebounds": [0.0],
            "steals": [0.0],
            "blocks": [0.0],
            "fouls": [0.0],
            "plus_minus": [0.0],
        }
    )
    result = _derive_rates(totals).iloc[0]
    rate_columns = [column for column in result.index if column.endswith("_per_36")]
    assert result[rate_columns].isna().all()
    assert pd.isna(result.true_shooting_pct)
    assert pd.isna(result.effective_fg_pct)
    assert pd.isna(result.three_point_pct)
    assert pd.isna(result.assist_turnover_ratio)
    assert result.availability_minutes == 0.0


def _box_row(
    athlete_id: int,
    name: str,
    game_id: str,
    team_id: int,
    team: str,
    *,
    minutes: float = 24.0,
    points: float = 12.0,
    starter: bool = False,
    did_not_play: bool = False,
    season_type: int = 2,
    position: str = "G",
) -> dict:
    row = {
        "game_id": game_id,
        "season_type": season_type,
        "athlete_id": athlete_id,
        "athlete_display_name": name,
        "team_id": team_id,
        "team_abbreviation": team,
        "minutes": np.nan if did_not_play else minutes,
        "starter": starter,
        "did_not_play": did_not_play,
        "athlete_position_abbreviation": position,
        "field_goals_made": np.nan if did_not_play else 5.0,
        "field_goals_attempted": np.nan if did_not_play else 10.0,
        "three_point_field_goals_made": np.nan if did_not_play else 2.0,
        "three_point_field_goals_attempted": np.nan if did_not_play else 5.0,
        "free_throws_made": np.nan if did_not_play else 0.0,
        "free_throws_attempted": np.nan if did_not_play else 0.0,
        "offensive_rebounds": np.nan if did_not_play else 1.0,
        "defensive_rebounds": np.nan if did_not_play else 3.0,
        "rebounds": np.nan if did_not_play else 4.0,
        "assists": np.nan if did_not_play else 4.0,
        "steals": np.nan if did_not_play else 1.0,
        "blocks": np.nan if did_not_play else 0.0,
        "turnovers": np.nan if did_not_play else 2.0,
        "fouls": np.nan if did_not_play else 1.0,
        "plus_minus": np.nan if did_not_play else "+3",
        "points": np.nan if did_not_play else points,
    }
    assert set(RAW_TOTAL_COLUMNS).issubset(row)
    return row


def test_builder_aggregates_trades_filters_games_and_preserves_curry_identities(tmp_path) -> None:
    raw_dir = tmp_path / "data" / "raw" / "nba" / "2022"
    raw_dir.mkdir(parents=True)
    processed_dir = tmp_path / "data" / "processed" / "nba"
    processed_dir.mkdir(parents=True)

    raw = pd.DataFrame(
        [
            _box_row(1966, "LeBron James", "g1", 1, "LAL", minutes=30, points=30, starter=True),
            _box_row(3975, "Stephen Curry", "g1", 2, "GS", minutes=32, points=28, starter=True),
            _box_row(2326307, "Seth Curry", "g1", 2, "GS", minutes=20, points=10),
            _box_row(1966, "LeBron James", "g2", 3, "MIA", minutes=20, points=20, starter=True),
            _box_row(999, "Reference Player", "g2", 4, "BOS", minutes=10, points=4),
            _box_row(
                2326307,
                "Seth Curry",
                "g2",
                4,
                "BOS",
                did_not_play=True,
            ),
            _box_row(1966, "LeBron James", "playoff", 1, "LAL", season_type=3),
            _box_row(999, "Reference Player", "playoff", 4, "BOS", season_type=3),
        ]
    )
    raw.to_parquet(raw_dir / "player_box_2022.parquet", index=False)

    processed = pd.DataFrame(
        {
            "player_id": ["1966", "3975", "2326307", "999"],
            "name": ["LeBron James", "Stephen Curry", "Seth Curry", "Reference Player"],
            "season": [2021, 2021, 2021, 2021],
            "position": ["SF", "PG", "SG", "C"],
            "role": ["forward", "guard", "guard", "center"],
            "teams": ["LAL;MIA", "GS", "GS", "BOS"],
            "height_cm": [206.0, 188.0, 188.0, 210.0],
            "weight_kg": [113.0, 84.0, 84.0, 110.0],
            "age": [37.0, 33.0, 31.0, 26.0],
        }
    )
    processed.to_parquet(processed_dir / "player_seasons.parquet", index=False)

    panel = build_nba_all_roles_panel(tmp_path, seasons=[2021])
    assert list(panel.columns) == list(OUTPUT_COLUMNS)
    assert not panel.duplicated(["player_id", "season"]).any()
    assert set(panel.player_id) == {"1966", "3975", "2326307", "999"}

    by_id = panel.set_index("player_id")
    assert by_id.loc["1966", "name"] == "LeBron James"
    assert by_id.loc["3975", "name"] == "Stephen Curry"
    assert by_id.loc["2326307", "name"] == "Seth Curry"
    assert by_id.loc["1966", "games"] == 2
    assert by_id.loc["1966", "games_started"] == 2
    assert by_id.loc["1966", "opportunity"] == 50.0
    assert by_id.loc["1966", "availability_minutes"] == 50.0
    assert by_id.loc["1966", "points"] == 50.0
    assert by_id.loc["1966", "team"] == "LAL;MIA"
    assert by_id.loc["1966", "role"] == "forward"


def test_builder_requires_processed_identity_for_every_played_player(tmp_path) -> None:
    raw_dir = tmp_path / "data" / "raw" / "nba" / "2022"
    raw_dir.mkdir(parents=True)
    processed_dir = tmp_path / "data" / "processed" / "nba"
    processed_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            _box_row(1, "Known", "g1", 1, "ATL"),
            _box_row(2, "Unknown", "g1", 2, "BOS"),
        ]
    ).to_parquet(raw_dir / "player_box_2022.parquet", index=False)
    pd.DataFrame(
        {
            "player_id": ["1"],
            "name": ["Known"],
            "season": [2021],
            "position": ["G"],
            "role": ["guard"],
            "teams": ["ATL"],
            "height_cm": [190.0],
            "weight_kg": [85.0],
            "age": [25.0],
        }
    ).to_parquet(processed_dir / "player_seasons.parquet", index=False)

    with pytest.raises(ValueError, match="lack canonical processed identities"):
        build_nba_all_roles_panel(tmp_path, seasons=[2021])
