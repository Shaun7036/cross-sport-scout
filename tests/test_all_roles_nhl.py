from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import possession_lab.all_roles_nhl as nhl
from possession_lab.all_roles_nhl import OUTPUT_COLUMNS, build_nhl_all_roles_panel


def _skater_row(
    player_id: int,
    name: str,
    team: str,
    position: str,
    *,
    season: int = 2021,
    situation: str = "all",
    games: float = 10.0,
    icetime: float = 3600.0,
    goals: float = 2.0,
    expected_goals: float = 1.5,
    primary_assists: float = 2.0,
    secondary_assists: float = 1.0,
    giveaways: float = 3.0,
    takeaways: float = 6.0,
    blocks: float = 4.0,
    hits: float = 8.0,
    on_ice_xgoal_pct: float = 0.60,
    off_ice_xgoal_pct: float = 0.50,
) -> dict:
    return {
        "playerId": player_id,
        "season": season,
        "name": name,
        "team": team,
        "position": position,
        "situation": situation,
        "games_played": games,
        "icetime": icetime,
        "I_F_goals": goals,
        "I_F_xGoals": expected_goals,
        "I_F_primaryAssists": primary_assists,
        "I_F_secondaryAssists": secondary_assists,
        "I_F_giveaways": giveaways,
        "I_F_takeaways": takeaways,
        "shotsBlockedByPlayer": blocks,
        "I_F_hits": hits,
        "onIce_xGoalsPercentage": on_ice_xgoal_pct,
        "offIce_xGoalsPercentage": off_ice_xgoal_pct,
    }


def _goalie_row(
    player_id: int,
    name: str,
    team: str,
    *,
    season: int = 2021,
    situation: str = "all",
    games: float = 5.0,
    icetime: float = 3600.0,
    expected_goals: float = 4.0,
    goals: float = 3.0,
    shots_on_goal: float = 40.0,
    high_danger_shots: float = 10.0,
    high_danger_goals: float = 2.0,
    rebounds: float = 8.0,
) -> dict:
    return {
        "playerId": player_id,
        "season": season,
        "name": name,
        "team": team,
        "position": "G",
        "situation": situation,
        "games_played": games,
        "icetime": icetime,
        "xGoals": expected_goals,
        "goals": goals,
        "ongoal": shots_on_goal,
        "highDangerShots": high_danger_shots,
        "highDangerGoals": high_danger_goals,
        "rebounds": rebounds,
    }


def _write_skater_source(root: Path, rows: list[dict]) -> None:
    raw = root / "data" / "raw" / "nhl"
    raw.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(raw / "moneypuck_skaters_2021_regular.csv", index=False)


def _write_season_profiles(root: Path, player_ids: list[str]) -> None:
    processed = root / "data" / "processed" / "nhl"
    processed.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "player_id": player_ids,
            "season": [2021] * len(player_ids),
            "height_cm": [190.0 + index for index in range(len(player_ids))],
            "weight_kg": [90.0 + index for index in range(len(player_ids))],
            "age": [25 + index for index in range(len(player_ids))],
            "birth_date": pd.to_datetime([f"199{index}-01-01" for index in range(len(player_ids))]),
            "nationality": ["CAN"] * len(player_ids),
            "shoots_catches": ["L"] * len(player_ids),
            "physical_source": ["Undated test profile"] * len(player_ids),
            "physical_measurement_scope": [
                "current/undated profile; not a season measurement"
            ]
            * len(player_ids),
        }
    ).to_parquet(processed / "player_seasons.parquet", index=False)


def test_skater_builder_uses_all_situation_and_handles_team_stints(tmp_path: Path) -> None:
    rows = [
        _skater_row(1, "Centre", "AAA", "C", icetime=3600, on_ice_xgoal_pct=0.60),
        _skater_row(
            1,
            "Centre",
            "BBB",
            "C",
            games=4,
            icetime=1800,
            goals=1,
            expected_goals=0.75,
            primary_assists=1,
            secondary_assists=0.5,
            giveaways=1.5,
            takeaways=3,
            blocks=2,
            hits=4,
            on_ice_xgoal_pct=0.30,
            off_ice_xgoal_pct=0.45,
        ),
        # A distinct situation is already contained in "all" and must be ignored.
        _skater_row(1, "Centre", "AAA", "C", situation="5on5", goals=100),
        _skater_row(2, "Left Wing", "AAA", "L", icetime=1200, goals=1),
        _skater_row(2, "Left Wing", "BBB", "L", icetime=600, goals=1),
        _skater_row(2, "Left Wing", "TOT", "L", icetime=1800, goals=2),
        _skater_row(3, "Right Wing", "CCC", "R"),
        _skater_row(4, "Defender", "DDD", "D"),
    ]
    _write_skater_source(tmp_path, rows)
    _write_season_profiles(tmp_path, ["1", "2", "3", "4"])

    with pytest.warns(RuntimeWarning, match="goalie summaries are not cached"):
        panel = build_nhl_all_roles_panel(tmp_path, seasons=[2021])

    assert list(panel.columns) == list(OUTPUT_COLUMNS)
    assert not panel.duplicated(["player_id", "season"]).any()
    assert set(panel.role) == {"center", "left_wing", "right_wing", "defense"}
    assert panel.attrs["goalie_coverage"] == {
        "requested_seasons": [2021],
        "available_seasons": [],
        "missing_seasons": [2021],
        "status": "partial_or_absent",
    }

    by_id = panel.set_index("player_id")
    centre = by_id.loc["1"]
    assert centre.team == "AAA;BBB"
    assert centre.games == 14
    assert centre.opportunity == pytest.approx(90.0)
    assert centre.goals == pytest.approx(3.0)
    assert centre.goals_per_60 == pytest.approx(2.0)
    assert centre.expected_goals_per_60 == pytest.approx(1.5)
    assert centre.takeaway_giveaway_ratio == pytest.approx(2.0)
    assert centre.on_ice_xgoal_pct == pytest.approx(0.50)
    assert centre.relative_xgoal_pct == pytest.approx(0.50 - (0.50 * 2 / 3 + 0.45 / 3))
    assert centre.height_cm == pytest.approx(190.0)
    assert not bool(centre.physical_is_confirmed_season_measurement)
    assert "not a season measurement" in centre.physical_measurement_scope

    # The explicit provider total is used once, while actual stint teams remain visible.
    left_wing = by_id.loc["2"]
    assert left_wing.team == "AAA;BBB"
    assert left_wing.opportunity == pytest.approx(30.0)
    assert left_wing.goals == pytest.approx(2.0)


