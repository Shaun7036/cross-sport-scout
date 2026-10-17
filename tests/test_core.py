from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from possession_lab.analysis import build_forecast_pairs, regression_scores, validate_panel
from possession_lab.io import fetch, sha256, write_json
from possession_lab.sports.nfl import (
    map_role,
    parse_height,
    participation_credit_gaps,
    participation_opportunities,
    scrimmage_events,
)


def panel():
    return pd.DataFrame(
        [
            {
                "player_id": "a",
                "name": "A",
                "season": 2021,
                "role": "CB",
                "opportunity": 100,
                "steals": 2,
                "height_cm": 190,
                "weight_kg": 90,
                "age": 24,
            },
            {
                "player_id": "b",
                "name": "B",
                "season": 2021,
                "role": "CB",
                "opportunity": 100,
                "steals": 1,
                "height_cm": 190,
                "weight_kg": 90,
                "age": 25,
            },
            {
                "player_id": "a",
                "name": "A",
                "season": 2022,
                "role": "S",
                "opportunity": 150,
                "steals": 3,
                "height_cm": 191,
                "weight_kg": 94,
                "age": 25,
            },
            {
                "player_id": "c",
                "name": "C",
                "season": 2022,
                "role": "CB",
                "opportunity": 100,
                "steals": np.nan,
                "height_cm": np.nan,
                "weight_kg": np.nan,
                "age": 20,
            },
        ]
    )


def test_temporal_pairs_preserve_nonreturners_and_prior_role():
    pairs = build_forecast_pairs(panel(), {"steals": "steals"}).set_index("player_id")
    assert pairs.loc["b", "target_opportunity"] == 0
    assert pairs.loc["b", "target_steals"] == 0
    assert pairs.loc["a", "prior_role"] == "CB"
    assert pairs.loc["a", "lag_steals_rate"] == 2
    assert pairs.loc["a", "target_opportunity"] == 150
    assert set(pairs.index) == {"a", "b"}  # later entrant c was not known in 2021


def test_present_but_unobserved_target_stays_missing():
    source = panel()
    source.loc[2, "steals"] = np.nan
    pairs = build_forecast_pairs(source, {"steals": "steals"}).set_index("player_id")
    assert np.isnan(pairs.loc["a", "target_steals"])


def test_reject_duplicate_or_negative_panel():
    with pytest.raises(ValueError, match="Duplicate"):
        validate_panel(pd.concat([panel(), panel().iloc[[0]]]), {"steals": "steals"})
    source = panel()
    source.loc[0, "opportunity"] = -1
    with pytest.raises(ValueError, match="Negative opportunity"):
        validate_panel(source, {"steals": "steals"})


def test_missing_count_never_converted_to_zero():
    validated = validate_panel(panel(), {"steals": "steals", "blocks": "blocks"})
    assert validated.blocks.isna().all()
    assert validated.loc[validated.player_id.eq("c"), "steals"].isna().all()


def test_cached_file_integrity(tmp_path: Path):
    path = tmp_path / "fixture.csv"
    path.write_text("x\n1\n")
    write_json(
        path.with_name("fixture.csv.source.json"),
        {"url": "https://example.com/data.csv", "sha256": sha256(path)},
    )
    assert fetch("https://example.com/data.csv", path, source="fixture", license_note="test") == path
    path.write_text("x\n2\n")
    with pytest.raises(ValueError, match="integrity"):
        fetch("https://example.com/data.csv", path, source="fixture", license_note="test")


