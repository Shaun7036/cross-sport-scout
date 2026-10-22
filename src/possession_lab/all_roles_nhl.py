"""Build the NHL all-role player-season performance panel.

Skater outcomes come from the cached MoneyPuck season-summary files.  Only the
``all`` situation is used: it already includes even-strength and special-teams
minutes, so situation rows must never be added together.  Goalie summaries are
optional because they were not part of the original possession-only cache.

MoneyPuck records ``icetime`` in seconds.  ``opportunity`` and every per-60
metric in this module therefore use ``icetime / 60`` minutes.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from possession_lab.io import fetch, read_frame
from possession_lab.sports.nhl import MONEYPUCK_LICENSE, PHYSICAL_TEMPORALITY

MONEYPUCK_GOALIE_URL = (
    "https://www.moneypuck.com/moneypuck/playerData/seasonSummary/"
    "{season}/regular/goalies.csv"
)

SKATER_SOURCE_COLUMNS = {
    "goals": "I_F_goals",
    "expected_goals": "I_F_xGoals",
    "primary_assists": "I_F_primaryAssists",
    "secondary_assists": "I_F_secondaryAssists",
    "giveaways": "I_F_giveaways",
    "takeaways": "I_F_takeaways",
    "blocks": "shotsBlockedByPlayer",
    "hits": "I_F_hits",
}

SKATER_OPTIONAL_SOURCE_COLUMNS = {
    "shots_on_goal": "I_F_shotsOnGoal",
    "shot_attempts": "I_F_shotAttempts",
    "high_danger_shots": "I_F_highDangerShots",
    "faceoffs_won": "faceoffsWon",
    "faceoffs_lost": "faceoffsLost",
    "penalties_taken": "penalties",
    "penalties_drawn": "penaltiesDrawn",
}

SKATER_RATE_COLUMNS = {
    "goals": "goals_per_60",
    "expected_goals": "expected_goals_per_60",
    "primary_assists": "primary_assists_per_60",
    "secondary_assists": "secondary_assists_per_60",
    "giveaways": "giveaways_per_60",
    "takeaways": "takeaways_per_60",
    "blocks": "blocks_per_60",
    "hits": "hits_per_60",
    "shots_on_goal": "shots_on_goal_per_60",
    "shot_attempts": "shot_attempts_per_60",
    "high_danger_shots": "high_danger_shots_per_60",
    "penalties_taken": "penalties_taken_per_60",
    "penalties_drawn": "penalties_drawn_per_60",
}

GOALIE_SOURCE_COLUMNS = {
    "expected_goals_against": "xGoals",
    "goals_against": "goals",
    "shots_on_goal_against": "ongoal",
    "high_danger_shots_against": "highDangerShots",
    "high_danger_goals_against": "highDangerGoals",
    "rebounds_allowed": "rebounds",
}

SKATER_ROLES = {
    "C": "center",
    "L": "left_wing",
    "LW": "left_wing",
    "R": "right_wing",
    "RW": "right_wing",
    "D": "defense",
}

OUTPUT_COLUMNS = (
    "sport",
    "player_id",
    "name",
    "season",
    "position",
    "role",
    "team",
    "games",
    "opportunity",
    "height_cm",
    "weight_kg",
    "age",
    "birth_date",
    "nationality",
    "shoots_catches",
    *SKATER_SOURCE_COLUMNS,
    *SKATER_OPTIONAL_SOURCE_COLUMNS,
    *SKATER_RATE_COLUMNS.values(),
    "takeaway_giveaway_ratio",
    "faceoff_win_pct",
    "penalty_differential_per_60",
    "on_ice_xgoal_pct",
    "relative_xgoal_pct",
    "on_ice_corsi_pct",
    "relative_corsi_pct",
    *GOALIE_SOURCE_COLUMNS,
    "save_pct",
    "high_danger_save_pct",
    "goals_saved_above_expected",
    "goals_saved_above_expected_per_60",
    "rebound_rate",
    "rebound_goals_against_rate",
    "availability_minutes",
    "physical_source",
    "physical_measurement_scope",
    "physical_is_confirmed_season_measurement",
    "source",
    "source_grain",
    "coverage_scope",
    "license_note",
)

_TOTAL_TEAM_LABELS = {"TOT", "TOTAL", "ALL"}


def _clean_id(values: pd.Series) -> pd.Series:
    result = values.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    return result.mask(result.isin(["", "nan", "None", "<NA>"]))


def _safe_ratio(
    numerator: pd.Series,
    denominator: pd.Series,
    *,
    scale: float = 1.0,
) -> pd.Series:
    top = pd.to_numeric(numerator, errors="coerce").astype(float)
    bottom = pd.to_numeric(denominator, errors="coerce").astype(float)
    valid = np.isfinite(top) & np.isfinite(bottom) & bottom.gt(0)
    result = pd.Series(np.nan, index=top.index, dtype=float)
    result.loc[valid] = scale * top.loc[valid] / bottom.loc[valid]
    return result


def _parse_height_cm(value: Any) -> float:
    if value is None or pd.isna(value):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        return number * 2.54 if 48 <= number <= 96 else np.nan
    text = str(value).strip()
    match = re.fullmatch(r"(\d+)\s*['′]\s*(\d+)\s*(?:[\"″])?", text)
    if match:
        return (int(match.group(1)) * 12 + int(match.group(2))) * 2.54
    match = re.fullmatch(r"(\d+)\s*[- ]\s*(\d+)", text)
    if match and int(match.group(1)) < 9:
        return (int(match.group(1)) * 12 + int(match.group(2))) * 2.54
    try:
        number = float(text)
    except ValueError:
        return np.nan
    return number * 2.54 if 48 <= number <= 96 else np.nan


def _age_on_october_first(birth_dates: pd.Series, seasons: pd.Series) -> pd.Series:
    births = pd.to_datetime(birth_dates, errors="coerce")
    years = pd.to_numeric(seasons, errors="coerce").astype("Int64")
    result = pd.Series(pd.NA, index=birth_dates.index, dtype="Int64")
    valid = births.notna() & years.notna()
    if valid.any():
        birthdays_passed = (births[valid].dt.month < 10) | (
            (births[valid].dt.month == 10) & (births[valid].dt.day <= 1)
        )
        result.loc[valid] = (
            years[valid] - births[valid].dt.year - (~birthdays_passed).astype(int)
        ).astype("Int64")
    return result


def _requested_seasons(seasons: Iterable[int]) -> list[int]:
    requested = sorted({int(season) for season in seasons})
    if not requested:
        raise ValueError("At least one NHL season is required")
    return requested


def fetch_nhl_goalie_sources(
    root: Path,
    seasons: Iterable[int] = range(2021, 2026),
) -> dict[int, Path]:
    """Fetch designated MoneyPuck goalie summaries into the normal raw cache.

    This helper is intentionally separate from :func:`build_nhl_all_roles_panel`.
    Building a panel never performs network IO; callers opt into acquisition.
    """
    root = Path(root)
    raw = root / "data" / "raw" / "nhl"
    return {
        season: fetch(
            MONEYPUCK_GOALIE_URL.format(season=season),
            raw / f"moneypuck_goalies_{season}_regular.csv",
            source="MoneyPuck regular-season goalie season summary designated download",
            license_note=MONEYPUCK_LICENSE,
            timeout=180,
        )
        for season in _requested_seasons(seasons)
    }


def _joined_teams(group: pd.DataFrame) -> Any:
    values = group["team"].dropna().astype(str).str.strip()
    actual = sorted({value for value in values if value and value.upper() not in _TOTAL_TEAM_LABELS})
    if actual:
        return ";".join(actual)
    fallback = sorted({value for value in values if value})
    return ";".join(fallback) if fallback else pd.NA


def _aggregate_player_seasons(
    frame: pd.DataFrame,
    *,
    total_columns: tuple[str, ...],
    weighted_columns: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Collapse team stints, preferring a provider-supplied total when present."""
    records: list[dict[str, Any]] = []
    for (player_id, season), original in frame.groupby(
        ["player_id", "season"], sort=False, dropna=False
    ):
        team_upper = original["team"].astype("string").str.upper()
        total_rows = original.loc[team_upper.isin(_TOTAL_TEAM_LABELS)]
        if len(total_rows) > 1:
            raise ValueError(f"Multiple NHL total rows for player {player_id}, season {season}")
        if total_rows.empty:
            actual_teams = team_upper.loc[~team_upper.isin(_TOTAL_TEAM_LABELS)]
            if actual_teams.duplicated().any():
                raise ValueError(
                    f"Duplicate NHL team rows for player {player_id}, season {season}"
                )
            selected = original
        else:
            selected = total_rows

        ice = pd.to_numeric(selected["icetime"], errors="coerce")
        dominant = selected.assign(_ice=ice).sort_values(
            "_ice", ascending=False, na_position="last"
        ).iloc[0]
        row: dict[str, Any] = {
            "player_id": player_id,
            "season": int(season),
            "name": dominant["name"],
            "position": dominant["position"],
            "team": _joined_teams(original),
        }
        for column in total_columns:
            values = pd.to_numeric(selected[column], errors="coerce")
            row[column] = values.sum() if values.notna().all() else np.nan
        for column in weighted_columns:
            values = pd.to_numeric(selected[column], errors="coerce")
            valid = values.notna() & ice.notna() & ice.gt(0)
            row[column] = (
                float(np.average(values.loc[valid], weights=ice.loc[valid]))
                if valid.all() and valid.any()
                else np.nan
            )
        records.append(row)
    return pd.DataFrame.from_records(records)


