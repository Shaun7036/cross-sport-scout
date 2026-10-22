from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from possession_lab.all_roles_nfl import (
    CANONICAL_ROLES,
    DEFENSIVE_TOTAL_COLUMNS,
    WEEKLY_TOTAL_COLUMNS,
    _aggregate_charged_offensive_penalties,
    _aggregate_weekly_stats,
    _assign_performance_source_status,
    _assign_role_exposure,
    _derive_rates,
    _seasonal_role_assignments,
    build_nfl_all_roles_panel,
    map_nfl_role,
)


@pytest.mark.parametrize(
    ("position", "depth", "expected"),
    [
        ("QB", "QB", "QB"),
        ("RB", "FB", "RB_FB"),
        ("OL", "T", "OT"),
        ("OL", "G", "IOL"),
        ("DL", "DE", "EDGE"),
        ("LB", "OLB", "EDGE"),
        ("DL", "NT", "IDL"),
        ("LB", "ILB", "LB"),
        ("DB", "CB", "CB"),
        ("DB", "FS", "S"),
        ("K", None, "K"),
        ("P", None, "P"),
        ("LS", None, "LS"),
    ],
)
def test_map_nfl_role_uses_specific_depth_chart_first(
    position: str,
    depth: str | None,
    expected: str,
) -> None:
    role = map_nfl_role(position, depth)
    assert role == expected
    assert role in CANONICAL_ROLES


@pytest.mark.parametrize("ambiguous", ["DB", "DL", "OL", "ATH", None])
def test_map_nfl_role_does_not_guess_ambiguous_positions(ambiguous: str | None) -> None:
    assert map_nfl_role(ambiguous, ambiguous) is None