def test_tracked_snapshot_change_requires_explicit_new_version(tmp_path: Path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    path = tmp_path / "data" / "raw" / "fixture.csv"
    path.parent.mkdir(parents=True)
    path.write_text("x\n1\n")
    url = "https://example.com/data.csv"
    write_json(path.with_name("fixture.csv.source.json"), {"url": url, "sha256": sha256(path)})
    write_json(
        tmp_path / "metadata" / "download_manifest.json",
        {"files": [{"path": "data/raw/fixture.csv", "url": url, "sha256": "old_snapshot_hash"}]},
    )
    with pytest.raises(ValueError, match="tracked manifest"):
        fetch(url, path, source="fixture", license_note="test")
    monkeypatch.setenv("POSSESSION_LAB_ACCEPT_SOURCE_UPDATES", "1")
    assert fetch(url, path, source="fixture", license_note="test") == path


def test_nfl_position_ambiguity_is_explicit():
    assert map_role("LB", "OLB") == "OLB_HYBRID"
    assert map_role("DL", "DT") == "IDL"
    assert map_role("DB", "FS") == "S"
    assert map_role("QB", "QB") == "NON_DEFENSE"
    assert parse_height("6-4") == pytest.approx(193.04)
    assert parse_height(76) == pytest.approx(193.04)


def test_participation_is_opportunity_not_individual_pressure():
    pbp = pd.DataFrame(
        [
            {
                "game_id": "g",
                "play_id": 1,
                "season_type": "REG",
                "play_type": "pass",
                "defteam": "T",
                "pass_attempt": 1,
                "rush_attempt": 0,
                "qb_dropback": 1,
                "qb_scramble": 0,
                "no_play": 0,
                "down": 3,
            },
            {
                "game_id": "g",
                "play_id": 2,
                "season_type": "REG",
                "play_type": "no_play",
                "defteam": "T",
                "pass_attempt": 0,
                "rush_attempt": 0,
                "qb_dropback": 0,
                "qb_scramble": 0,
                "no_play": 1,
                "down": 3,
            },
        ]
    )
    participation = pd.DataFrame(
        [
            {
                "nflverse_game_id": "g",
                "play_id": 1,
                "defense_players": "00-0001;00-0002",
                "was_pressure": True,
            },
            {
                "nflverse_game_id": "g",
                "play_id": 2,
                "defense_players": "00-0001;00-0002",
                "was_pressure": False,
            },
        ]
    )
    result, qa = participation_opportunities(pbp, participation)
    assert result.opportunity.tolist() == [1, 1]
    assert result.on_field_dropbacks.tolist() == [1, 1]
    assert "pressures" not in result
    assert qa["player_plays"] == 2


def test_constant_prediction_has_no_fake_rank_correlation():
    score = regression_scores([1, 2, 3], [2, 2, 2])
    assert score["spearman"] is None
    assert score["mae"] == pytest.approx(2 / 3)


def test_scrimmage_credits_half_sacks_and_excludes_own_recovery():
    base = {
        "game_id": "g",
        "season_type": "REG",
        "defteam": "D",
        "posteam": "O",
        "down": 3,
        "ydstogo": 5,
        "yards_gained": -4,
        "epa": -1,
        "sack_player_id": None,
        "half_sack_1_player_id": None,
        "half_sack_2_player_id": None,
        "fumble_recovery_1_player_id": None,
        "fumble_recovery_1_team": None,
        "fumbled_1_team": None,
    }
    fixture = pd.DataFrame(
        [
            {
                **base,
                "play_id": 1,
                "play_type": "pass",
                "half_sack_1_player_id": "00-1",
                "half_sack_2_player_id": "00-2",
                "qb_hit_1_player_id": "00-1",
            },
            {**base, "play_id": 2, "play_type": "punt", "sack_player_id": "00-3"},
            {
                **base,
                "play_id": 3,
                "play_type": "run",
                "fumble_recovery_1_player_id": "00-4",
                "fumble_recovery_1_team": "D",
                "fumbled_1_team": "D",
            },
            {
                **base,
                "play_id": 4,
                "play_type": "run",
                "fumble_recovery_1_player_id": "00-5",
                "fumble_recovery_1_team": "D",
                "fumbled_1_team": "O",
            },
        ]
    )
    counts, credits = scrimmage_events(fixture)
    assert counts.set_index("player_id").loc["00-1", "sacks"] == 0.5
    assert counts.set_index("player_id").loc["00-2", "sacks"] == 0.5
    assert counts.set_index("player_id").loc["00-1", "pass_disruption_plays"] == 1
    assert "00-3" not in counts.player_id.values
    assert "00-4" not in counts.player_id.values
    assert credits[credits.metric.eq("opponent_fumble_recoveries")].player_id.tolist() == ["00-5"]


def test_aborted_double_fumble_uses_previous_recovery_possession():
    fixture = pd.DataFrame(
        [
            {
                "game_id": "g",
                "play_id": 1,
                "season_type": "REG",
                "play_type": "run",
                "defteam": "D",
                "posteam": "O",
                "down": 1,
                "ydstogo": 10,
                "yards_gained": -8,
                "epa": -3,
                "fumble_recovery_1_player_id": "00-1",
                "fumble_recovery_1_team": "O",
                "fumble_recovery_2_player_id": "00-2",
                "fumble_recovery_2_team": "D",
                "fumbled_1_team": "O",
                "fumbled_2_team": None,
            }
        ]
    )
    _, credits = scrimmage_events(fixture)
    assert credits[credits.metric.eq("opponent_fumble_recoveries")].player_id.tolist() == ["00-2"]


def test_safety_credits_are_observed_without_fake_missingness():
    fixture = pd.DataFrame(
        [
            {
                "game_id": "g",
                "play_id": 1,
                "season_type": "REG",
                "play_type": "run",
                "defteam": "D",
                "posteam": "O",
                "down": 1,
                "ydstogo": 10,
                "yards_gained": -2,
                "epa": -4,
                "safety_player_id": "00-1",
            }
        ]
    )
    counts, _ = scrimmage_events(fixture)
    assert counts.set_index("player_id").loc["00-1", "safeties"] == 1
    assert "safeties" in counts.attrs["observed_metrics"]


def test_missing_participation_credit_is_flagged_not_assumed_complete():
    credits = pd.DataFrame(
        [
            {"game_id": "g", "play_id": 1, "player_id": "00-1", "metric": "sacks"},
            {"game_id": "g", "play_id": 1, "player_id": "00-2", "metric": "qb_hits"},
        ]
    )
    participants = pd.DataFrame([{"nflverse_game_id": "g", "play_id": 1, "defense_players": "00-1"}])
    gaps = participation_credit_gaps(credits, participants)
    assert gaps.player_id.tolist() == ["00-2"]