def _normalise_skater_source(raw: pd.DataFrame, season: int) -> pd.DataFrame:
    required = {
        "playerId",
        "season",
        "name",
        "team",
        "position",
        "situation",
        "games_played",
        "icetime",
        "onIce_xGoalsPercentage",
        "offIce_xGoalsPercentage",
        *SKATER_SOURCE_COLUMNS.values(),
    }
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise ValueError(f"MoneyPuck skater summary {season} is missing columns: {missing}")

    source_season = pd.to_numeric(raw["season"], errors="coerce")
    keep = raw["situation"].astype("string").str.lower().eq("all") & source_season.eq(season)
    selected = raw.loc[keep].copy()
    normalised = pd.DataFrame(
        {
            "player_id": _clean_id(selected["playerId"]),
            "season": source_season.loc[keep].astype("Int64"),
            "name": selected["name"].astype("string"),
            "team": selected["team"].astype("string"),
            "position": selected["position"].astype("string").str.upper(),
            "games": pd.to_numeric(selected["games_played"], errors="coerce"),
            "icetime": pd.to_numeric(selected["icetime"], errors="coerce"),
            "on_ice_xgoal_pct": pd.to_numeric(
                selected["onIce_xGoalsPercentage"], errors="coerce"
            ),
            "off_ice_xgoal_pct": pd.to_numeric(
                selected["offIce_xGoalsPercentage"], errors="coerce"
            ),
        }
    )
    for canonical, source in SKATER_SOURCE_COLUMNS.items():
        normalised[canonical] = pd.to_numeric(selected[source], errors="coerce")
    for canonical, source in SKATER_OPTIONAL_SOURCE_COLUMNS.items():
        normalised[canonical] = (
            pd.to_numeric(selected[source], errors="coerce")
            if source in selected
            else np.nan
        )
    normalised["on_ice_corsi_pct"] = (
        pd.to_numeric(selected["onIce_corsiPercentage"], errors="coerce")
        if "onIce_corsiPercentage" in selected
        else np.nan
    )
    normalised["off_ice_corsi_pct"] = (
        pd.to_numeric(selected["offIce_corsiPercentage"], errors="coerce")
        if "offIce_corsiPercentage" in selected
        else np.nan
    )
    return normalised.loc[normalised["player_id"].notna()].copy()