def test_derive_rates_uses_role_aligned_denominators() -> None:
    frame = pd.DataFrame(
        [
            {
                "role": "QB",
                "attempts": 100.0,
                "sacks_suffered": 20.0,
                "passing_epa": 24.0,
                "passing_yards": 800.0,
                "passing_cpoe": 5.0,
                "passing_first_downs": 40.0,
                "passing_air_yards": 1_000.0,
                "passing_20": 15.0,
                "passing_tds": 10.0,
                "passing_interceptions": 4.0,
                "sack_fumbles_lost": 2.0,
            },
            {
                "role": "RB_FB",
                "carries": 80.0,
                "receptions": 20.0,
                "targets": 25.0,
                "rushing_epa": 8.0,
                "rushing_yards": 400.0,
                "rushing_first_downs": 20.0,
                "rushing_10": 12.0,
                "receiving_epa": 5.0,
                "receiving_yards": 150.0,
                "receiving_20": 3.0,
                "rushing_tds": 6.0,
                "receiving_tds": 2.0,
                "rushing_fumbles_lost": 1.0,
                "receiving_fumbles_lost": 1.0,
            },
            {
                "role": "WR",
                "receptions": 6.0,
                "targets": 10.0,
                "receiving_epa": 3.0,
                "receiving_yards": 100.0,
                "receiving_first_downs": 5.0,
                "receiving_20": 2.0,
                "receiving_yards_after_catch": 42.0,
                "receiving_tds": 2.0,
                "receiving_fumbles_lost": 1.0,
            },
            {
                "role": "EDGE",
                "defensive_opportunity": 200.0,
                "sacks": 10.0,
                "qb_hits": 20.0,
                "negative_play_tackle_credits": 15.0,
                "forced_fumbles": 3.0,
                "solo_tackles": 40.0,
                "tackle_assists": 10.0,
                "interceptions": 2.0,
                "passes_defended": 8.0,
            },
            {
                "role": "OT",
                "offense_snaps": 500.0,
                "charged_offensive_penalties": 5.0,
            },
            {
                "role": "K",
                "fg_made": 20.0,
                "fg_att": 25.0,
                "fg_made_50_59": 4.0,
                "fg_made_60_": 1.0,
                "pat_made": 30.0,
                "pat_att": 31.0,
            },
            {
                "role": "P",
                "pt_att": 50.0,
                "pt_net_yards": 2_100.0,
                "pt_inside_20": 20.0,
                "pt_touchback": 5.0,
                "pt_blocked": 1.0,
            },
        ]
    )

    result = _assign_role_exposure(_derive_rates(frame)).set_index("role")
    qb = result.loc["QB"]
    assert qb.dropbacks == 120.0
    assert qb.opportunity == 120.0
    assert qb.passing_epa_per_play == pytest.approx(0.2)
    assert qb.passing_yards_per_attempt == pytest.approx(8.0)
    assert qb.passing_first_down_rate == pytest.approx(0.4)
    assert qb.passing_air_yards_per_attempt == pytest.approx(10.0)
    assert qb.explosive_pass_rate == pytest.approx(0.15)
    assert qb.touchdown_rate == pytest.approx(0.1)
    assert qb.turnover_rate == pytest.approx(6.0 / 120.0)
    assert qb.sack_rate == pytest.approx(20.0 / 120.0)

    rb = result.loc["RB_FB"]
    assert rb.touches == 100.0
    assert rb.opportunity == 100.0
    assert rb.rushing_epa_per_carry == pytest.approx(0.1)
    assert rb.explosive_run_rate == pytest.approx(0.15)
    assert rb.explosive_target_rate == pytest.approx(0.12)
    assert rb.receiving_epa_per_target == pytest.approx(0.2)
    assert rb.touchdown_rate == pytest.approx(0.08)
    assert rb.turnover_rate == pytest.approx(0.02)

    receiver = result.loc["WR"]
    assert receiver.opportunity == 10.0
    assert receiver.receiving_yards_per_target == pytest.approx(10.0)
    assert receiver.explosive_target_rate == pytest.approx(0.2)
    assert receiver.catch_rate == pytest.approx(0.6)
    assert receiver.yards_after_catch_per_reception == pytest.approx(7.0)
    assert receiver.turnover_rate == pytest.approx(0.1)

    edge = result.loc["EDGE"]
    assert edge.opportunity == 200.0
    assert edge.sack_rate == pytest.approx(0.05)
    assert edge.qb_hit_rate == pytest.approx(0.1)
    assert edge.tackle_rate == pytest.approx(0.25)

    assert pd.isna(result.loc["OT", "penalties_per_100_snaps"])
    assert pd.isna(result.loc["OT", "opportunity"])
    assert result.loc["K", "field_goal_pct"] == pytest.approx(0.8)
    assert result.loc["K", "long_field_goal_rate"] == pytest.approx(0.2)
    assert result.loc["K", "opportunity"] == 25.0
    assert result.loc["P", "net_yards_per_punt"] == pytest.approx(42.0)
    assert result.loc["P", "inside_20_rate"] == pytest.approx(0.4)
    assert result.loc["P", "opportunity"] == 50.0


def test_derive_rates_leaves_zero_and_missing_denominators_unscored() -> None:
    frame = pd.DataFrame(
        [
            {
                "role": "QB",
                "attempts": 0.0,
                "sacks_suffered": 0.0,
                "passing_epa": 0.0,
                "passing_yards": 0.0,
                "passing_tds": 0.0,
                "passing_interceptions": 0.0,
                "sack_fumbles_lost": 0.0,
            },
            {
                "role": "OT",
                "offense_snaps": np.nan,
                "charged_offensive_penalties": 0.0,
            },
        ]
    )
    result = _assign_role_exposure(_derive_rates(frame)).set_index("role")
    assert result.loc["QB", "dropbacks"] == 0.0
    assert pd.isna(result.loc["QB", "passing_epa_per_play"])
    assert pd.isna(result.loc["QB", "sack_rate"])
    assert pd.isna(result.loc["OT", "penalties_per_100_snaps"])
    assert pd.isna(result.loc["OT", "opportunity"])


