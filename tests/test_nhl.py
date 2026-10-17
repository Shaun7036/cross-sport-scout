from __future__ import annotations

import json
import zipfile

import numpy as np
import pandas as pd

from possession_lab.sports import nhl


def _row(
    *,
    situation: str,
    team: str,
    icetime: float,
    takeaways: float,
    blocks: float,
    hits: float,
    giveaways: float,
    faceoff_wins: float,
) -> dict:
    return {
        "playerId": 8470001,
        "season": 2021,
        "name": "Test Skater",
        "team": team,
        "position": "D",
        "situation": situation,
        "games_played": 10,
        "icetime": icetime,
        "I_F_takeaways": takeaways,
        "shotsBlockedByPlayer": blocks,
        "I_F_hits": hits,
        "I_F_giveaways": giveaways,
        "faceoffsWon": faceoff_wins,
    }


def test_height_parser_and_role_mapping() -> None:
    assert np.isclose(nhl._parse_height_cm("6' 3\""), 190.5)
    assert np.isclose(nhl._parse_height_cm("6-3"), 190.5)
    assert np.isnan(nhl._parse_height_cm("unknown"))
    assert nhl._role("D") == "defense"
    assert nhl._role("C") == "center"
    assert nhl._role("LW") == "wing"


def test_team_stints_combine_without_adding_overlapping_situations() -> None:
    source = pd.DataFrame(
        [
            _row(
                situation="all",
                team="AAA",
                icetime=600,
                takeaways=3,
                blocks=4,
                hits=5,
                giveaways=2,
                faceoff_wins=0,
            ),
            _row(
                situation="all",
                team="BBB",
                icetime=300,
                takeaways=2,
                blocks=1,
                hits=2,
                giveaways=1,
                faceoff_wins=0,
            ),
            _row(
                situation="5on5",
                team="AAA",
                icetime=420,
                takeaways=2,
                blocks=3,
                hits=4,
                giveaways=1,
                faceoff_wins=0,
            ),
            _row(
                situation="5on5",
                team="BBB",
                icetime=180,
                takeaways=1,
                blocks=1,
                hits=1,
                giveaways=1,
                faceoff_wins=0,
            ),
        ]
    )
    panel = nhl._build_season_panel(source)
    assert len(panel) == 1
    row = panel.iloc[0]
    assert row["player_id"] == "8470001"
    assert row["teams"] == "AAA|BBB"
    assert row["role"] == "defense"
    assert row["opportunity"] == 15
    assert row["opportunity_5v5"] == 10
    assert row["takeaways"] == 5
    assert row["takeaways_5v5"] == 3
    # A common error would produce eight by summing all and 5-on-5.
    assert row["takeaways"] != row["takeaways"] + row["takeaways_5v5"]


def test_explicit_total_row_is_not_double_counted() -> None:
    source = pd.DataFrame(
        [
            _row(
                situation="all",
                team="AAA",
                icetime=600,
                takeaways=3,
                blocks=4,
                hits=5,
                giveaways=2,
                faceoff_wins=0,
            ),
            _row(
                situation="all",
                team="TOT",
                icetime=900,
                takeaways=5,
                blocks=5,
                hits=7,
                giveaways=3,
                faceoff_wins=0,
            ),
            _row(
                situation="5on5",
                team="TOT",
                icetime=600,
                takeaways=3,
                blocks=4,
                hits=5,
                giveaways=2,
                faceoff_wins=0,
            ),
        ]
    )
    panel = nhl._build_season_panel(source)
    assert panel.loc[0, "opportunity"] == 15
    assert panel.loc[0, "takeaways"] == 5


def test_latest_lookup_physical_values_are_not_backfilled_into_seasons() -> None:
    panel = nhl._build_season_panel(
        pd.DataFrame(
            [
                _row(
                    situation="all",
                    team="AAA",
                    icetime=600,
                    takeaways=3,
                    blocks=4,
                    hits=5,
                    giveaways=2,
                    faceoff_wins=0,
                ),
                _row(
                    situation="5on5",
                    team="AAA",
                    icetime=400,
                    takeaways=2,
                    blocks=3,
                    hits=4,
                    giveaways=1,
                    faceoff_wins=0,
                ),
            ]
        )
    )
    official = pd.DataFrame(columns=["player_id", "season", "birth_date_official", "height_cm", "weight_kg"])
    latest = pd.DataFrame(
        {
            "player_id": ["8470001"],
            "birth_date_latest_profile": [pd.Timestamp("1995-11-02")],
            "nationality": ["CAN"],
            "shoots_catches": ["L"],
            "height_cm_latest_profile": [200.0],
            "weight_kg_latest_profile": [100.0],
        }
    )
    result = nhl._attach_bios(panel, official, latest)
    assert pd.isna(result.loc[0, "height_cm"])
    assert pd.isna(result.loc[0, "weight_kg"])
    assert result.loc[0, "age"] == 25
    assert not bool(result.loc[0, "physical_is_confirmed_season_measurement"])


def test_official_bios_are_converted_and_temporality_is_disclosed(tmp_path) -> None:
    path = tmp_path / "bios.json"
    path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "playerId": 8470001,
                        "birthDate": "1995-11-02",
                        "height": 75,
                        "weight": 220,
                    }
                ]
            }
        )
    )
    official = nhl._load_official_bios(path, 2021)
    assert np.isclose(official.loc[0, "height_cm"], 190.5)
    assert np.isclose(official.loc[0, "weight_kg"], 99.7903214)


def test_game_zip_reader_keeps_regular_all_and_5v5_only(tmp_path) -> None:
    base = {
        "playerId": 8470001,
        "name": "Test Skater",
        "season": 2021,
        "playerTeam": "AAA",
        "opposingTeam": "BBB",
        "home_or_away": "HOME",
        "gameDate": "2021-10-10",
        "position": "D",
        "icetime": 600,
        "I_F_takeaways": 1,
        "shotsBlockedByPlayer": 2,
        "I_F_hits": 3,
        "I_F_giveaways": 1,
        "faceoffsWon": 0,
    }
    rows = [
        {**base, "gameId": 2021020001, "situation": "all"},
        {**base, "gameId": 2021020001, "situation": "5on5"},
        {**base, "gameId": 2021020001, "situation": "5on4"},
        {**base, "gameId": 2021030001, "situation": "all"},
    ]
    archive_path = tmp_path / "games.zip"
    csv_path = tmp_path / "2021.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(csv_path, arcname="2021.csv")

    source = nhl._read_game_zip(archive_path)
    assert len(source) == 2
    result = nhl._build_game_panel(source)
    assert len(result) == 1
    assert result.loc[0, "game_id"] == "2021020001"
    assert result.loc[0, "takeaways"] == 1
    assert result.loc[0, "takeaways_5v5"] == 1
