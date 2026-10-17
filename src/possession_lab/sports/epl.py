"""Premier League player panels with explicit source-coverage boundaries.

The five-season common core comes from archived Fantasy Premier League tables.
Those tables identify players and their opportunities, but do not contain tackles,
interceptions, recoveries, or blocks before 2025-26.  A separate 2025-26 match
detail source supplies those defensive events.  Missing historic events remain
missing; they are never converted to zero or inferred from fantasy points.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from possession_lab.io import fetch, read_frame, write_json

SPORT = "epl"
VAASTAV_BASE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
CORE_BASE = "https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/main/data/2025-2026"
CORE_PL_BASE = CORE_BASE + "/By%20Tournament/Premier%20League"
ESPN_TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams?limit=100&season=2025"

VAASTAV_LICENSE = (
    "Repository software is MIT licensed, but its LICENSE says the underlying data belongs to "
    "fantasy.premierleague.com/Understat. Research use only; review upstream terms before redistribution."
)
CORE_LICENSE = (
    "Public GitHub data with no repository license found at retrieval; underlying provider rights are "
    "unclear. Research/prototyping only; do not redistribute raw files without permission review."
)
ESPN_LICENSE = (
    "Public ESPN site JSON without an API key; no open-data license asserted. Store as a dated research "
    "profile snapshot and review ESPN/upstream terms before redistribution or commercial use."
)

ROLE_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
ROLE_TEXT_MAP = {
    "goalkeeper": "GK",
    "defender": "DEF",
    "midfielder": "MID",
    "forward": "FWD",
    "g": "GK",
    "d": "DEF",
    "m": "MID",
    "f": "FWD",
}

POSSESSION_COLUMNS = [
    "tackles",
    "tackles_won",
    "interceptions",
    "recoveries",
    "blocks",
    "clearances",
    "headed_clearances",
    "duels_won",
    "duels_lost",
    "ground_duels_won",
    "aerial_duels_won",
    "dribbled_past",
    "fouls_committed",
    "dispossessed",
    "defensive_contributions_raw",
]

COMMON_GAME_SUMS = [
    "goals_scored",
    "assists",
    "clean_sheets",
    "goals_conceded",
    "saves",
    "yellow_cards",
    "red_cards",
]


def _season_slug(year: int) -> str:
    return f"{int(year)}-{str(int(year) + 1)[-2:]}"


def _normalize_name(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.translate(str.maketrans({"ø": "o", "ł": "l", "đ": "d", "ð": "d", "þ": "th"}))
    text = "".join(
        character for character in unicodedata.normalize("NFKD", text) if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _role(value: object) -> str:
    if pd.isna(value):
        return "UNK"
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return ROLE_TEXT_MAP.get(str(value).strip().lower(), str(value).strip().upper())
    return ROLE_MAP.get(numeric, "UNK")


def _stable_player_id(code: object) -> str:
    if pd.isna(code):
        raise ValueError("FPL player code is required for a stable cross-season identity")
    return f"fpl:{int(code)}"


def _numeric(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    for column in columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        else:
            frame[column] = np.nan
    return frame


def _age_on(dob: object, when: pd.Timestamp) -> float:
    if pd.isna(dob) or pd.isna(when):
        return np.nan
    born = pd.Timestamp(dob)
    return float(when.year - born.year - ((when.month, when.day) < (born.month, born.day)))


def _prepare_common_season(
    players: pd.DataFrame,
    games: pd.DataFrame,
    teams: pd.DataFrame,
    year: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return a roster universe and appearance rows from a Vaastav season."""
    required_players = {"id", "code", "first_name", "second_name", "element_type", "team"}
    required_games = {"element", "fixture", "minutes"}
    missing_players = required_players - set(players.columns)
    missing_games = required_games - set(games.columns)
    if missing_players or missing_games:
        raise ValueError(
            f"Unexpected Vaastav schema for {year}: players={sorted(missing_players)}, "
            f"games={sorted(missing_games)}"
        )

    profiles = players.copy()
    profiles["code"] = pd.to_numeric(profiles["code"], errors="coerce").astype("Int64")
    if profiles["code"].isna().any():
        raise ValueError(f"Vaastav {year} players contain missing stable FPL codes")
    if profiles["code"].duplicated().any():
        raise ValueError(f"Vaastav {year} stable FPL codes are not unique")

    team_lookup: dict[int, str] = {}
    if {"id", "name"}.issubset(teams.columns):
        team_lookup = dict(
            zip(
                pd.to_numeric(teams["id"], errors="coerce").dropna().astype(int),
                teams.loc[pd.to_numeric(teams["id"], errors="coerce").notna(), "name"].astype(str),
            )
        )

    profiles["player_id"] = profiles["code"].map(_stable_player_id)
    profiles["name"] = (
        profiles["first_name"].fillna("").astype(str).str.strip()
        + " "
        + profiles["second_name"].fillna("").astype(str).str.strip()
    ).str.strip()
    profiles["season"] = int(year)
    profiles["role"] = profiles["element_type"].map(_role)
    profiles["team"] = pd.to_numeric(profiles["team"], errors="coerce").map(team_lookup)
    profiles["date_of_birth_fpl"] = pd.to_datetime(
        profiles.get("birth_date", pd.Series(index=profiles.index, dtype="object")),
        errors="coerce",
        utc=True,
    )
    roster = profiles[
        ["player_id", "name", "season", "role", "team", "code", "id", "date_of_birth_fpl"]
    ].rename(columns={"code": "fpl_code", "id": "season_element_id"})
    roster["source"] = "vaastav_fpl_archive"
    roster["roster_coverage"] = "all_players_present_in_end_of_season_FPL_player_table"

    element_lookup = profiles[["id", "player_id", "code", "name", "role"]].rename(
        columns={"id": "element", "name": "canonical_name"}
    )
    appearances = games.copy()
    appearances = _numeric(
        appearances,
        ["element", "fixture", "minutes", *COMMON_GAME_SUMS, "round", "GW"],
    )
    appearances = appearances.loc[appearances["minutes"].fillna(0) > 0].copy()
    appearances = appearances.merge(element_lookup, on="element", how="left", validate="many_to_one")
    if appearances["player_id"].isna().any():
        raise ValueError(f"Vaastav {year} appearance rows failed stable-code mapping")
    # The game archive's ``name`` is a mutable display label.  Use the player
    # table's full canonical name while retaining FPL ``code`` as the identity.
    appearances["name"] = appearances["canonical_name"]

    appearances["season"] = int(year)
    appearances["game_id"] = (
        "epl:" + str(year) + ":fixture:" + appearances["fixture"].astype("Int64").astype(str)
    )
    appearances["game_date"] = pd.to_datetime(appearances.get("kickoff_time"), errors="coerce", utc=True)
    appearances["opportunity"] = appearances["minutes"].astype(float)
    appearances["opportunity_minutes"] = appearances["opportunity"]
    if "position" in appearances:
        appearances["role"] = appearances["position"].map(_role).fillna(appearances["role"])
    appearances["team"] = appearances.get("team", pd.Series(index=appearances.index, dtype="object"))
    for column in POSSESSION_COLUMNS:
        appearances[column] = np.nan
    appearances["possession_metric_coverage"] = "not_observed_in_five_season_FPL_common_core"
    appearances["defensive_counts_observed"] = False
    appearances["source"] = "vaastav_fpl_archive"
    appearances["data_tier"] = "common_core"

    keep = [
        "player_id",
        "name",
        "season",
        "game_id",
        "game_date",
        "role",
        "team",
        "opportunity",
        "opportunity_minutes",
        "goals_scored",
        "assists",
        "clean_sheets",
        "goals_conceded",
        "saves",
        "yellow_cards",
        "red_cards",
        *POSSESSION_COLUMNS,
        "possession_metric_coverage",
        "defensive_counts_observed",
        "source",
        "data_tier",
    ]
    return roster, appearances[keep]


