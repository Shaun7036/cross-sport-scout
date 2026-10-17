"""NBA 2021-22--2025-26 regular-season roster and possession-event panel.

The SportsDataverse files use the season-ending year (2022 means 2021-22),
whereas the public project interface uses season-start years. ESPN includes
game-roster rows for DNPs, allowing the processed panel to retain players with
zero appearances instead of applying a minutes-based survivorship filter.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from possession_lab.io import fetch, read_frame, save_frame, write_json

BASE = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
SOURCE_NOTE = (
    "SportsDataverse public release packaging of ESPN NBA data. The repository/software license does not "
    "confer ownership of the underlying ESPN/NBA data; use for reproducible research/prototyping and review "
    "upstream rights before redistribution or commercial use."
)
CROSSWALK_NOTE = (
    "SportsDataverse NBA crosswalk; current-season enrichment with incomplete historical-player coverage. "
    "Underlying provider identifiers retain their upstream rights."
)

# ESPN marks the NBA Cup championship as season_type=2 even though it does not
# count in the 82-game standings. These are the only such games in this fixed
# study window. Keeping the IDs explicit is safer than guessing from dates.
NBA_CUP_FINAL_GAME_IDS = {
    2023: "401607495",  # 2023-24: Indiana vs Los Angeles Lakers
    2024: "401734908",  # 2024-25: Milwaukee vs Oklahoma City
    2025: "401809839",  # 2025-26: New York vs San Antonio
}
NBA_TEAM_IDS = frozenset(range(1, 31))

COUNT_COLUMNS = [
    "steals",
    "blocks",
    "defensive_rebounds",
    "offensive_rebounds",
    "rebounds",
    "turnovers",
    "fouls",
    "assists",
    "points",
]
METRICS = {
    "steals": "steals",
    "blocks": "blocks",
    "defensive_rebounds": "defensive_rebounds",
}

LIMITATIONS = [
    "Steals are direct possession changes; blocks are disruptions and defensive rebounds end opponent possessions. They are not interchangeable and are modeled separately.",
    "The public ESPN box score does not expose deflections, charges drawn, loose balls recovered, contested shots, matchup possessions, top speed or defensive tracking.",
    "ESPN minutes are rounded to whole minutes. Zero-minute rows can be a sub-minute appearance or a roster-coding ambiguity; explicit flags are retained.",
    "Historical SportsDataverse player_core files were regenerated from current ESPN profiles: reported age, experience, current team and status are not historical snapshots.",
    "Height and weight are undated profile values. Height is treated as an adult static descriptor; weight must not be interpreted as season-specific change.",
    "The 2026 NBA-ID crosswalk is current-season enrichment and is not comprehensive for players who left the league in earlier seasons; ESPN athlete_id remains canonical.",
    "All-Star exhibitions and NBA Cup championship games are removed even though ESPN labels them season_type=2; only each team's 82 standings games remain.",
    "No official NBA hustle/tracking enrichment is collected by default because the public website endpoints are undocumented and NBA reuse restrictions require separate review.",
]


def _mode(values: pd.Series) -> object:
    valid = values.dropna()
    if valid.empty:
        return pd.NA
    modes = valid.mode()
    return modes.iloc[0] if len(modes) else valid.iloc[0]


def _join_unique(values: pd.Series) -> str:
    valid = sorted({str(value) for value in values.dropna() if str(value)})
    return ";".join(valid)


def _player_ids(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").astype("Int64")
    return numeric.astype("string")


def map_role(position: object) -> str:
    """Map changing ESPN granularity to stable broad NBA role families."""
    if pd.isna(position):
        return "unknown"
    abbreviation = str(position).strip().upper()
    if abbreviation in {"G", "PG", "SG", "POINT GUARD", "SHOOTING GUARD", "GUARD"}:
        return "guard"
    if abbreviation in {
        "F",
        "SF",
        "PF",
        "SMALL FORWARD",
        "POWER FORWARD",
        "FORWARD",
    }:
        return "forward"
    if abbreviation in {"C", "CENTER"}:
        return "center"
    return "unknown"


def _source_retrieved_at(path: Path) -> str:
    sidecar = path.with_name(path.name + ".source.json")
    if sidecar.exists():
        return str(json.loads(sidecar.read_text()).get("retrieved_at"))
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _filter_regular_box(box: pd.DataFrame, season_start: int) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Keep NBA standings games, excluding exhibitions and the Cup final."""
    frame = box.copy()
    frame["game_id"] = frame["game_id"].astype("string")
    frame["team_id"] = pd.to_numeric(frame["team_id"], errors="coerce").astype("Int64")
    type_two = frame["season_type"].eq(2)
    official_team = frame["team_id"].isin(NBA_TEAM_IDS)
    exhibition = frame[type_two & ~official_team].copy()
    candidate = frame[type_two & official_team].copy()

    # A valid game must contain two distinct NBA teams. This also prevents a
    # partially malformed game from entering the model as if it were complete.
    teams_per_game = candidate.groupby("game_id")["team_id"].nunique()
    invalid_game_ids = set(teams_per_game[teams_per_game.ne(2)].index.astype(str))
    invalid_games = candidate[candidate["game_id"].isin(invalid_game_ids)].copy()
    candidate = candidate[~candidate["game_id"].isin(invalid_game_ids)].copy()

    cup_id = NBA_CUP_FINAL_GAME_IDS.get(season_start)
    cup_rows = candidate[candidate["game_id"].eq(cup_id)].copy() if cup_id else candidate.iloc[0:0].copy()
    if cup_id:
        candidate = candidate[~candidate["game_id"].eq(cup_id)].copy()

    excluded = pd.concat([exhibition, invalid_games, cup_rows], ignore_index=True)
    qa = {
        "raw_rows": int(len(frame)),
        "season_type_2_rows": int(type_two.sum()),
        "exhibition_rows_excluded": int(len(exhibition)),
        "invalid_game_rows_excluded": int(len(invalid_games)),
        "cup_final_rows_excluded": int(len(cup_rows)),
        "cup_final_game_id": cup_id,
    }
    return candidate, excluded, qa