def test_skater_builder_engineers_shot_faceoff_penalty_and_corsi_features(
    tmp_path: Path,
) -> None:
    row = _skater_row(1, "Centre", "AAA", "C")
    row.update(
        {
            "I_F_shotsOnGoal": 12.0,
            "I_F_shotAttempts": 20.0,
            "I_F_highDangerShots": 5.0,
            "faceoffsWon": 30.0,
            "faceoffsLost": 20.0,
            "penalties": 2.0,
            "penaltiesDrawn": 5.0,
            "onIce_corsiPercentage": 0.58,
            "offIce_corsiPercentage": 0.50,
        }
    )
    _write_skater_source(tmp_path, [row])
    _write_season_profiles(tmp_path, ["1"])

    with pytest.warns(RuntimeWarning, match="goalie summaries are not cached"):
        player = build_nhl_all_roles_panel(tmp_path, seasons=[2021]).iloc[0]

    assert player.shots_on_goal_per_60 == pytest.approx(12.0)
    assert player.high_danger_shots_per_60 == pytest.approx(5.0)
    assert player.faceoff_win_pct == pytest.approx(0.6)
    assert player.penalty_differential_per_60 == pytest.approx(3.0)
    assert player.relative_corsi_pct == pytest.approx(0.08)


def test_goalie_builder_derives_available_moneypuck_measures(tmp_path: Path) -> None:
    _write_skater_source(tmp_path, [_skater_row(1, "Skater", "AAA", "C")])
    _write_season_profiles(tmp_path, ["1"])
    raw = tmp_path / "data" / "raw" / "nhl"
    pd.DataFrame(
        [
            _goalie_row(9, "Goalie", "AAA"),
            _goalie_row(
                9,
                "Goalie",
                "BBB",
                games=3,
                icetime=1800,
                expected_goals=2,
                goals=1,
                shots_on_goal=20,
                high_danger_shots=5,
                high_danger_goals=1,
                rebounds=4,
            ),
            _goalie_row(9, "Goalie", "AAA", situation="5on5", goals=50),
        ]
    ).to_csv(raw / "moneypuck_goalies_2021_regular.csv", index=False)

    processed = tmp_path / "data" / "processed" / "nhl"
    pd.DataFrame(
        {
            "player_id": ["9"],
            "name_latest_profile": ["Goalie"],
            "birth_date_latest_profile": pd.to_datetime(["1990-10-02"]),
            "position_latest_profile": ["G"],
            "nationality": ["USA"],
            "shoots_catches": ["L"],
            "height_cm_latest_profile": [193.04],
            "weight_kg_latest_profile": [95.0],
            "profile_temporality": ["current/undated lookup; not season history"],
        }
    ).to_parquet(processed / "latest_player_bios.parquet", index=False)

    panel = build_nhl_all_roles_panel(tmp_path, seasons=[2021])
    goalie = panel.loc[panel.role == "goalie"].iloc[0]
    assert goalie.team == "AAA;BBB"
    assert goalie.games == 8
    assert goalie.opportunity == pytest.approx(90.0)
    assert goalie.save_pct == pytest.approx(1.0 - 4.0 / 60.0)
    assert goalie.high_danger_save_pct == pytest.approx(1.0 - 3.0 / 15.0)
    assert goalie.goals_saved_above_expected == pytest.approx(2.0)
    assert goalie.goals_saved_above_expected_per_60 == pytest.approx(4.0 / 3.0)
    assert goalie.rebound_rate == pytest.approx(12.0 / 56.0)
    assert goalie.rebound_goals_against_rate == pytest.approx(12.0 / 56.0)
    assert goalie.height_cm == pytest.approx(193.04)
    assert goalie.age == 30
    assert not bool(goalie.physical_is_confirmed_season_measurement)
    assert panel.attrs["goalie_coverage"]["status"] == "complete"


def test_fetch_goalie_sources_uses_designated_urls_without_builder_network_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, Path, dict]] = []

    def fake_fetch(url: str, dest: Path, **kwargs: object) -> Path:
        calls.append((url, Path(dest), kwargs))
        return Path(dest)

    monkeypatch.setattr(nhl, "fetch", fake_fetch)
    result = nhl.fetch_nhl_goalie_sources(tmp_path, seasons=[2022, 2021, 2022])

    assert list(result) == [2021, 2022]
    assert [call[0] for call in calls] == [
        "https://www.moneypuck.com/moneypuck/playerData/seasonSummary/2021/regular/goalies.csv",
        "https://www.moneypuck.com/moneypuck/playerData/seasonSummary/2022/regular/goalies.csv",
    ]
    assert calls[0][1] == (
        tmp_path / "data" / "raw" / "nhl" / "moneypuck_goalies_2021_regular.csv"
    )
    assert calls[0][2]["license_note"] == nhl.MONEYPUCK_LICENSE