def _prepare_enhanced_2025(
    players: pd.DataFrame,
    teams: pd.DataFrame,
    stats_frames: list[pd.DataFrame],
    lineup_frames: list[pd.DataFrame],
    match_frames: list[pd.DataFrame],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Create genuine 2025-26 appearance rows from detailed match tables."""
    required_players = {"player_id", "player_code", "first_name", "second_name", "position"}
    if required_players - set(players.columns):
        raise ValueError(
            f"Unexpected FPL-Core players schema: {sorted(required_players - set(players.columns))}"
        )
    if not stats_frames:
        raise ValueError("No FPL-Core match-stat frames were supplied")

    player_map = players.copy()
    player_map["player_id"] = pd.to_numeric(player_map["player_id"], errors="coerce").astype("Int64")
    player_map["player_code"] = pd.to_numeric(player_map["player_code"], errors="coerce").astype("Int64")
    player_map["stable_player_id"] = player_map["player_code"].map(_stable_player_id)
    player_map["canonical_name"] = (
        player_map["first_name"].fillna("").astype(str).str.strip()
        + " "
        + player_map["second_name"].fillna("").astype(str).str.strip()
    ).str.strip()
    player_map["canonical_role"] = player_map["position"].map(_role)

    team_lookup = {}
    if {"code", "name"}.issubset(teams.columns):
        team_lookup = dict(
            zip(
                pd.to_numeric(teams["code"], errors="coerce").dropna().astype(int),
                teams.loc[pd.to_numeric(teams["code"], errors="coerce").notna(), "name"].astype(str),
            )
        )

    stats = pd.concat(stats_frames, ignore_index=True)
    if not {"player_id", "match_id", "minutes_played"}.issubset(stats.columns):
        raise ValueError("FPL-Core match stats lack player_id/match_id/minutes_played")
    stats["player_id"] = pd.to_numeric(stats["player_id"], errors="coerce").astype("Int64")
    stats = _numeric(
        stats,
        [
            "minutes_played",
            "goals",
            "assists",
            "saves",
            "goals_conceded",
            "tackles",
            "tackles_won",
            "interceptions",
            "recoveries",
            "blocks",
            "clearances",
            "headed_clearances",
            "duels_won",
            "duels_lost",
            "ground_duels_won",
            "aerial_duels_won",
            "dribbled_past",
            "fouls_committed",
            "dispossessed",
            "defensive_contributions",
            "top_speed",
            "distance_covered",
            "number_of_sprints",
        ],
    )
    stats = stats.loc[stats["minutes_played"].fillna(0) > 0].copy()

    duplicate_rows = int(stats.duplicated(["player_id", "match_id"]).sum())
    if duplicate_rows:
        metric_columns = ["minutes_played", "tackles", "tackles_won", "interceptions", "recoveries", "blocks"]
        conflict = stats.groupby(["player_id", "match_id"], dropna=False)[metric_columns].nunique(
            dropna=False
        )
        if (conflict > 1).any(axis=None):
            raise ValueError("Conflicting duplicate FPL-Core player-match rows")
        stats = stats.drop_duplicates(["player_id", "match_id"], keep="last")

    stats = stats.merge(
        player_map[["player_id", "stable_player_id", "player_code", "canonical_name", "canonical_role"]],
        on="player_id",
        how="left",
        validate="many_to_one",
    )
    if stats["stable_player_id"].isna().any():
        raise ValueError("FPL-Core appearance rows failed stable player-code mapping")

    if lineup_frames:
        lineups = pd.concat(lineup_frames, ignore_index=True)
        lineups["player_id"] = pd.to_numeric(lineups["player_id"], errors="coerce").astype("Int64")
        lineup_keep = [
            column
            for column in [
                "player_id",
                "match_id",
                "team_code",
                "position",
                "is_starting",
                "team_side",
                "formation",
            ]
            if column in lineups
        ]
        lineups = lineups[lineup_keep].drop_duplicates(["player_id", "match_id"], keep="last")
        stats = stats.merge(lineups, on=["player_id", "match_id"], how="left", validate="one_to_one")
    else:
        stats["team_code"] = np.nan
        stats["position"] = np.nan

    if match_frames:
        matches = pd.concat(match_frames, ignore_index=True)
        matches = matches.drop_duplicates("match_id", keep="last")
        match_keep = [
            column
            for column in ["match_id", "gameweek", "kickoff_time", "home_team", "away_team", "finished"]
            if column in matches
        ]
        stats = stats.merge(matches[match_keep], on="match_id", how="left", validate="many_to_one")
    else:
        stats["kickoff_time"] = pd.NaT

    stats["season"] = 2025
    stats["game_id"] = "epl:2025:" + stats["match_id"].astype(str)
    stats["game_date"] = pd.to_datetime(stats.get("kickoff_time"), errors="coerce", utc=True)
    stats["role"] = stats.get("position", pd.Series(index=stats.index, dtype="object")).map(_role)
    stats.loc[stats["role"].eq("UNK"), "role"] = stats.loc[stats["role"].eq("UNK"), "canonical_role"]
    stats["team"] = pd.to_numeric(stats.get("team_code"), errors="coerce").map(team_lookup)
    stats["opportunity"] = stats["minutes_played"].astype(float)
    stats["opportunity_minutes"] = stats["opportunity"]
    stats["goals_scored"] = stats["goals"]
    stats["yellow_cards"] = np.nan
    stats["red_cards"] = np.nan
    stats["clean_sheets"] = np.nan
    stats["defensive_contributions_raw"] = stats["defensive_contributions"]
    stats["top_speed_kmh"] = stats["top_speed"]
    stats["distance_covered_km"] = stats["distance_covered"]
    stats["possession_metric_coverage"] = "observed_FPL-Core-Insights_2025-26_match_detail"
    stats["defensive_counts_observed"] = True
    stats["source"] = "FPL-Core-Insights"
    stats["data_tier"] = "enhanced_recent_season"

    keep = [
        "stable_player_id",
        "canonical_name",
        "season",
        "game_id",
        "game_date",
        "role",
        "team",
        "opportunity",
        "opportunity_minutes",
        "goals_scored",
        "assists",
        "clean_sheets",
        "goals_conceded",
        "saves",
        "yellow_cards",
        "red_cards",
        *POSSESSION_COLUMNS,
        "top_speed_kmh",
        "distance_covered_km",
        "number_of_sprints",
        "possession_metric_coverage",
        "defensive_counts_observed",
        "source",
        "data_tier",
    ]
    result = stats[keep].rename(columns={"stable_player_id": "player_id", "canonical_name": "name"})
    qa = {
        "raw_appearance_rows": int(
            len(pd.concat(stats_frames, ignore_index=True).query("minutes_played > 0"))
        ),
        "duplicate_player_match_rows_removed": duplicate_rows,
        "appearance_rows": int(len(result)),
        "unique_matches": int(result["game_id"].nunique()),
        "unique_players": int(result["player_id"].nunique()),
        "metric_non_null_rows": {
            column: int(result[column].notna().sum())
            for column in ["tackles", "tackles_won", "interceptions", "recoveries", "blocks"]
        },
    }
    return result, qa


def _extract_espn_team_ids(payload: dict[str, Any]) -> list[str]:
    teams: list[str] = []
    for sport in payload.get("sports", []):
        for league in sport.get("leagues", []):
            for wrapper in league.get("teams", []):
                team_id = wrapper.get("team", {}).get("id")
                if team_id is not None:
                    teams.append(str(team_id))
    return sorted(set(teams), key=lambda value: int(value))


def _parse_espn_profiles(payloads: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        team = payload.get("team", {})
        timestamp = payload.get("timestamp")
        for athlete in payload.get("athletes", []):
            rows.append(
                {
                    "espn_player_id": str(athlete.get("id")),
                    "espn_name": athlete.get("fullName") or athlete.get("displayName"),
                    "espn_display_name": athlete.get("displayName"),
                    "espn_short_name": athlete.get("shortName"),
                    "espn_team": team.get("displayName") or team.get("name"),
                    "height_cm": (
                        float(athlete["height"]) * 2.54 if athlete.get("height") is not None else np.nan
                    ),
                    "weight_kg": (
                        float(athlete["weight"]) * 0.45359237 if athlete.get("weight") is not None else np.nan
                    ),
                    "date_of_birth": athlete.get("dateOfBirth"),
                    "profile_age_at_source": athlete.get("age"),
                    "physical_source_date": str(timestamp)[:10] if timestamp else None,
                }
            )
    if not rows:
        return pd.DataFrame(
            columns=[
                "espn_player_id",
                "espn_name",
                "espn_display_name",
                "espn_short_name",
                "espn_team",
                "height_cm",
                "weight_kg",
                "date_of_birth",
                "profile_age_at_source",
                "physical_source_date",
            ]
        )
    frame = pd.DataFrame(rows)
    frame["date_of_birth"] = pd.to_datetime(frame["date_of_birth"], errors="coerce", utc=True)
    return frame.drop_duplicates(["espn_player_id", "espn_team"], keep="last")


def _name_score(fpl_names: list[str], espn_names: list[str]) -> tuple[float, str]:
    left = [_normalize_name(value) for value in fpl_names if value]
    right = [_normalize_name(value) for value in espn_names if value]
    left = [value for value in left if value]
    right = [value for value in right if value]
    if not left or not right:
        return 0.0, "unmatched"
    if set(left) & set(right):
        return 1.0, "exact_normalized_name"
    best = max(SequenceMatcher(None, a, b).ratio() for a in left for b in right)
    for a in left:
        for b in right:
            a_tokens, b_tokens = a.split(), b.split()
            if a_tokens and b_tokens and a_tokens[0][0] == b_tokens[0][0] and a_tokens[-1] == b_tokens[-1]:
                best = max(best, 0.94)
    return best, "team_constrained_fuzzy_name"


def _match_physical_profiles(
    fpl_players: pd.DataFrame,
    fpl_teams: pd.DataFrame,
    espn_profiles: pd.DataFrame,
) -> pd.DataFrame:
    players = fpl_players.copy()
    teams = fpl_teams.copy()
    teams["team_code"] = pd.to_numeric(teams["code"], errors="coerce").astype("Int64")
    team_name_column = "fotmob_name" if "fotmob_name" in teams else "name"
    team_lookup = teams[["team_code", team_name_column]].rename(columns={team_name_column: "fpl_team"})
    players["team_code"] = pd.to_numeric(players["team_code"], errors="coerce").astype("Int64")
    players = players.merge(team_lookup, on="team_code", how="left", validate="many_to_one")
    players["player_code"] = pd.to_numeric(players["player_code"], errors="coerce").astype("Int64")

    espn = espn_profiles.copy()
    espn["team_key"] = espn["espn_team"].map(_normalize_name)
    rows: list[dict[str, Any]] = []
    for player in players.itertuples(index=False):
        team_key = _normalize_name(getattr(player, "fpl_team", ""))
        candidates = espn.loc[espn["team_key"] == team_key].copy()
        if candidates.empty:
            continue
        fpl_names = [
            f"{getattr(player, 'first_name', '')} {getattr(player, 'second_name', '')}".strip(),
            str(getattr(player, "web_name", "") or ""),
        ]
        scored: list[tuple[float, str, int]] = []
        for index, candidate in candidates.iterrows():
            score, method = _name_score(
                fpl_names,
                [
                    candidate.get("espn_name"),
                    candidate.get("espn_display_name"),
                    candidate.get("espn_short_name"),
                ],
            )
            scored.append((score, method, index))
        scored.sort(reverse=True)
        best_score, method, best_index = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        if best_score < 0.88 or (best_score < 1.0 and best_score - second_score < 0.03):
            continue
        profile = candidates.loc[best_index]
        rows.append(
            {
                "player_id": _stable_player_id(player.player_code),
                "espn_player_id": profile["espn_player_id"],
                "height_cm": profile["height_cm"],
                "weight_kg": profile["weight_kg"],
                "date_of_birth": profile["date_of_birth"],
                "physical_source_date": profile["physical_source_date"],
                "physical_match_method": method,
                "physical_match_score": float(best_score),
                "physical_source": "ESPN public roster profile JSON (season=2025 endpoint)",
                "physical_temporality": (
                    "profile snapshot retrieved after 2025-26; height/weight are not asserted as historic "
                    "season measurements"
                ),
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        return pd.DataFrame(
            columns=[
                "player_id",
                "espn_player_id",
                "height_cm",
                "weight_kg",
                "date_of_birth",
                "physical_source_date",
                "physical_match_method",
                "physical_match_score",
                "physical_source",
                "physical_temporality",
            ]
        )
    return result.drop_duplicates("player_id", keep="last")


def _aggregate_player_seasons(roster: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    sum_columns = [*COMMON_GAME_SUMS, *POSSESSION_COLUMNS]
    for column in sum_columns:
        if column not in games:
            games[column] = np.nan

    grouped_rows: list[dict[str, Any]] = []
    for (player_id, season), group in games.groupby(["player_id", "season"], sort=False):
        row: dict[str, Any] = {
            "player_id": player_id,
            "season": int(season),
            "opportunity": float(group["opportunity"].sum()),
            "opportunity_minutes": float(group["opportunity_minutes"].sum()),
            "games_played": int(group["game_id"].nunique()),
            "teams_observed": ";".join(sorted(set(group["team"].dropna().astype(str)))),
            "data_tier": group["data_tier"].iloc[-1],
            "possession_metric_coverage": group["possession_metric_coverage"].iloc[-1],
            "defensive_counts_observed": bool(group["defensive_counts_observed"].any()),
        }
        for column in sum_columns:
            row[column] = group[column].sum(min_count=1)
        if "top_speed_kmh" in group:
            row["top_speed_kmh"] = group["top_speed_kmh"].max(skipna=True)
        grouped_rows.append(row)
    aggregates = pd.DataFrame(grouped_rows)

    panel = roster.copy()
    panel = panel.merge(aggregates, on=["player_id", "season"], how="left", validate="one_to_one")
    panel["opportunity"] = panel["opportunity"].fillna(0.0)
    panel["opportunity_minutes"] = panel["opportunity_minutes"].fillna(0.0)
    panel["games_played"] = panel["games_played"].fillna(0).astype(int)
    panel["teams_observed"] = panel["teams_observed"].fillna("")
    panel["data_tier"] = panel["data_tier"].fillna(
        panel["season"].map(lambda value: "enhanced_recent_season" if value == 2025 else "common_core")
    )
    panel["possession_metric_coverage"] = panel["possession_metric_coverage"].fillna(
        panel["season"].map(
            lambda value: (
                "observed_FPL-Core-Insights_2025-26_match_detail"
                if value == 2025
                else "not_observed_in_five_season_FPL_common_core"
            )
        )
    )
    observed_default = panel["season"].eq(2025)
    panel["defensive_counts_observed"] = (
        panel["defensive_counts_observed"]
        .where(panel["defensive_counts_observed"].notna(), observed_default)
        .astype(bool)
    )

    # A rostered player with no minutes has genuinely zero 2025-26 events because
    # the enhanced source covers all league matches. Older missing counts stay NA.
    current_no_games = panel["season"].eq(2025) & panel["games_played"].eq(0)
    for column in [*COMMON_GAME_SUMS, *POSSESSION_COLUMNS]:
        if column in panel:
            panel.loc[current_no_games & panel[column].isna(), column] = 0.0
    return panel


def _attach_physical(frame: pd.DataFrame, physical: pd.DataFrame, *, game_level: bool) -> pd.DataFrame:
    result = frame.merge(physical, on="player_id", how="left", validate="many_to_one")
    if "date_of_birth_fpl" in result:
        fpl_dob = pd.to_datetime(result["date_of_birth_fpl"], errors="coerce", utc=True)
        espn_dob = pd.to_datetime(result["date_of_birth"], errors="coerce", utc=True)
        result["date_of_birth"] = fpl_dob.combine_first(espn_dob)
        result["age_source"] = np.where(
            fpl_dob.notna(),
            "FPL players_raw birth_date",
            np.where(espn_dob.notna(), "ESPN roster dateOfBirth", None),
        )
    else:
        result["age_source"] = np.where(result["date_of_birth"].notna(), "ESPN roster dateOfBirth", None)
    if game_level:
        result["age"] = [
            _age_on(dob, when) for dob, when in zip(result["date_of_birth"], result["game_date"])
        ]
    else:
        result["age"] = [
            _age_on(dob, pd.Timestamp(date(int(season), 8, 1)))
            for dob, season in zip(result["date_of_birth"], result["season"])
        ]
    for column in ["wingspan_cm", "arm_length_cm", "leg_length_cm"]:
        result[column] = np.nan
    return result


def _download_common(root: Path, year: int) -> tuple[Path, Path, Path]:
    slug = _season_slug(year)
    raw = root / "data" / "raw" / SPORT / "vaastav" / slug
    players = fetch(
        f"{VAASTAV_BASE}/{slug}/players_raw.csv",
        raw / "players_raw.csv",
        source="vaastav/Fantasy-Premier-League",
        license_note=VAASTAV_LICENSE,
    )
    games = fetch(
        f"{VAASTAV_BASE}/{slug}/gws/merged_gw.csv",
        raw / "merged_gw.csv",
        source="vaastav/Fantasy-Premier-League",
        license_note=VAASTAV_LICENSE,
    )
    teams = fetch(
        f"{VAASTAV_BASE}/{slug}/teams.csv",
        raw / "teams.csv",
        source="vaastav/Fantasy-Premier-League",
        license_note=VAASTAV_LICENSE,
    )
    return players, games, teams


def _download_enhanced(root: Path) -> tuple[Path, Path, list[Path], list[Path], list[Path]]:
    raw = root / "data" / "raw" / SPORT / "fpl_core_insights" / "2025-26"
    players = fetch(
        f"{CORE_BASE}/players.csv",
        raw / "players.csv",
        source="olbauday/FPL-Core-Insights",
        license_note=CORE_LICENSE,
    )
    teams = fetch(
        f"{CORE_BASE}/teams.csv",
        raw / "teams.csv",
        source="olbauday/FPL-Core-Insights",
        license_note=CORE_LICENSE,
    )
    stats_paths: list[Path] = []
    lineup_paths: list[Path] = []
    match_paths: list[Path] = []
    for gameweek in range(1, 39):
        gw_url = f"{CORE_PL_BASE}/GW{gameweek}"
        stats_paths.append(
            fetch(
                f"{gw_url}/playermatchstats.csv",
                raw / f"gw_{gameweek:02d}_playermatchstats.csv",
                source="olbauday/FPL-Core-Insights",
                license_note=CORE_LICENSE,
            )
        )
        lineup_paths.append(
            fetch(
                f"{gw_url}/lineups.csv",
                raw / f"gw_{gameweek:02d}_lineups.csv",
                source="olbauday/FPL-Core-Insights",
                license_note=CORE_LICENSE,
            )
        )
        match_paths.append(
            fetch(
                f"{gw_url}/matches.csv",
                raw / f"gw_{gameweek:02d}_matches.csv",
                source="olbauday/FPL-Core-Insights",
                license_note=CORE_LICENSE,
            )
        )
    return players, teams, stats_paths, lineup_paths, match_paths


def _download_espn_profiles(root: Path) -> list[Path]:
    raw = root / "data" / "raw" / SPORT / "espn_profiles" / "2025-26"
    teams_path = fetch(
        ESPN_TEAMS_URL,
        raw / "teams.json",
        source="ESPN public site API",
        license_note=ESPN_LICENSE,
    )
    payload = json.loads(teams_path.read_text())
    paths: list[Path] = []
    for team_id in _extract_espn_team_ids(payload):
        paths.append(
            fetch(
                f"https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams/{team_id}/roster?season=2025",
                raw / f"team_{team_id}_roster.json",
                source="ESPN public site API",
                license_note=ESPN_LICENSE,
            )
        )
    return paths


def recent_season_model(
    panel: pd.DataFrame,
    root: Path,
    *,
    min_minutes: int = 450,
    random_state: int = 202510,
) -> dict[str, Any]:
    """Fit bounded 2025-26 player-held-out profile/event-rate associations.

    This is deliberately separate from the temporal forecasting layer.  It uses
    only broad role and profile fields, never other same-season event outcomes,
    to associate player characteristics with genuine event rates per 90 minutes.
    It is retrospective evidence, not a deployable next-season forecast.
    """
    from joblib import dump
    from scipy.stats import spearmanr
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import RidgeCV
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    required = {
        "player_id",
        "name",
        "season",
        "role",
        "opportunity",
        "age",
        "height_cm",
        "weight_kg",
        "tackles",
        "interceptions",
        "recoveries",
        "blocks",
    }
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"Recent EPL model is missing columns: {sorted(missing)}")

    cohort = panel.loc[
        panel["season"].eq(2025) & pd.to_numeric(panel["opportunity"], errors="coerce").ge(min_minutes)
    ].copy()
    if "defensive_counts_observed" in cohort:
        cohort = cohort.loc[cohort["defensive_counts_observed"].fillna(False).astype(bool)].copy()
    if cohort["player_id"].duplicated().any():
        raise ValueError("Recent EPL model expects one row per athlete in the target season")
    if len(cohort) < 80:
        result = {
            "status": "insufficient_sample",
            "season": 2025,
            "eligible_players": int(len(cohort)),
            "minimum_minutes": int(min_minutes),
        }
        write_json(Path(root) / "reports" / SPORT / "recent_2025_association.json", result)
        return result

    numeric_features = ["height_cm", "weight_kg", "age"]
    categorical_features = ["role"]
    feature_columns = [*categorical_features, *numeric_features]
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=random_state)
    train_indices, test_indices = next(splitter.split(cohort, groups=cohort["player_id"].astype(str)))
    train = cohort.iloc[train_indices].copy()
    test = cohort.iloc[test_indices].copy()
    overlap = set(train["player_id"]) & set(test["player_id"])
    if overlap:
        raise ValueError("Player-held-out EPL split leaked athletes across folds")

    report_dir = Path(root) / "reports" / SPORT
    model_dir = Path(root) / "models" / SPORT
    report_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    split_manifest = {
        "method": "GroupShuffleSplit by stable player_id",
        "random_state": random_state,
        "train_player_ids": sorted(train["player_id"].astype(str).tolist()),
        "test_player_ids": sorted(test["player_id"].astype(str).tolist()),
        "player_overlap": 0,
    }
    write_json(report_dir / "recent_2025_split_manifest.json", split_manifest)

    predictions: list[pd.DataFrame] = []
    target_results: dict[str, Any] = {}
    for target in ["tackles", "interceptions", "recoveries", "blocks"]:
        train_target = train.loc[train[target].notna()].copy()
        test_target = test.loc[test[target].notna()].copy()
        if len(train_target) < 60 or len(test_target) < 20:
            target_results[target] = {
                "status": "insufficient_observed_target_rows",
                "n_train": int(len(train_target)),
                "n_test": int(len(test_target)),
            }
            continue
        train_target["target_per90"] = (
            pd.to_numeric(train_target[target], errors="coerce") * 90.0 / train_target["opportunity"]
        )
        test_target["target_per90"] = (
            pd.to_numeric(test_target[target], errors="coerce") * 90.0 / test_target["opportunity"]
        )

        transform = ColumnTransformer(
            [
                (
                    "numeric",
                    Pipeline(
                        [
                            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                            ("scale", StandardScaler()),
                        ]
                    ),
                    numeric_features,
                ),
                (
                    "role",
                    Pipeline(
                        [
                            ("impute", SimpleImputer(strategy="most_frequent")),
                            ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                        ]
                    ),
                    categorical_features,
                ),
            ]
        )
        model = Pipeline(
            [
                ("features", transform),
                ("regressor", RidgeCV(alphas=np.array([0.1, 1.0, 10.0, 100.0]))),
            ]
        )
        model.fit(train_target[feature_columns], train_target["target_per90"])
        predicted = np.clip(model.predict(test_target[feature_columns]), 0.0, None)

        role_means = train_target.groupby("role")["target_per90"].mean()
        global_mean = float(train_target["target_per90"].mean())
        baseline = test_target["role"].map(role_means).fillna(global_mean).to_numpy(dtype=float)
        actual = test_target["target_per90"].to_numpy(dtype=float)
        rho = spearmanr(actual, predicted).statistic
        model_mae = float(mean_absolute_error(actual, predicted))
        baseline_mae = float(mean_absolute_error(actual, baseline))
        target_results[target] = {
            "status": "trained",
            "n_train": int(len(train_target)),
            "n_test": int(len(test_target)),
            "target": f"{target}_per_90_minutes",
            "ridge_alpha": float(model.named_steps["regressor"].alpha_),
            "model_mae": model_mae,
            "role_mean_baseline_mae": baseline_mae,
            "mae_improvement_vs_role_mean_pct": (
                float(100.0 * (baseline_mae - model_mae) / baseline_mae) if baseline_mae > 0 else None
            ),
            "model_rmse": float(mean_squared_error(actual, predicted) ** 0.5),
            "model_r2": float(r2_score(actual, predicted)),
            "model_spearman": float(rho) if np.isfinite(rho) else None,
        }
        dump(
            {
                "pipeline": model,
                "target": f"{target}_per_90_minutes",
                "features": feature_columns,
                "minimum_minutes": min_minutes,
                "scope": "retrospective 2025-26 player-held-out association",
            },
            model_dir / f"recent_2025_{target}_per90.joblib",
        )
        prediction = test_target[["player_id", "name", "role", "opportunity", target]].copy()
        prediction["target"] = target
        prediction["actual_per90"] = actual
        prediction["profile_ridge_prediction_per90"] = predicted
        prediction["role_mean_baseline_per90"] = baseline
        predictions.append(prediction)

    if predictions:
        pd.concat(predictions, ignore_index=True).to_parquet(
            report_dir / "recent_2025_predictions.parquet", index=False
        )

    result = {
        "status": "trained"
        if any(value.get("status") == "trained" for value in target_results.values())
        else "insufficient_sample",
        "scope": "retrospective within-2025-26 association; not a next-season forecast",
        "season": 2025,
        "target_unit": "events per 90 minutes",
        "minimum_minutes": int(min_minutes),
        "eligible_players": int(len(cohort)),
        "n_train_players": int(train["player_id"].nunique()),
        "n_test_players": int(test["player_id"].nunique()),
        "player_overlap": 0,
        "features": feature_columns,
        "same_season_event_predictors_used": False,
        "profile_caveat": (
            "Height/weight are dated ESPN profile snapshots and may postdate the playing season; "
            "missing values are median-imputed with indicators."
        ),
        "feature_coverage": {feature: float(cohort[feature].notna().mean()) for feature in numeric_features},
        "baseline": "training-fold role mean for the same per-90 target",
        "targets": target_results,
    }
    write_json(report_dir / "recent_2025_association.json", result)
    lines = [
        "# EPL 2025-26 recent-season possession association",
        "",
        "This is a retrospective player-held-out association, not a temporal or next-season forecast.",
        f"Cohort: {len(cohort)} players with at least {min_minutes} league minutes; "
        f"{len(train)} train and {len(test)} unseen test athletes.",
        "Inputs are broad FPL role, age, height, and weight. No same-season event statistic is an input.",
        "Targets are genuine FPL-Core-Insights tackles, interceptions, recoveries, and blocks per 90.",
        "The comparison baseline is the target's training-fold mean within broad role.",
        "",
        "| Target | Test n | Ridge MAE | Role-mean MAE | Spearman |",
        "|---|---:|---:|---:|---:|",
    ]
    for target, metric in target_results.items():
        if metric.get("status") == "trained":
            lines.append(
                f"| {target} | {metric['n_test']} | {metric['model_mae']:.3f} | "
                f"{metric['role_mean_baseline_mae']:.3f} | "
                f"{metric['model_spearman'] if metric['model_spearman'] is not None else 'NA'} |"
            )
        else:
            lines.append(f"| {target} | {metric.get('n_test', 0)} | NA | NA | NA |")
    lines.extend(
        [
            "",
            "Negative improvement is an honest result: it means the simple role mean beat the profile model.",
            "Current profile snapshots and broad roles limit causal or scouting interpretation.",
            "",
        ]
    )
    (report_dir / "recent_2025_association.md").write_text("\n".join(lines))
    return result


def run(root: Path, seasons: list[int]) -> dict[str, Any]:
    """Download, build, validate, save, and analyze the Premier League panels."""
    root = Path(root)
    years = sorted({int(season) for season in seasons})
    unsupported = [year for year in years if year < 2021 or year > 2025]
    if unsupported:
        raise ValueError(f"EPL adapter currently supports start years 2021..2025, not {unsupported}")

    rosters: list[pd.DataFrame] = []
    common_games: list[pd.DataFrame] = []
    raw_common_qa: dict[str, Any] = {}
    for year in years:
        player_path, game_path, team_path = _download_common(root, year)
        roster, games = _prepare_common_season(
            read_frame(player_path), read_frame(game_path), read_frame(team_path), year
        )
        rosters.append(roster)
        common_games.append(games)
        raw_common_qa[str(year)] = {
            "rostered_players": int(len(roster)),
            "appearance_rows": int(len(games)),
            "unique_appearing_players": int(games["player_id"].nunique()),
            "minutes": float(games["opportunity_minutes"].sum()),
        }

    roster_panel = pd.concat(rosters, ignore_index=True)
    game_panel = pd.concat(common_games, ignore_index=True)
    enhanced_qa: dict[str, Any] | None = None
    physical = pd.DataFrame(
        columns=[
            "player_id",
            "espn_player_id",
            "height_cm",
            "weight_kg",
            "date_of_birth",
            "physical_source_date",
            "physical_match_method",
            "physical_match_score",
            "physical_source",
            "physical_temporality",
        ]
    )

    if 2025 in years:
        core_player_path, core_team_path, stat_paths, lineup_paths, match_paths = _download_enhanced(root)
        core_players = read_frame(core_player_path)
        core_teams = read_frame(core_team_path)
        enhanced_games, enhanced_qa = _prepare_enhanced_2025(
            core_players,
            core_teams,
            [read_frame(path) for path in stat_paths],
            [read_frame(path) for path in lineup_paths],
            [read_frame(path) for path in match_paths],
        )
        # The detailed source is the only 2025-26 defensive-event layer. Do not
        # pool its new defensive-contribution fields with older FPL schemas.
        game_panel = pd.concat(
            [game_panel.loc[game_panel["season"] != 2025], enhanced_games],
            ignore_index=True,
            sort=False,
        )

        roster_payloads = [json.loads(path.read_text()) for path in _download_espn_profiles(root)]
        espn_profiles = _parse_espn_profiles(roster_payloads)
        physical = _match_physical_profiles(core_players, core_teams, espn_profiles)

    player_seasons = _aggregate_player_seasons(roster_panel, game_panel)
    player_seasons = _attach_physical(player_seasons, physical, game_level=False)
    game_panel = game_panel.merge(
        roster_panel[["player_id", "season", "date_of_birth_fpl"]],
        on=["player_id", "season"],
        how="left",
        validate="many_to_one",
    )
    player_games = _attach_physical(game_panel, physical, game_level=True)

    player_seasons = player_seasons.sort_values(["season", "player_id"]).reset_index(drop=True)
    player_games = player_games.sort_values(["season", "game_date", "game_id", "player_id"]).reset_index(
        drop=True
    )

    processed = root / "data" / "processed" / SPORT
    processed.mkdir(parents=True, exist_ok=True)
    season_path = processed / "player_seasons.parquet"
    game_path = processed / "player_games.parquet"
    physical_path = processed / "physical_profiles.parquet"
    player_seasons.to_parquet(season_path, index=False)
    player_games.to_parquet(game_path, index=False)
    physical.to_parquet(physical_path, index=False)

    negative_columns = ["opportunity_minutes", "tackles", "interceptions", "recoveries", "blocks"]
    negative_counts = {
        column: int((pd.to_numeric(player_games[column], errors="coerce") < 0).sum())
        for column in negative_columns
        if column in player_games
    }
    stable_id_missing = int(player_seasons["player_id"].isna().sum())
    duplicate_player_seasons = int(player_seasons.duplicated(["player_id", "season"]).sum())
    duplicate_player_games = int(player_games.duplicated(["player_id", "game_id"]).sum())
    physical_rows = int(player_seasons["height_cm"].notna().sum())
    qa = {
        "sport": SPORT,
        "seasons_requested": years,
        "season_rows": int(len(player_seasons)),
        "game_rows": int(len(player_games)),
        "unique_players": int(player_seasons["player_id"].nunique()),
        "common_core_by_season": raw_common_qa,
        "enhanced_2025_26": enhanced_qa,
        "stable_id_namespace": "fpl:<Fantasy Premier League player code>",
        "stable_id_missing": stable_id_missing,
        "duplicate_player_seasons": duplicate_player_seasons,
        "duplicate_player_games": duplicate_player_games,
        "negative_value_counts": negative_counts,
        "physical_profile_matches": int(len(physical)),
        "player_season_rows_with_height": physical_rows,
        "physical_profile_match_methods": (
            physical["physical_match_method"].value_counts(dropna=False).to_dict()
            if not physical.empty
            else {}
        ),
        "possession_coverage_by_season": {
            str(int(season)): {
                metric: int(group[metric].notna().sum())
                for metric in ["tackles", "interceptions", "recoveries", "blocks"]
            }
            for season, group in player_seasons.groupby("season")
        },
        "checks_passed": bool(
            stable_id_missing == 0
            and duplicate_player_seasons == 0
            and duplicate_player_games == 0
            and not any(negative_counts.values())
            and (enhanced_qa is None or enhanced_qa["unique_matches"] == 380)
        ),
        "important_boundary": (
            "Tackles/interceptions/recoveries/blocks are observed only in the enhanced 2025-26 source. "
            "Earlier seasons remain NA, not zero. Defensive_contributions_raw is a 2025-26-only FPL rule field."
        ),
        "physical_boundary": (
            "ESPN height/weight are dated profile snapshots, not measurements taken in each historic season."
        ),
    }
    if not qa["checks_passed"]:
        raise ValueError(f"EPL QA failed: {qa}")
    write_json(processed / "qa.json", qa)
    write_json(root / "reports" / SPORT / "qa.json", qa)

    analysis_result = analyze(root)
    recent_result = (
        recent_season_model(player_seasons, root)
        if 2025 in years
        else {"status": "not_run", "reason": "2025 season was not requested"}
    )
    return {
        "sport": SPORT,
        "player_seasons": str(season_path),
        "player_games": str(game_path),
        "physical_profiles": str(physical_path),
        "qa": qa,
        "analysis": analysis_result,
        "recent_season_model": recent_result,
    }


def analyze(root: Path) -> dict[str, Any]:
    """Run the shared EDA/model layer on the EPL season panel."""
    from possession_lab.analysis import analyze_sport

    panel = read_frame(Path(root) / "data" / "processed" / SPORT / "player_seasons.parquet")
    return analyze_sport(
        panel,
        SPORT,
        Path(root),
        metrics={
            "tackle activity": "tackles",
            "interception activity": "interceptions",
            "ball recovery activity": "recoveries",
            "blocking activity": "blocks",
        },
        physical_features=["height_cm", "weight_kg", "age"],
        limitations=[
            "The five-season FPL common core has no tackles, interceptions, recoveries, or blocks before 2025-26.",
            "The enhanced 2025-26 match archive publishes detailed events but no explicit open-data license.",
            "Public events do not measure pressures, pressing attempts, forced turnovers, or possession-adjusted opportunities.",
            "FPL role buckets do not separate center backs, fullbacks, holding midfielders, wingers, or pressing forwards.",
            "ESPN height/weight are post-season profile snapshots and must not be interpreted as annual measurements.",
            "Wingspan, arm length, and leg length are unavailable at league scale and remain missing.",
        ],
        opportunity_unit="minutes",
    )