def test_seasonal_roles_use_all_specific_observations_and_explicit_ties() -> None:
    roster = pd.DataFrame(
        [
            # Generic DB observations do not vote; the later specific mode wins.
            *[
                {
                    "gsis_id": "mode",
                    "season": 2024,
                    "game_type": "REG",
                    "week": week,
                    "depth_chart_position": depth,
                }
                for week, depth in [(1, "DB"), (2, "DB"), (3, "CB"), (4, "CB"), (5, "FS")]
            ],
            # FS and SS combine at the canonical safety-role level.  A 2-2
            # role tie is then resolved by the role seen most recently (CB).
            *[
                {
                    "gsis_id": "tie",
                    "season": 2024,
                    "game_type": "REG",
                    "week": week,
                    "depth_chart_position": depth,
                }
                for week, depth in [(1, "FS"), (2, "SS"), (3, "CB"), (4, "CB")]
            ],
            {
                "gsis_id": "generic",
                "season": 2024,
                "game_type": "REG",
                "week": 1,
                "depth_chart_position": "DB",
            },
            # Preseason specificity must not resolve a generic REG history.
            {
                "gsis_id": "generic",
                "season": 2024,
                "game_type": "PRE",
                "week": 3,
                "depth_chart_position": "CB",
            },
            # If count and latest week are identical, lexical role order is
            # the final deterministic (and deliberately non-semantic) tie-break.
            {
                "gsis_id": "lexical",
                "season": 2024,
                "game_type": "REG",
                "week": 1,
                "depth_chart_position": "S",
            },
            {
                "gsis_id": "lexical",
                "season": 2024,
                "game_type": "REG",
                "week": 1,
                "depth_chart_position": "CB",
            },
        ]
    )

    result = _seasonal_role_assignments(roster).set_index("player_id")
    assert result.loc["mode", "seasonal_role"] == "CB"
    assert result.loc["mode", "seasonal_depth_chart_position"] == "CB"
    assert result.loc["mode", "role_roster_observations"] == 5
    assert result.loc["mode", "role_specific_observations"] == 3
    assert not result.loc["mode", "role_assignment_tied"]

    assert result.loc["tie", "seasonal_role"] == "CB"
    assert result.loc["tie", "role_specific_observations"] == 4
    assert result.loc["tie", "role_assignment_tied"]

    assert pd.isna(result.loc["generic", "seasonal_role"])
    assert pd.isna(result.loc["generic", "seasonal_depth_chart_position"])
    assert result.loc["generic", "role_specific_observations"] == 0

    assert result.loc["lexical", "seasonal_role"] == "CB"
    assert result.loc["lexical", "role_assignment_tied"]


def test_performance_source_status_abstains_for_identity_only_roles() -> None:
    frame = pd.DataFrame({"role": ["OT", "IOL", "LS", "WR", "CB", pd.NA]})
    result = _assign_performance_source_status(frame)

    assert set(result.loc[result["role"].isin(["OT", "IOL", "LS"]), "performance_source"]) == {
        "none_release_safe"
    }
    assert set(
        result.loc[
            result["role"].isin(["OT", "IOL", "LS"]), "performance_label_status"
        ]
    ) == {"abstain_no_release_safe_individual_label"}
    assert result.loc[3, "performance_source"] == "nflverse_weekly_player_stats"
    assert result.loc[4, "performance_source"] == "nflverse_pbp_participation"
    assert result.loc[5, "performance_label_status"] == "abstain_unregistered_role"


def test_builder_does_not_require_conditional_snap_file(tmp_path) -> None:
    season = 2024
    raw_dir = tmp_path / "data" / "raw" / "nfl" / str(season)
    processed_dir = tmp_path / "data" / "processed" / "nfl"
    raw_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)

    profile = {
        "player_id": "00-0000002",
        "season": season,
        "name": "Test Tackle",
        "position": "OL",
        "depth_chart_position": "OL",
        "height_cm": 198.0,
        "weight_kg": 140.0,
        "age": 27.0,
        "opportunity": 0.0,
        "games_with_participation": 0.0,
        "teams": "TST",
        "rostered_weeks": 1,
        "opportunity_observed": True,
        "opportunity_complete": True,
        "participation_provider": "FTN",
        **{column: 0.0 for column in DEFENSIVE_TOTAL_COLUMNS},
    }
    pd.DataFrame([profile]).to_parquet(
        processed_dir / "all_rostered_player_seasons.parquet", index=False
    )
    pd.DataFrame(
        [
            {
                "gsis_id": "00-0000002",
                "season": season,
                "game_type": "REG",
                "week": 1,
                "depth_chart_position": "T",
            }
        ]
    ).to_parquet(raw_dir / f"roster_weekly_{season}.parquet", index=False)
    pd.DataFrame(columns=sorted({
        "player_id",
        "player_display_name",
        "position",
        "season",
        "season_type",
        "game_id",
        "team",
        "passing_cpoe",
        *WEEKLY_TOTAL_COLUMNS,
    })).to_parquet(raw_dir / f"stats_player_week_{season}.parquet", index=False)

    result = build_nfl_all_roles_panel(tmp_path, seasons=[season])
    assert len(result) == 1
    row = result.iloc[0]
    assert row["role"] == "OT"
    assert row["depth_chart_position"] == "T"
    assert row["role_assignment_source"] == "weekly_roster_seasonal_modal_specific_depth"
    assert row["role_roster_observations"] == 1
    assert pd.isna(row["opportunity"])
    assert pd.isna(row["games"])
    assert pd.isna(row["offense_snaps"])
    assert not row["snaps_observed"]
    assert row["snap_fields_status"] == "not_loaded_conditional_pfr_source"
    assert row["performance_source"] == "none_release_safe"
    assert row["performance_label_status"] == "abstain_no_release_safe_individual_label"


