"""Build the NBA all-role player-season performance panel.

The possession-focused NBA adapter intentionally retained only a small set of
box-score totals.  This module returns to the cached SportsDataverse/ESPN
player-box files so that shooting, playmaking, rebounding, defensive activity,
and plus/minus can be represented without another download.

Season values use the project's season-start convention: ``2021`` identifies
the 2021-22 NBA season and therefore reads ``player_box_2022.parquet``.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd

from possession_lab.sports.nba import (
    _appearance_fields,
    _filter_regular_box,
    _join_unique,
    _mode,
    _player_ids,
    map_role,
)

RAW_TOTAL_COLUMNS = (
    "field_goals_made",
    "field_goals_attempted",
    "three_point_field_goals_made",
    "three_point_field_goals_attempted",
    "free_throws_made",
    "free_throws_attempted",
    "points",
    "assists",
    "turnovers",
    "offensive_rebounds",
    "defensive_rebounds",
    "rebounds",
    "steals",
    "blocks",
    "fouls",
    "plus_minus",
)

RATE_COLUMNS = (
    "points_per_36",
    "true_shooting_pct",
    "effective_fg_pct",
    "three_point_pct",
    "three_point_attempt_rate",
    "free_throw_pct",
    "free_throw_attempt_rate",
    "assists_per_36",
    "assist_turnover_ratio",
    "turnovers_per_36",
    "offensive_rebounds_per_36",
    "defensive_rebounds_per_36",
    "steals_per_36",
    "blocks_per_36",
    "fouls_per_36",
    "plus_minus_per_36",
)

OUTPUT_COLUMNS = (
    "sport",
    "player_id",
    "name",
    "season",
    "position",
    "role",
    "team",
    "games",
    "games_started",
    "opportunity",
    "height_cm",
    "weight_kg",
    "age",
    *RAW_TOTAL_COLUMNS,
    *RATE_COLUMNS,
    "availability_minutes",
)

_RAW_REQUIRED = {
    "game_id",
    "season_type",
    "athlete_id",
    "athlete_display_name",
    "team_id",
    "team_abbreviation",
    "minutes",
    "starter",
    "did_not_play",
    "athlete_position_abbreviation",
    *RAW_TOTAL_COLUMNS,
}


def _safe_ratio(
    numerator: pd.Series,
    denominator: pd.Series,
    *,
    scale: float = 1.0,
) -> pd.Series:
    """Return a finite ratio only where the denominator is strictly positive."""
    top = pd.to_numeric(numerator, errors="coerce").astype(float)
    bottom = pd.to_numeric(denominator, errors="coerce").astype(float)
    valid = np.isfinite(top) & np.isfinite(bottom) & bottom.gt(0)
    result = pd.Series(np.nan, index=top.index, dtype=float)
    result.loc[valid] = scale * top.loc[valid] / bottom.loc[valid]
    return result


def _derive_rates(frame: pd.DataFrame) -> pd.DataFrame:
    """Add transparent box-score rates to aggregated player-season totals."""
    result = frame.copy()
    minutes = result["opportunity"]
    result["points_per_36"] = _safe_ratio(result["points"], minutes, scale=36.0)

    true_shooting_denominator = 2.0 * (
        result["field_goals_attempted"] + 0.44 * result["free_throws_attempted"]
    )
    result["true_shooting_pct"] = _safe_ratio(result["points"], true_shooting_denominator)
    result["effective_fg_pct"] = _safe_ratio(
        result["field_goals_made"] + 0.5 * result["three_point_field_goals_made"],
        result["field_goals_attempted"],
    )
    result["three_point_pct"] = _safe_ratio(
        result["three_point_field_goals_made"],
        result["three_point_field_goals_attempted"],
    )
    result["three_point_attempt_rate"] = _safe_ratio(
        result["three_point_field_goals_attempted"],
        result["field_goals_attempted"],
    )
    result["free_throw_pct"] = _safe_ratio(
        result["free_throws_made"], result["free_throws_attempted"]
    )
    result["free_throw_attempt_rate"] = _safe_ratio(
        result["free_throws_attempted"], result["field_goals_attempted"]
    )
    result["assists_per_36"] = _safe_ratio(result["assists"], minutes, scale=36.0)
    result["assist_turnover_ratio"] = _safe_ratio(result["assists"], result["turnovers"])
    result["turnovers_per_36"] = _safe_ratio(result["turnovers"], minutes, scale=36.0)
    result["offensive_rebounds_per_36"] = _safe_ratio(
        result["offensive_rebounds"], minutes, scale=36.0
    )
    result["defensive_rebounds_per_36"] = _safe_ratio(
        result["defensive_rebounds"], minutes, scale=36.0
    )
    result["steals_per_36"] = _safe_ratio(result["steals"], minutes, scale=36.0)
    result["blocks_per_36"] = _safe_ratio(result["blocks"], minutes, scale=36.0)
    result["fouls_per_36"] = _safe_ratio(result["fouls"], minutes, scale=36.0)
    result["plus_minus_per_36"] = _safe_ratio(result["plus_minus"], minutes, scale=36.0)
    result["availability_minutes"] = pd.to_numeric(minutes, errors="coerce")
    return result


def _strict_totals(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    """Aggregate totals without presenting a partial season as complete.

    A total is null when any confirmed appearance is missing that field.  The
    source files are normally complete, but this rule makes missingness honest
    for damaged caches and small synthetic fixtures.
    """
    grouped = frame.groupby("player_id", sort=False, dropna=False)
    numeric = frame.loc[:, columns].apply(pd.to_numeric, errors="coerce")
    totals = numeric.groupby(frame["player_id"], sort=False, dropna=False).sum(min_count=1)
    observed = numeric.notna().groupby(frame["player_id"], sort=False, dropna=False).sum()
    expected = grouped.size()
    totals = totals.mask(observed.ne(expected, axis=0))
    totals.index.name = "player_id"
    return totals


def _aggregate_played_rows(frame: pd.DataFrame, season: int) -> pd.DataFrame:
    """Collapse confirmed regular-season appearances to one player-season."""
    if frame.empty:
        return pd.DataFrame(columns=["player_id", "season"])
    grouped = frame.groupby("player_id", sort=False, dropna=False)
    base = grouped.agg(
        raw_name=("athlete_display_name", _mode),
        raw_position=("athlete_position_abbreviation", _mode),
        raw_team=("team_abbreviation", _join_unique),
        games=("game_id", "nunique"),
        games_started=("starter", lambda values: int(values.fillna(False).astype(bool).sum())),
        opportunity=("minutes", lambda values: pd.to_numeric(values, errors="coerce").sum(min_count=1)),
    )
    totals = _strict_totals(frame, RAW_TOTAL_COLUMNS)
    result = base.join(totals).reset_index()
    result["season"] = int(season)
    result["games"] = pd.to_numeric(result["games"], errors="raise").astype("Int64")
    result["games_started"] = pd.to_numeric(
        result["games_started"], errors="raise"
    ).astype("Int64")
    return _derive_rates(result)


def _canonical_profiles(processed: pd.DataFrame, seasons: set[int]) -> pd.DataFrame:
    required = {
        "player_id",
        "name",
        "season",
        "position",
        "role",
        "height_cm",
        "weight_kg",
        "age",
    }
    missing = sorted(required.difference(processed.columns))
    if missing:
        raise ValueError(f"Processed NBA player_seasons is missing columns: {missing}")
    canonical = processed.copy()
    canonical["season"] = pd.to_numeric(canonical["season"], errors="raise").astype(int)
    canonical = canonical.loc[canonical["season"].isin(seasons)].copy()
    canonical["player_id"] = canonical["player_id"].astype("string")
    if canonical.duplicated(["player_id", "season"]).any():
        raise ValueError("Processed NBA panel has duplicate player-season identities")
    if "teams" in canonical:
        canonical["canonical_team"] = canonical["teams"]
    elif "team" in canonical:
        canonical["canonical_team"] = canonical["team"]
    else:
        canonical["canonical_team"] = pd.NA
    return canonical[
        [
            "player_id",
            "season",
            "name",
            "position",
            "role",
            "canonical_team",
            "height_cm",
            "weight_kg",
            "age",
        ]
    ]


def build_nba_all_roles_panel(
    root: Path,
    seasons: Iterable[int] = range(2021, 2026),
) -> pd.DataFrame:
    """Return one all-role NBA row per confirmed player-season.

    The existing adapter's standings-game filter and confirmed-appearance rule
    are reused verbatim.  Processed ``player_seasons`` supplies canonical ESPN
    IDs, names, broad roles, and physical descriptors; the raw box files supply
    the expanded performance totals.
    """
    root = Path(root)
    requested = sorted({int(season) for season in seasons})
    if not requested:
        raise ValueError("At least one NBA season is required")

    processed_path = root / "data" / "processed" / "nba" / "player_seasons.parquet"
    if not processed_path.exists():
        raise FileNotFoundError(f"Processed NBA player seasons not found: {processed_path}")
    canonical = _canonical_profiles(pd.read_parquet(processed_path), set(requested))

    annual: list[pd.DataFrame] = []
    for season in requested:
        ending_year = season + 1
        path = (
            root
            / "data"
            / "raw"
            / "nba"
            / str(ending_year)
            / f"player_box_{ending_year}.parquet"
        )
        if not path.exists():
            raise FileNotFoundError(f"Cached NBA player box file not found: {path}")
        raw = pd.read_parquet(path)
        missing = sorted(_RAW_REQUIRED.difference(raw.columns))
        if missing:
            raise ValueError(f"NBA player box {ending_year} is missing columns: {missing}")

        regular, _, _ = _filter_regular_box(raw, season)
        regular["player_id"] = _player_ids(regular["athlete_id"])
        regular = regular.loc[regular["player_id"].notna()].copy()
        key = ["game_id", "team_id", "player_id"]
        if regular.duplicated(key).any():
            raise ValueError(f"Duplicate NBA player-game key in {ending_year}")
        regular["minutes"] = pd.to_numeric(regular["minutes"], errors="coerce")
        regular["plus_minus"] = pd.to_numeric(regular["plus_minus"], errors="coerce")
        regular = _appearance_fields(regular)
        played = regular.loc[regular["appearance_observed"]].copy()
        annual.append(_aggregate_played_rows(played, season))

    performance = pd.concat(annual, ignore_index=True)
    if performance.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    if performance.duplicated(["player_id", "season"]).any():
        raise ValueError("NBA all-role aggregation produced duplicate player-seasons")
    panel = performance.merge(
        canonical,
        on=["player_id", "season"],
        how="left",
        validate="one_to_one",
        indicator=True,
        suffixes=("", "_canonical"),
    )
    unmatched = panel["_merge"].ne("both")
    if unmatched.any():
        identities = panel.loc[unmatched, ["player_id", "season"]].to_dict("records")
        raise ValueError(f"Raw NBA appearances lack canonical processed identities: {identities[:10]}")

    panel["sport"] = "nba"
    panel["name"] = panel["name"].combine_first(panel["raw_name"])
    panel["position"] = panel["position"].combine_first(panel["raw_position"])
    panel["team"] = panel["canonical_team"].where(
        panel["canonical_team"].notna() & panel["canonical_team"].astype(str).ne(""),
        panel["raw_team"],
    )
    mapped_role = panel["position"].map(map_role)
    panel["role"] = panel["role"].where(
        panel["role"].isin({"guard", "forward", "center"}), mapped_role
    )
    panel = panel.drop(
        columns=["raw_name", "raw_position", "raw_team", "canonical_team", "_merge"]
    )
    panel = panel.loc[:, OUTPUT_COLUMNS].sort_values(["season", "player_id"]).reset_index(drop=True)
    return panel