def _appearance_fields(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["reported_dnp"] = result["did_not_play"].fillna(False).astype(bool)
    result["minutes"] = pd.to_numeric(result["minutes"], errors="coerce")
    for column in COUNT_COLUMNS:
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce")
        else:
            result[column] = np.nan
    result["stats_observed"] = result[["steals", "blocks"]].notna().all(axis=1)
    positive_stat = result[COUNT_COLUMNS].fillna(0).abs().sum(axis=1).gt(0)
    starter = result["starter"].fillna(False).astype(bool)
    result["appearance_observed"] = (
        ~result["reported_dnp"]
        & result["minutes"].notna()
        & (result["minutes"].gt(0) | positive_stat | starter)
    )
    conditions = [
        result["reported_dnp"],
        ~result["reported_dnp"] & result["minutes"].isna(),
        result["appearance_observed"] & result["minutes"].eq(0),
        result["appearance_observed"],
    ]
    choices = [
        "reported_dnp",
        "missing_minutes_ambiguous",
        "zero_minute_appearance_or_rounding",
        "confirmed_appearance",
    ]
    result["appearance_status"] = np.select(conditions, choices, default="zero_minute_ambiguous")
    # Preserve the raw missingness at game grain. Structural zeros are assigned
    # only after aggregating a player's documented zero-appearance season.
    result["opportunity"] = result["minutes"]
    result["event_observation_status"] = np.where(
        result["stats_observed"], "box_stats_observed", "not_observed_dnp_or_missing"
    )
    return result


def _prepare_profile(core: pd.DataFrame, season_start: int, source_path: Path) -> pd.DataFrame:
    profile = core.copy()
    profile["player_id"] = _player_ids(profile["athlete_id"])
    profile = profile[profile["player_id"].notna()].copy()
    if profile.duplicated("player_id").any():
        raise ValueError(f"Duplicate ESPN athlete_id in {source_path}")
    profile["profile_reported_age_at_retrieval"] = pd.to_numeric(profile["age"], errors="coerce")
    profile["profile_experience_at_retrieval"] = pd.to_numeric(profile["experience_years"], errors="coerce")
    profile["profile_status_at_retrieval"] = profile["status_type"]
    profile["profile_current_team_id_at_retrieval"] = profile["current_team_id"]
    dob = pd.to_datetime(profile["date_of_birth"], errors="coerce", utc=True).dt.tz_localize(None)
    anchor = pd.Timestamp(f"{season_start}-10-01")
    profile["age"] = (anchor - dob).dt.days / 365.2425
    profile["date_of_birth"] = dob
    profile["height_cm"] = pd.to_numeric(profile["height"], errors="coerce") * 2.54
    profile["weight_kg"] = pd.to_numeric(profile["weight"], errors="coerce") * 0.45359237
    profile["name_profile"] = profile["display_name"]
    profile["position_profile"] = profile["position_abbreviation"]
    profile["role_profile"] = profile["position_profile"].map(map_role)
    profile["espn_uid"] = profile["uid"]
    profile["espn_guid"] = profile["guid"]
    profile["profile_source_retrieved_at"] = _source_retrieved_at(source_path)
    profile["physical_measurement_date"] = pd.NaT
    profile["physical_measurement_context"] = (
        "undated ESPN profile value from a retrospectively regenerated SportsDataverse snapshot"
    )
    profile["physical_asof_valid"] = False
    profile["height_observation_status"] = np.where(
        profile["height_cm"].notna(), "undated_current_profile", "missing"
    )
    profile["weight_observation_status"] = np.where(
        profile["weight_kg"].notna(), "undated_current_profile_not_season_weight", "missing"
    )
    profile["profile_source_season_end"] = season_start + 1
    keep = [
        "player_id",
        "name_profile",
        "date_of_birth",
        "age",
        "height_cm",
        "weight_kg",
        "position_profile",
        "role_profile",
        "espn_uid",
        "espn_guid",
        "profile_reported_age_at_retrieval",
        "profile_experience_at_retrieval",
        "profile_status_at_retrieval",
        "profile_current_team_id_at_retrieval",
        "profile_source_retrieved_at",
        "physical_measurement_date",
        "physical_measurement_context",
        "physical_asof_valid",
        "height_observation_status",
        "weight_observation_status",
        "profile_source_season_end",
    ]
    return profile[keep]


def _aggregate_group(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    grouped = frame.groupby(keys, dropna=False, sort=False)
    base = grouped.agg(
        name_game=("name", _mode),
        role_game=("role", _mode),
        position_game=("position", _mode),
        games_rostered=("game_id", "nunique"),
        games_played_confirmed=("appearance_observed", "sum"),
        games_with_box_stats=("stats_observed", "sum"),
        reported_dnp_games=("reported_dnp", "sum"),
        missing_minutes_ambiguous_games=(
            "appearance_status",
            lambda values: int(values.eq("missing_minutes_ambiguous").sum()),
        ),
        zero_minutes_ambiguous_games=(
            "appearance_status",
            lambda values: int(values.eq("zero_minute_ambiguous").sum()),
        ),
        first_game_date=("game_date", "min"),
        last_game_date=("game_date", "max"),
    )
    sums = grouped[["opportunity", *COUNT_COLUMNS]].sum(min_count=1)
    result = base.join(sums).reset_index()
    return result


def _observation_flags(panel: pd.DataFrame) -> pd.DataFrame:
    result = panel.copy()
    integer_counts = [
        "games_rostered",
        "games_played_confirmed",
        "games_with_box_stats",
        "reported_dnp_games",
        "missing_minutes_ambiguous_games",
        "zero_minutes_ambiguous_games",
    ]
    for column in integer_counts:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0).astype("Int64")

    no_confirmed_appearance = result["games_played_confirmed"].eq(0)
    result["zero_appearance_roster"] = no_confirmed_appearance
    result["profile_only_no_game_roster"] = result["games_rostered"].eq(0)
    # A player with no recorded appearance has zero season opportunity/events,
    # not an unknown per-minute rate. The accompanying status prevents these
    # explicit structural zeros from being confused with observed box-score 0s.
    result.loc[no_confirmed_appearance & result["opportunity"].isna(), "opportunity"] = 0.0
    for column in COUNT_COLUMNS:
        result.loc[no_confirmed_appearance & result[column].isna(), column] = 0.0

    ambiguous = result["missing_minutes_ambiguous_games"].gt(0) | result["zero_minutes_ambiguous_games"].gt(0)
    result["observation_coverage"] = np.select(
        [
            result["profile_only_no_game_roster"],
            no_confirmed_appearance & ambiguous,
            no_confirmed_appearance,
            ambiguous,
        ],
        [
            "profile_only_no_regular_game_roster_record",
            "roster_only_with_ambiguous_minutes",
            "roster_only_zero_recorded_appearance",
            "appearances_observed_with_some_ambiguous_minutes",
        ],
        default="regular_season_box_scores_observed",
    )
    result["events_observed"] = result["games_with_box_stats"].gt(0)
    result["event_total_status"] = np.where(
        result["events_observed"],
        "sum_of_observed_regular_season_box_scores",
        "structural_zero_no_recorded_appearance",
    )
    result["opportunity_observed"] = result["games_played_confirmed"].gt(0) | no_confirmed_appearance
    result["opportunity_status"] = np.where(
        ambiguous,
        "whole_minutes_with_zero_or_missing_minute_ambiguity",
        "whole_minutes_or_explicit_zero_appearance",
    )
    return result


def _build_player_season(games: pd.DataFrame, profile: pd.DataFrame, season_start: int) -> pd.DataFrame:
    annual = _aggregate_group(games, ["player_id"])
    teams = (
        games.groupby("player_id", sort=False)
        .agg(
            team_ids=("team_id", _join_unique),
            teams=("team", _join_unique),
            team_stint_count=("team_id", "nunique"),
        )
        .reset_index()
    )
    annual = annual.merge(teams, on="player_id", how="left", validate="one_to_one")
    panel = profile.merge(annual, on="player_id", how="outer", validate="one_to_one")
    panel["name"] = panel["name_game"].combine_first(panel["name_profile"])
    panel["position"] = panel["position_game"].combine_first(panel["position_profile"])
    panel["role"] = panel["role_game"].combine_first(panel["role_profile"]).fillna("unknown")
    panel["season"] = season_start
    panel["season_end_year"] = season_start + 1
    panel["player_id"] = panel["player_id"].astype("string")
    panel["player_id_source"] = "ESPN athlete_id"
    panel["espn_athlete_id"] = panel["player_id"]
    panel["team_stint_count"] = (
        pd.to_numeric(panel["team_stint_count"], errors="coerce").fillna(0).astype("Int64")
    )
    panel["traded_midseason"] = panel["team_stint_count"].gt(1)
    panel["teams"] = panel["teams"].fillna("")
    panel["team_ids"] = panel["team_ids"].fillna("")
    panel = _observation_flags(panel)
    panel["steals_plus_blocks"] = panel["steals"] + panel["blocks"]
    panel["source"] = "SportsDataverse ESPN NBA core/roster/player-box releases"
    drop = [
        "name_game",
        "name_profile",
        "role_game",
        "role_profile",
        "position_game",
        "position_profile",
    ]
    return panel.drop(columns=[column for column in drop if column in panel])


def _build_team_seasons(games: pd.DataFrame) -> pd.DataFrame:
    team = _aggregate_group(games, ["player_id", "season", "team_id", "team"])
    team = _observation_flags(team)
    team = team.sort_values(["player_id", "first_game_date", "team_id"])
    team["stint_order"] = team.groupby(["player_id", "season"]).cumcount() + 1
    team["player_id_source"] = "ESPN athlete_id"
    return team


def _prepare_crosswalk(frame: pd.DataFrame) -> pd.DataFrame:
    crosswalk = frame.copy()
    crosswalk["player_id"] = _player_ids(crosswalk["espn_athlete_id"])
    for column in ["nba_player_id", "yahoo_player_id"]:
        if column in crosswalk:
            crosswalk[column] = crosswalk[column].astype("string")
    fields = [
        "player_id",
        "nba_player_id",
        "yahoo_player_id",
        "match_method",
        "match_confidence",
    ]
    fields = [column for column in fields if column in crosswalk]
    duplicate_conflicts = (
        crosswalk.groupby("player_id")["nba_player_id"].nunique(dropna=False).gt(1)
        if "nba_player_id" in crosswalk
        else pd.Series(dtype=bool)
    )
    if duplicate_conflicts.any():
        raise ValueError("Conflicting NBA IDs in SportsDataverse crosswalk")
    return crosswalk[fields].dropna(subset=["player_id"]).drop_duplicates("player_id")


def download(root: Path, seasons: list[int]) -> dict:
    seasons = sorted(set(int(season) for season in seasons))
    raw = root / "data" / "raw" / "nba"
    tasks: list[tuple[str, Path, str, str]] = []
    for season_start in seasons:
        year_end = season_start + 1
        assets = [
            (
                "espn_nba_player_core",
                f"player_core_{year_end}.parquet",
                f"player_core_{year_end}.parquet",
                "SportsDataverse ESPN NBA player core",
            ),
            (
                "espn_nba_game_rosters",
                f"game_rosters_{year_end}.parquet",
                f"game_rosters_{year_end}.parquet",
                "SportsDataverse ESPN NBA game rosters",
            ),
            (
                "espn_nba_player_boxscores",
                f"player_box_{year_end}.parquet",
                f"player_box_{year_end}.parquet",
                "SportsDataverse ESPN NBA player box scores",
            ),
        ]
        for release, filename, local_name, source in assets:
            tasks.append(
                (
                    f"{BASE}/{release}/{filename}",
                    raw / str(year_end) / local_name,
                    source,
                    SOURCE_NOTE,
                )
            )

    failures = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(fetch, url, dest, source=source, license_note=note): dest
            for url, dest, source, note in tasks
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:  # pragma: no cover - network failure path
                failures.append({"path": str(futures[future]), "error": str(exc)})
    if failures:
        write_json(
            root / "reports" / "nba" / "download_status.json",
            {
                "expected_files": len(tasks),
                "mandatory_failures": failures,
            },
        )
        raise RuntimeError(f"NBA downloads incomplete: {failures}")

    optional_failure = None
    crosswalk_path = raw / "nba_player_crosswalk_2026.parquet"
    try:
        fetch(
            f"{BASE}/nba_crosswalk/nba_player_crosswalk_2026.parquet",
            crosswalk_path,
            source="SportsDataverse NBA crosswalk",
            license_note=CROSSWALK_NOTE,
        )
    except Exception as exc:  # pragma: no cover - optional network failure
        optional_failure = str(exc)
    status = {
        "requested_season_starts": seasons,
        "mandatory_files": len(tasks),
        "mandatory_failures": [],
        "optional_crosswalk_available": crosswalk_path.exists(),
        "optional_crosswalk_failure": optional_failure,
    }
    write_json(root / "reports" / "nba" / "download_status.json", status)
    return status


def process(root: Path, seasons: list[int]) -> pd.DataFrame:
    seasons = sorted(set(int(season) for season in seasons))
    raw = root / "data" / "raw" / "nba"
    out = root / "data" / "processed" / "nba"
    out.mkdir(parents=True, exist_ok=True)

    all_panels: list[pd.DataFrame] = []
    all_games: list[pd.DataFrame] = []
    all_team_seasons: list[pd.DataFrame] = []
    all_profiles: list[pd.DataFrame] = []
    excluded_rows: list[pd.DataFrame] = []
    unresolved_rows: list[pd.DataFrame] = []
    qa: dict = {
        "requested_season_starts": seasons,
        "season_mapping": "input/start year S maps to SportsDataverse season-ending year S+1",
        "regular_season_definition": (
            "ESPN season_type=2, NBA team IDs 1-30, exactly two NBA teams per game, "
            "with explicit NBA Cup championship exclusion"
        ),
        "seasons": {},
    }

    crosswalk_path = raw / "nba_player_crosswalk_2026.parquet"
    crosswalk = _prepare_crosswalk(read_frame(crosswalk_path)) if crosswalk_path.exists() else None

    for season_start in seasons:
        year_end = season_start + 1
        print(f"NBA processing {season_start}-{str(year_end)[-2:]}", flush=True)
        season_path = raw / str(year_end)
        core_path = season_path / f"player_core_{year_end}.parquet"
        roster_path = season_path / f"game_rosters_{year_end}.parquet"
        box_path = season_path / f"player_box_{year_end}.parquet"
        core = read_frame(core_path)
        roster_raw = read_frame(roster_path)
        box_raw = read_frame(box_path)

        regular, excluded, filter_qa = _filter_regular_box(box_raw, season_start)
        excluded["study_season"] = season_start
        excluded_rows.append(excluded)
        regular["player_id"] = _player_ids(regular["athlete_id"])
        unresolved_box = regular[regular["player_id"].isna()].copy()
        unresolved_box["unresolved_source"] = "player_box"
        regular = regular[regular["player_id"].notna()].copy()

        regular_game_ids = set(regular["game_id"].dropna().astype(str))
        roster = roster_raw.copy()
        roster["game_id"] = roster["game_id"].astype("string")
        roster = roster[roster["game_id"].isin(regular_game_ids)].copy()
        roster["team_id"] = pd.to_numeric(roster["team_id"], errors="coerce").astype("Int64")
        roster["player_id"] = _player_ids(roster["athlete_id"])
        unresolved_roster = roster[roster["player_id"].isna()].copy()
        unresolved_roster["unresolved_source"] = "game_rosters"
        unresolved = pd.concat([unresolved_box, unresolved_roster], ignore_index=True)
        unresolved["study_season"] = season_start
        unresolved_rows.append(unresolved)
        roster = roster[roster["player_id"].notna()].copy()

        key = ["game_id", "team_id", "player_id"]
        if regular.duplicated(key).any() or roster.duplicated(key).any():
            raise ValueError(f"Duplicate NBA player-game key in {year_end}")
        roster_fields = roster[
            key
            + [
                "athlete_uid",
                "athlete_guid",
                "athlete_position",
                "team_abbreviation",
            ]
        ].rename(
            columns={
                "athlete_uid": "espn_uid_roster",
                "athlete_guid": "espn_guid_roster",
                "athlete_position": "position_roster",
                "team_abbreviation": "team_roster",
            }
        )
        regular = regular.merge(
            roster_fields, on=key, how="left", validate="one_to_one", indicator="roster_join"
        )
        unmatched_roster = int(regular["roster_join"].ne("both").sum())
        regular["name"] = regular["athlete_display_name"]
        regular["position"] = regular["athlete_position_abbreviation"].combine_first(
            regular["position_roster"]
        )
        regular["role"] = regular["position"].map(map_role)
        regular["team"] = regular["team_abbreviation"].combine_first(regular["team_roster"])
        regular["season"] = season_start
        regular["season_end_year"] = year_end
        regular["game_date"] = pd.to_datetime(regular["game_date"], errors="coerce")
        regular["source_retrieved_at"] = _source_retrieved_at(box_path)
        regular = _appearance_fields(regular)

        profile = _prepare_profile(core, season_start, core_path)
        all_profiles.append(profile.assign(season=season_start))
        panel = _build_player_season(regular, profile, season_start)
        if crosswalk is not None:
            panel = panel.merge(crosswalk, on="player_id", how="left", validate="one_to_one")
            panel["nba_player_id_source"] = np.where(
                panel.get("nba_player_id", pd.Series(pd.NA, index=panel.index)).notna(),
                "SportsDataverse 2026 NBA crosswalk",
                "unavailable_in_current_crosswalk",
            )

        team_seasons = _build_team_seasons(regular)
        all_panels.append(panel)
        all_team_seasons.append(team_seasons)

        game_columns = [
            "player_id",
            "name",
            "season",
            "season_end_year",
            "game_id",
            "game_date",
            "team_id",
            "team",
            "role",
            "position",
            "opportunity",
            "minutes",
            *COUNT_COLUMNS,
            "steals",
            "blocks",
            "starter",
            "reported_dnp",
            "appearance_observed",
            "appearance_status",
            "stats_observed",
            "event_observation_status",
            "espn_uid_roster",
            "espn_guid_roster",
            "source_retrieved_at",
        ]
        # Deduplicate names in the requested list while retaining a stable order.
        game_columns = list(dict.fromkeys(column for column in game_columns if column in regular))
        games = regular[game_columns].copy()
        games["player_id_source"] = "ESPN athlete_id"
        all_games.append(games)

        game_counts = regular.groupby("team_id")["game_id"].nunique()
        regular_games = int(regular["game_id"].nunique())
        critical_checks = {
            "exactly_1230_standings_games": regular_games == 1230,
            "exactly_30_teams": int(regular["team_id"].nunique()) == 30,
            "each_team_has_82_games": bool(len(game_counts) == 30 and game_counts.eq(82).all()),
            "unique_player_game_key": not regular.duplicated(key).any(),
            "box_rows_match_roster_keys": unmatched_roster == 0,
            "unique_player_season": not panel.duplicated(["player_id", "season"]).any(),
        }
        qa["seasons"][str(season_start)] = {
            **filter_qa,
            "raw_roster_rows": int(len(roster_raw)),
            "raw_profile_rows": int(len(core)),
            "regular_season_games": regular_games,
            "regular_player_game_rows": int(len(regular)),
            "regular_players": int(regular["player_id"].nunique()),
            "panel_players": int(len(panel)),
            "profile_only_players": int(panel["profile_only_no_game_roster"].sum()),
            "zero_recorded_appearance_players": int(panel["zero_appearance_roster"].sum()),
            "unresolved_player_rows_quarantined": int(len(unresolved)),
            "box_rows_unmatched_to_roster": unmatched_roster,
            "reported_dnp_rows": int(regular["reported_dnp"].sum()),
            "missing_minute_ambiguous_rows": int(
                regular["appearance_status"].eq("missing_minutes_ambiguous").sum()
            ),
            "zero_minute_ambiguous_rows": int(regular["appearance_status"].eq("zero_minute_ambiguous").sum()),
            "team_games_min": int(game_counts.min()),
            "team_games_max": int(game_counts.max()),
            "height_coverage": float(panel["height_cm"].notna().mean()),
            "weight_coverage": float(panel["weight_kg"].notna().mean()),
            "nba_id_crosswalk_coverage": (
                float(panel["nba_player_id"].notna().mean()) if "nba_player_id" in panel else 0.0
            ),
            "critical_checks": critical_checks,
        }
        if not all(critical_checks.values()):
            raise ValueError(f"NBA {season_start} QA failed: {critical_checks}")

    player_seasons = pd.concat(all_panels, ignore_index=True)
    player_games = pd.concat(all_games, ignore_index=True)
    player_team_seasons = pd.concat(all_team_seasons, ignore_index=True)
    profiles = pd.concat(all_profiles, ignore_index=True)
    if player_seasons.duplicated(["player_id", "season"]).any():
        raise ValueError("NBA duplicated player-season after concatenation")
    if player_games.duplicated(["game_id", "team_id", "player_id"]).any():
        raise ValueError("NBA duplicated player-game after concatenation")

    save_frame(player_seasons, out / "player_seasons.parquet")
    save_frame(player_games, out / "player_games.parquet")
    save_frame(player_team_seasons, out / "player_team_seasons.parquet")
    save_frame(profiles, out / "physical_profile_snapshots.parquet")
    save_frame(pd.concat(excluded_rows, ignore_index=True), out / "excluded_non_standings_rows.parquet")
    unresolved_all = pd.concat(unresolved_rows, ignore_index=True)
    save_frame(unresolved_all, out / "unresolved_player_rows.parquet")

    variation = profiles.groupby("player_id").agg(
        height_values=("height_cm", lambda values: values.nunique(dropna=False)),
        weight_values=("weight_kg", lambda values: values.nunique(dropna=False)),
        reported_age_values=(
            "profile_reported_age_at_retrieval",
            lambda values: values.nunique(dropna=False),
        ),
    )
    qa["totals"] = {
        "player_season_rows": int(len(player_seasons)),
        "unique_players": int(player_seasons["player_id"].nunique()),
        "player_game_rows": int(len(player_games)),
        "player_team_season_rows": int(len(player_team_seasons)),
        "unresolved_rows_quarantined": int(len(unresolved_all)),
        "players_with_height_change_across_core_files": int(variation["height_values"].gt(1).sum()),
        "players_with_weight_change_across_core_files": int(variation["weight_values"].gt(1).sum()),
        "players_with_reported_age_change_across_core_files": int(
            variation["reported_age_values"].gt(1).sum()
        ),
        "physical_snapshot_interpretation": (
            "No common player's height, weight, reported age, experience, current team or status changes "
            "across year-labelled core files in this snapshot; these are current retrospective profiles, "
            "not annual measurements."
        ),
    }
    qa["all_critical_checks_passed"] = all(
        all(season_qa["critical_checks"].values()) for season_qa in qa["seasons"].values()
    )
    write_json(out / "qa.json", qa)
    write_json(root / "reports" / "nba" / "qa.json", qa)
    (out / "source_notes.md").write_text(_source_notes(seasons))
    return player_seasons


def _source_notes(seasons: list[int]) -> str:
    labels = ", ".join(f"{season}-{str(season + 1)[-2:]}" for season in seasons)
    bullets = "\n".join(f"- {item}" for item in LIMITATIONS)
    return f"""# NBA processed data: sources and limitations

## Coverage

This build covers the NBA regular seasons {labels}. Input arguments are season-start years; SportsDataverse
filenames and their `season` fields use the ending year. `player_games.parquet` retains game-roster DNP rows,
while `player_seasons.parquet` contains one row per ESPN athlete and season. Exact team/trade detail is retained
in both `player_games.parquet` and `player_team_seasons.parquet`.

## Sources

- `espn_nba_player_core`: ESPN player profile fields packaged by SportsDataverse.
- `espn_nba_game_rosters`: ESPN per-game rosters packaged by SportsDataverse.
- `espn_nba_player_boxscores`: ESPN per-game box scores packaged by SportsDataverse.
- `nba_crosswalk` (optional): current 2025-26 ID mapping packaged by SportsDataverse.

The files are public GitHub release assets. Public availability and the SportsDataverse software license do not
automatically grant rights to redistribute or commercialize underlying ESPN/NBA data. Every raw file has a
`.source.json` sidecar containing URL, source, retrieval time, hash, byte count and the rights note used here.

## Processing rules

- Regular season means ESPN `season_type=2`, official NBA team IDs 1-30, two NBA teams per game, and exclusion
  of the NBA Cup championship. The resulting audit requires 1,230 games and 82 games for every team.
- All-Star formats are removed because their team IDs are outside the 30 NBA franchises.
- DNP box statistics remain null at game level. Season totals become explicit structural zeros only for a player
  with no recorded appearance, and the observation-status fields identify that operation.
- `player_id` is the string form of ESPN `athlete_id`. The current crosswalk adds `nba_player_id` when available
  but never replaces the canonical ESPN key.
- Age is recomputed at October 1 of the season-start year from date of birth; the source's current reported age
  is retained under a clearly retrieval-time field and is not used as historical age.

## Known limitations

{bullets}
"""


def analyze(root: Path) -> dict:
    from possession_lab.analysis import analyze_sport

    panel = read_frame(root / "data" / "processed" / "nba" / "player_seasons.parquet")
    return analyze_sport(
        panel,
        "nba",
        root,
        metrics=METRICS,
        physical_features=["height_cm", "weight_kg", "age"],
        limitations=LIMITATIONS,
        opportunity_unit="ESPN whole regular-season minutes",
    )


def run(root: Path, seasons: list[int]) -> dict:
    download(root, seasons)
    process(root, seasons)
    return analyze(root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["download", "process", "analyze", "run"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--seasons", type=int, nargs="+", default=list(range(2021, 2026)))
    arguments = parser.parse_args()
    function = globals()[arguments.stage]
    if arguments.stage == "analyze":
        result = function(arguments.root)
    else:
        result = function(arguments.root, sorted(set(arguments.seasons)))
    if result is not None:
        print(result)