def _derive_skater_rates(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["opportunity"] = pd.to_numeric(result["icetime"], errors="coerce") / 60.0
    for total, rate in SKATER_RATE_COLUMNS.items():
        result[rate] = _safe_ratio(result[total], result["opportunity"], scale=60.0)
    result["takeaway_giveaway_ratio"] = _safe_ratio(
        result["takeaways"], result["giveaways"]
    )
    result["faceoff_win_pct"] = _safe_ratio(
        result["faceoffs_won"], result["faceoffs_won"] + result["faceoffs_lost"]
    )
    result["penalty_differential_per_60"] = _safe_ratio(
        result["penalties_drawn"] - result["penalties_taken"],
        result["opportunity"],
        scale=60.0,
    )
    result["relative_xgoal_pct"] = (
        pd.to_numeric(result["on_ice_xgoal_pct"], errors="coerce")
        - pd.to_numeric(result["off_ice_xgoal_pct"], errors="coerce")
    )
    result["relative_corsi_pct"] = (
        pd.to_numeric(result["on_ice_corsi_pct"], errors="coerce")
        - pd.to_numeric(result["off_ice_corsi_pct"], errors="coerce")
    )
    result["availability_minutes"] = result["opportunity"]
    return result


def _build_skater_season(raw: pd.DataFrame, season: int) -> pd.DataFrame:
    normalised = _normalise_skater_source(raw, season)
    panel = _aggregate_player_seasons(
        normalised,
        total_columns=(
            "games",
            "icetime",
            *SKATER_SOURCE_COLUMNS,
            *SKATER_OPTIONAL_SOURCE_COLUMNS,
        ),
        weighted_columns=(
            "on_ice_xgoal_pct",
            "off_ice_xgoal_pct",
            "on_ice_corsi_pct",
            "off_ice_corsi_pct",
        ),
    )
    if panel.empty:
        return panel
    panel["role"] = panel["position"].map(SKATER_ROLES)
    unsupported = panel["role"].isna()
    if unsupported.any():
        warnings.warn(
            f"Omitting {int(unsupported.sum())} NHL skater rows with unsupported positions",
            RuntimeWarning,
            stacklevel=2,
        )
        panel = panel.loc[~unsupported].copy()
    panel = _derive_skater_rates(panel)
    panel["sport"] = "nhl"
    panel["source"] = "MoneyPuck designated skater season summaries"
    panel["source_grain"] = "one row per appearing skater regular season"
    panel["coverage_scope"] = "appearance-based NHL regular-season skaters; all situations"
    panel["license_note"] = MONEYPUCK_LICENSE
    return panel


def _normalise_goalie_source(raw: pd.DataFrame, season: int) -> pd.DataFrame:
    required = {
        "playerId",
        "season",
        "name",
        "team",
        "situation",
        "games_played",
        "icetime",
        *GOALIE_SOURCE_COLUMNS.values(),
    }
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise ValueError(f"MoneyPuck goalie summary {season} is missing columns: {missing}")
    source_season = pd.to_numeric(raw["season"], errors="coerce")
    keep = raw["situation"].astype("string").str.lower().eq("all") & source_season.eq(season)
    selected = raw.loc[keep].copy()
    normalised = pd.DataFrame(
        {
            "player_id": _clean_id(selected["playerId"]),
            "season": source_season.loc[keep].astype("Int64"),
            "name": selected["name"].astype("string"),
            "team": selected["team"].astype("string"),
            "position": "G",
            "games": pd.to_numeric(selected["games_played"], errors="coerce"),
            "icetime": pd.to_numeric(selected["icetime"], errors="coerce"),
        }
    )
    for canonical, source in GOALIE_SOURCE_COLUMNS.items():
        normalised[canonical] = pd.to_numeric(selected[source], errors="coerce")
    return normalised.loc[normalised["player_id"].notna()].copy()


def _derive_goalie_rates(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["opportunity"] = pd.to_numeric(result["icetime"], errors="coerce") / 60.0
    result["save_pct"] = 1.0 - _safe_ratio(
        result["goals_against"], result["shots_on_goal_against"]
    )
    result["high_danger_save_pct"] = 1.0 - _safe_ratio(
        result["high_danger_goals_against"], result["high_danger_shots_against"]
    )
    result["goals_saved_above_expected"] = (
        result["expected_goals_against"] - result["goals_against"]
    )
    result["goals_saved_above_expected_per_60"] = _safe_ratio(
        result["goals_saved_above_expected"], result["opportunity"], scale=60.0
    )

    # MoneyPuck's designated goalie summary has actual rebounds, but no
    # rebound-goal column.  The defensible available measure is rebounds per
    # non-goal shot on goal (a save).  Keep the clearer name and the registry's
    # legacy column name as identical aliases; do not fabricate rebound goals.
    saves = result["shots_on_goal_against"] - result["goals_against"]
    result["rebound_rate"] = _safe_ratio(result["rebounds_allowed"], saves)
    result["rebound_goals_against_rate"] = result["rebound_rate"]
    result["availability_minutes"] = result["opportunity"]
    return result


def _build_goalie_season(raw: pd.DataFrame, season: int) -> pd.DataFrame:
    normalised = _normalise_goalie_source(raw, season)
    panel = _aggregate_player_seasons(
        normalised,
        total_columns=("games", "icetime", *GOALIE_SOURCE_COLUMNS),
    )
    if panel.empty:
        return panel
    panel = _derive_goalie_rates(panel)
    panel["role"] = "goalie"
    panel["position"] = "G"
    panel["sport"] = "nhl"
    panel["source"] = "MoneyPuck designated goalie season summaries"
    panel["source_grain"] = "one row per appearing goalie regular season"
    panel["coverage_scope"] = "appearance-based NHL regular-season goalies; all situations"
    panel["license_note"] = MONEYPUCK_LICENSE
    return panel


def _season_profiles(root: Path) -> pd.DataFrame:
    path = root / "data" / "processed" / "nhl" / "player_seasons.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["player_id", "season"])
    source = read_frame(path)
    required = {"player_id", "season"}
    missing = sorted(required.difference(source.columns))
    if missing:
        raise ValueError(f"Processed NHL player seasons is missing columns: {missing}")
    result = source.copy()
    result["player_id"] = _clean_id(result["player_id"])
    result["season"] = pd.to_numeric(result["season"], errors="coerce").astype("Int64")
    result = result.dropna(subset=["player_id", "season"])
    if result.duplicated(["player_id", "season"]).any():
        raise ValueError("Processed NHL player seasons has duplicate player-season identities")
    columns = [
        "player_id",
        "season",
        "height_cm",
        "weight_kg",
        "age",
        "birth_date",
        "nationality",
        "shoots_catches",
        "physical_source",
        "physical_measurement_scope",
    ]
    for column in columns:
        if column not in result:
            result[column] = pd.NA
    return result[columns]


def _latest_profiles(root: Path) -> pd.DataFrame:
    processed = root / "data" / "processed" / "nhl" / "latest_player_bios.parquet"
    raw = root / "data" / "raw" / "nhl" / "moneypuck_all_players_lookup.csv"
    if processed.exists():
        source = read_frame(processed)
        required = {"player_id"}
        missing = sorted(required.difference(source.columns))
        if missing:
            raise ValueError(f"NHL latest-player lookup is missing columns: {missing}")
        result = pd.DataFrame(
            {
                "player_id": _clean_id(source["player_id"]),
                "height_cm": pd.to_numeric(
                    source.get("height_cm_latest_profile"), errors="coerce"
                ),
                "weight_kg": pd.to_numeric(
                    source.get("weight_kg_latest_profile"), errors="coerce"
                ),
                "birth_date": pd.to_datetime(
                    source.get("birth_date_latest_profile"), errors="coerce"
                ),
                "nationality": source.get("nationality", pd.Series(pd.NA, index=source.index)),
                "shoots_catches": source.get(
                    "shoots_catches", pd.Series(pd.NA, index=source.index)
                ),
                "physical_measurement_scope": source.get(
                    "profile_temporality", pd.Series(pd.NA, index=source.index)
                ),
            }
        )
    elif raw.exists():
        source = read_frame(raw)
        required = {"playerId", "birthDate"}
        missing = sorted(required.difference(source.columns))
        if missing:
            raise ValueError(f"MoneyPuck player lookup is missing columns: {missing}")
        result = pd.DataFrame(
            {
                "player_id": _clean_id(source["playerId"]),
                "height_cm": source.get("height", pd.Series(pd.NA, index=source.index)).map(
                    _parse_height_cm
                ),
                "weight_kg": pd.to_numeric(source.get("weight"), errors="coerce")
                * 0.45359237,
                "birth_date": pd.to_datetime(source["birthDate"], errors="coerce"),
                "nationality": source.get("nationality", pd.Series(pd.NA, index=source.index)),
                "shoots_catches": source.get(
                    "shootsCatches", pd.Series(pd.NA, index=source.index)
                ),
                "physical_measurement_scope": "current/undated MoneyPuck lookup; not season history",
            }
        )
    else:
        return pd.DataFrame(columns=["player_id"])
    return result.dropna(subset=["player_id"]).drop_duplicates("player_id", keep="last")


def _attach_physical_profiles(panel: pd.DataFrame, root: Path) -> pd.DataFrame:
    result = panel.copy()
    seasonal = _season_profiles(root).rename(
        columns={
            column: f"season_profile_{column}"
            for column in [
                "height_cm",
                "weight_kg",
                "age",
                "birth_date",
                "nationality",
                "shoots_catches",
                "physical_source",
                "physical_measurement_scope",
            ]
        }
    )
    seasonal["season_profile_matched"] = True
    result = result.merge(
        seasonal,
        on=["player_id", "season"],
        how="left",
        validate="many_to_one",
    )

    latest = _latest_profiles(root).rename(
        columns={
            column: f"latest_profile_{column}"
            for column in [
                "height_cm",
                "weight_kg",
                "birth_date",
                "nationality",
                "shoots_catches",
                "physical_measurement_scope",
            ]
        }
    )
    latest["latest_profile_matched"] = True
    result = result.merge(latest, on="player_id", how="left", validate="many_to_one")

    def values(column: str, prefix: str) -> pd.Series:
        key = f"{prefix}_profile_{column}"
        return result[key] if key in result else pd.Series(pd.NA, index=result.index)

    for column in ["height_cm", "weight_kg", "birth_date", "nationality", "shoots_catches"]:
        season_values = values(column, "season")
        result[column] = season_values.where(season_values.notna(), values(column, "latest"))
    latest_age = _age_on_october_first(values("birth_date", "latest"), result["season"])
    season_age = values("age", "season")
    result["age"] = season_age.where(season_age.notna(), latest_age)

    seasonal_matched = result.get(
        "season_profile_matched", pd.Series(False, index=result.index)
    ).astype("boolean").fillna(False)
    latest_matched = result.get(
        "latest_profile_matched", pd.Series(False, index=result.index)
    ).astype("boolean").fillna(False)
    season_source = values("physical_source", "season").fillna(
        "NHL season-filtered profile; measurement date unavailable"
    )
    result["physical_source"] = pd.Series(pd.NA, index=result.index, dtype="object")
    result.loc[seasonal_matched, "physical_source"] = season_source.loc[seasonal_matched]
    result.loc[~seasonal_matched & latest_matched, "physical_source"] = (
        "MoneyPuck current/undated player lookup"
    )
    season_scope = values("physical_measurement_scope", "season").fillna(PHYSICAL_TEMPORALITY)
    latest_scope = values("physical_measurement_scope", "latest").fillna(
        "current/undated MoneyPuck lookup; not season history"
    )
    result["physical_measurement_scope"] = pd.Series(
        pd.NA, index=result.index, dtype="object"
    )
    result.loc[seasonal_matched, "physical_measurement_scope"] = season_scope.loc[
        seasonal_matched
    ]
    result.loc[~seasonal_matched & latest_matched, "physical_measurement_scope"] = (
        latest_scope.loc[~seasonal_matched & latest_matched]
    )
    result["physical_is_confirmed_season_measurement"] = False
    result["age_anchor"] = result["season"].astype("Int64").astype("string") + "-10-01"
    drop = [
        column
        for column in result
        if column.startswith("season_profile_") or column.startswith("latest_profile_")
    ]
    return result.drop(columns=drop)


def build_nhl_all_roles_panel(
    root: Path,
    seasons: Iterable[int] = range(2021, 2026),
) -> pd.DataFrame:
    """Return one NHL row per appearing player-season across all supported roles.

    Skater caches are required.  Missing goalie caches are reported through a
    warning and ``DataFrame.attrs['goalie_coverage']``; they never cause skater
    coverage to be discarded and never trigger an implicit download.
    """
    root = Path(root)
    requested = _requested_seasons(seasons)
    raw_dir = root / "data" / "raw" / "nhl"

    skaters: list[pd.DataFrame] = []
    for season in requested:
        path = raw_dir / f"moneypuck_skaters_{season}_regular.csv"
        if not path.exists():
            raise FileNotFoundError(f"Cached NHL skater summary not found: {path}")
        skaters.append(_build_skater_season(read_frame(path), season))

    goalies: list[pd.DataFrame] = []
    goalie_available: list[int] = []
    goalie_missing: list[int] = []
    for season in requested:
        path = raw_dir / f"moneypuck_goalies_{season}_regular.csv"
        if not path.exists():
            goalie_missing.append(season)
            continue
        goalies.append(_build_goalie_season(read_frame(path), season))
        goalie_available.append(season)
    if goalie_missing:
        warnings.warn(
            "NHL goalie summaries are not cached for seasons "
            f"{goalie_missing}; the panel omits those goalie-seasons. "
            "Call fetch_nhl_goalie_sources explicitly to acquire them.",
            RuntimeWarning,
            stacklevel=2,
        )

    pieces = [piece for piece in [*skaters, *goalies] if not piece.empty]
    if not pieces:
        result = pd.DataFrame(columns=OUTPUT_COLUMNS)
    else:
        result = pd.concat(pieces, ignore_index=True, sort=False)
        if result.duplicated(["player_id", "season"]).any():
            raise ValueError("NHL all-role aggregation produced duplicate player-seasons")
        result = _attach_physical_profiles(result, root)
        result["games"] = pd.to_numeric(result["games"], errors="coerce").astype("Int64")
        result = result.reindex(columns=OUTPUT_COLUMNS)
        result = result.sort_values(["season", "player_id"]).reset_index(drop=True)

    result.attrs["goalie_coverage"] = {
        "requested_seasons": requested,
        "available_seasons": goalie_available,
        "missing_seasons": goalie_missing,
        "status": "complete" if not goalie_missing else "partial_or_absent",
    }
    return result