def _weekly_row(game_id: str, attempts: float, cpoe: float | None) -> dict:
    row = {column: 0.0 for column in WEEKLY_TOTAL_COLUMNS}
    row.update(
        {
            "player_id": "00-0000001",
            "player_display_name": "Test Quarterback",
            "position": "QB",
            "season": 2024,
            "season_type": "REG",
            "game_id": game_id,
            "team": "TST",
            "attempts": attempts,
            "passing_cpoe": cpoe,
            "passing_epa": np.nan if attempts == 0 else attempts / 10.0,
            "rushing_epa": np.nan,
            "receiving_epa": np.nan,
        }
    )
    return row


def test_weekly_aggregation_weights_cpoe_and_preserves_real_missingness() -> None:
    rows = [
        _weekly_row("g1", 10.0, 2.0),
        _weekly_row("g2", 20.0, 8.0),
        _weekly_row("g3", 0.0, None),
    ]
    rows[0]["passing_yards"] = 100.0
    rows[1]["passing_yards"] = np.nan
    result = _aggregate_weekly_stats(pd.DataFrame(rows)).iloc[0]
    assert result.weekly_stats_games == 3
    assert result.attempts == 30.0
    assert result.passing_epa == pytest.approx(3.0)
    assert result.passing_cpoe == pytest.approx((10.0 * 2.0 + 20.0 * 8.0) / 30.0)
    assert pd.isna(result.passing_yards)


def test_penalty_proxy_filters_side_and_phase_and_deduplicates() -> None:
    pbp = pd.DataFrame(
        [
            {
                "season": 2024,
                "season_type": "REG",
                "game_id": "g1",
                "play_id": 1,
                "posteam": "AAA",
                "penalty": 1,
                "penalty_team": "AAA",
                "penalty_player_id": "00-0000002",
                "special_teams_play": 0,
            },
            {
                "season": 2024,
                "season_type": "REG",
                "game_id": "g1",
                "play_id": 1,
                "posteam": "AAA",
                "penalty": 1,
                "penalty_team": "AAA",
                "penalty_player_id": "00-0000002",
                "special_teams_play": 0,
            },
            {
                "season": 2024,
                "season_type": "REG",
                "game_id": "g1",
                "play_id": 2,
                "posteam": "AAA",
                "penalty": 1,
                "penalty_team": "BBB",
                "penalty_player_id": "00-0000002",
                "special_teams_play": 0,
            },
            {
                "season": 2024,
                "season_type": "REG",
                "game_id": "g1",
                "play_id": 3,
                "posteam": "AAA",
                "penalty": 1,
                "penalty_team": "AAA",
                "penalty_player_id": "00-0000002",
                "special_teams_play": 1,
            },
        ]
    )
    result = _aggregate_charged_offensive_penalties(pbp)
    assert result.attrs["source_usable"] is True
    assert result.loc[0, "charged_offensive_penalties"] == 1

    unavailable = _aggregate_charged_offensive_penalties(pbp.drop(columns="posteam"))
    assert unavailable.empty
    assert unavailable.attrs["source_usable"] is False
