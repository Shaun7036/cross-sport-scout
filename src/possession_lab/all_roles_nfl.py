"""Build the NFL all-role player-season performance panel.

The panel deliberately separates three observation systems:

* nflverse weekly player statistics for offensive skill roles, kickers, and
  punters;
* the existing participation-aligned defensive counts in
  ``all_rostered_player_seasons.parquet``; and
* nflverse weekly rosters for season-wide role identity and roster visibility.

Conditional PFR-derived snap counts are intentionally not loaded.  Offensive
line and long-snapper identities remain in the panel, but they abstain from an
individual performance label until a release-safe source is available.

Missing source rows remain missing.  A zero is inferred only within a source
whose complete event universe is observed; weekly stat rows contain enumerated
totals.  No snap-derived zero or exposure is inferred for offensive linemen or
long snappers.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

CANONICAL_ROLES = frozenset(
    {"QB", "RB_FB", "WR", "TE", "OT", "IOL", "EDGE", "IDL", "LB", "CB", "S", "K", "P", "LS"}
)
DEFENSIVE_ROLES = frozenset({"EDGE", "IDL", "LB", "CB", "S"})
RECEIVING_ROLES = frozenset({"WR", "TE"})
OFFENSIVE_LINE_ROLES = frozenset({"OT", "IOL"})

_POSITION_ROLE_MAP = {
    "QB": "QB",
    "RB": "RB_FB",
    "HB": "RB_FB",
    "FB": "RB_FB",
    "WR": "WR",
    "TE": "TE",
    "T": "OT",
    "OT": "OT",
    "LT": "OT",
    "RT": "OT",
    "G": "IOL",
    "LG": "IOL",
    "RG": "IOL",
    "C": "IOL",
    "OC": "IOL",
    "IOL": "IOL",
    "DE": "EDGE",
    "EDGE": "EDGE",
    "OLB": "EDGE",
    "DT": "IDL",
    "NT": "IDL",
    "IDL": "IDL",
    "LB": "LB",
    "ILB": "LB",
    "MLB": "LB",
    "WLB": "LB",
    "SLB": "LB",
    "CB": "CB",
    "LCB": "CB",
    "RCB": "CB",
    "NB": "CB",
    "S": "S",
    "FS": "S",
    "SS": "S",
    "SAF": "S",
    "K": "K",
    "PK": "K",
    "P": "P",
    "LS": "LS",
}


WEEKLY_TOTAL_COLUMNS = (
    "completions",
    "attempts",
    "passing_yards",
    "passing_tds",
    "passing_interceptions",
    "sacks_suffered",
    "sack_fumbles_lost",
    "passing_air_yards",
    "passing_first_downs",
    "passing_epa",
    "carries",
    "rushing_yards",
    "rushing_tds",
    "rushing_fumbles_lost",
    "rushing_first_downs",
    "rushing_epa",
    "receptions",
    "targets",
    "receiving_yards",
    "receiving_tds",
    "receiving_fumbles_lost",
    "receiving_yards_after_catch",
    "receiving_first_downs",
    "receiving_epa",
    "fg_made",
    "fg_att",
    "fg_made_50_59",
    "fg_made_60_",
    "pat_made",
    "pat_att",
    "pt_att",
    "pt_blocked",
    "pt_inside_20",
    "pt_touchback",
    "pt_net_yards",
)

DEFENSIVE_TOTAL_COLUMNS = (
    "sacks",
    "qb_hits",
    "interceptions",
    "forced_fumbles",
    "passes_defended",
    "negative_play_tackle_credits",
    "solo_tackles",
    "tackle_assists",
)

RATE_COLUMNS = (
    "passing_epa_per_play",
    "passing_yards_per_attempt",
    "completion_over_expected",
    "passing_first_down_rate",
    "passing_air_yards_per_attempt",
    "rushing_epa_per_carry",
    "rushing_yards_per_carry",
    "rushing_first_down_rate",
    "receiving_epa_per_target",
    "receiving_yards_per_target",
    "receiving_first_down_rate",
    "catch_rate",
    "yards_after_catch_per_reception",
    "touchdown_rate",
    "turnover_rate",
    "sack_rate",
    "qb_hit_rate",
    "negative_play_rate",
    "forced_fumble_rate",
    "tackle_rate",
    "interception_rate",
    "pass_defended_rate",
    "penalties_per_100_snaps",
    "field_goal_pct",
    "long_field_goal_rate",
    "extra_point_pct",
    "net_yards_per_punt",
    "inside_20_rate",
    "touchback_rate",
    "punt_block_rate",
)

OUTPUT_COLUMNS = (
    "sport",
    "player_id",
    "name",
    "season",
    "position",
    "depth_chart_position",
    "role",
    "role_assignment_source",
    "role_roster_observations",
    "role_specific_observations",
    "role_assignment_tied",
    "team",
    "games",
    "opportunity",
    "height",
    "weight",
    "height_cm",
    "weight_kg",
    "age",
    "rostered_weeks",
    *WEEKLY_TOTAL_COLUMNS,
    "passing_cpoe",
    *DEFENSIVE_TOTAL_COLUMNS,
    "defensive_opportunity",
    "offense_snaps",
    "defense_snaps",
    "st_snaps",
    "charged_offensive_penalties",
    "dropbacks",
    "touches",
    "total_tackles",
    "weekly_stats_games",
    "snap_count_games",
    "offense_snap_games",
    "defense_snap_games",
    "st_snap_games",
    "defensive_games",
    "snap_fields_status",
    *RATE_COLUMNS,
    "stats_observed",
    "snaps_observed",
    "defense_observed",
    "penalty_source_observed",
    "opportunity_complete",
    "participation_provider",
    "performance_source",
    "performance_label_status",
)

_WEEKLY_REQUIRED = {
    "player_id",
    "player_display_name",
    "position",
    "season",
    "season_type",
    "game_id",
    "team",
    "passing_cpoe",
    *WEEKLY_TOTAL_COLUMNS,
}

_PBP_PENALTY_COLUMNS = (
    "season",
    "season_type",
    "game_id",
    "play_id",
    "posteam",
    "penalty",
    "penalty_team",
    "penalty_player_id",
    "special_teams_play",
)


def map_nfl_role(position: object, depth_chart_position: object = None) -> str | None:
    """Map a roster listing to the registered all-role taxonomy.

    A specific depth-chart position takes precedence over the broader roster
    position.  Generic ``DB``, ``DL``, and ``OL`` labels are intentionally not
    guessed.  ``OLB`` is grouped with edge defenders for this broad taxonomy;
    the source position remains in the output so a later scheme-aware mapper
    can revisit that assumption.
    """

    for value in (depth_chart_position, position):
        if pd.isna(value):
            continue
        role = _POSITION_ROLE_MAP.get(str(value).strip().upper())
        if role is not None:
            return role
    return None


def _seasonal_role_assignments(frame: pd.DataFrame) -> pd.DataFrame:
    """Choose one season role from every available regular-season roster row.

    The mode is calculated at the canonical-role level, so ``FS`` and ``SS``
    jointly support the safety role rather than competing as raw labels.
    Generic or unmapped labels such as ``DB``, ``DL``, and ``OL`` never vote
    for a role.  Ties are resolved by the most recent observed week and then
    by the canonical role string; the same rule selects a representative raw
    depth-chart label inside the winning role.  Tie resolution is surfaced in
    ``role_assignment_tied`` rather than hidden.
    """

    required = {"gsis_id", "season", "game_type", "week", "depth_chart_position"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"NFL weekly rosters are missing role columns: {missing}")

    columns = [
        "player_id",
        "season",
        "seasonal_role",
        "seasonal_depth_chart_position",
        "role_roster_observations",
        "role_specific_observations",
        "role_assignment_tied",
    ]
    regular = frame.loc[frame["game_type"].eq("REG") & frame["gsis_id"].notna()].copy()
    if regular.empty:
        return pd.DataFrame(columns=columns)

    regular["player_id"] = regular["gsis_id"].astype("string")
    regular["season"] = pd.to_numeric(regular["season"], errors="raise").astype(int)
    regular["_week_order"] = pd.to_numeric(regular["week"], errors="coerce").fillna(-np.inf)
    regular["_depth"] = (
        regular["depth_chart_position"].astype("string").str.strip().str.upper().replace("", pd.NA)
    )
    regular["_role"] = regular["_depth"].map(_POSITION_ROLE_MAP).astype("string")
    keys = ["player_id", "season"]

    base = (
        regular.groupby(keys, as_index=False, dropna=False)
        .size()
        .rename(columns={"size": "role_roster_observations"})
    )
    specific = regular.loc[regular["_role"].notna()].copy()
    if specific.empty:
        base["seasonal_role"] = pd.NA
        base["seasonal_depth_chart_position"] = pd.NA
        base["role_specific_observations"] = 0
        base["role_assignment_tied"] = False
        return base.loc[:, columns]

    role_counts = (
        specific.groupby([*keys, "_role"], as_index=False, dropna=False)
        .agg(
            role_observations=("_role", "size"),
            role_last_week=("_week_order", "max"),
        )
    )
    specific_counts = (
        specific.groupby(keys, as_index=False)
        .size()
        .rename(columns={"size": "role_specific_observations"})
    )
    top_count = role_counts.groupby(keys)["role_observations"].transform("max")
    top_candidates = role_counts.loc[role_counts["role_observations"].eq(top_count)]
    ties = (
        top_candidates.groupby(keys, as_index=False)
        .size()
        .rename(columns={"size": "top_role_candidates"})
    )
    winners = (
        role_counts.sort_values(
            [*keys, "role_observations", "role_last_week", "_role"],
            ascending=[True, True, False, False, True],
        )
        .drop_duplicates(keys)
        .rename(columns={"_role": "seasonal_role"})
    )

    representative = specific.merge(
        winners.loc[:, [*keys, "seasonal_role"]].rename(columns={"seasonal_role": "_role"}),
        on=[*keys, "_role"],
        how="inner",
        validate="many_to_one",
    )
    depth_counts = (
        representative.groupby([*keys, "_depth"], as_index=False, dropna=False)
        .agg(
            depth_observations=("_depth", "size"),
            depth_last_week=("_week_order", "max"),
        )
        .sort_values(
            [*keys, "depth_observations", "depth_last_week", "_depth"],
            ascending=[True, True, False, False, True],
        )
        .drop_duplicates(keys)
        .rename(columns={"_depth": "seasonal_depth_chart_position"})
    )

    result = base.merge(
        winners.loc[:, [*keys, "seasonal_role"]],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    result = result.merge(specific_counts, on=keys, how="left", validate="one_to_one")
    result = result.merge(
        depth_counts.loc[:, [*keys, "seasonal_depth_chart_position"]],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    result = result.merge(ties, on=keys, how="left", validate="one_to_one")
    result["role_specific_observations"] = (
        result["role_specific_observations"].fillna(0).astype("Int64")
    )
    result["role_assignment_tied"] = result["top_role_candidates"].fillna(0).gt(1)
    return result.loc[:, columns].sort_values(keys).reset_index(drop=True)


def _mode(values: pd.Series) -> object:
    valid = values.dropna()
    return valid.mode().iloc[0] if len(valid) else pd.NA


def _join_unique(values: pd.Series) -> object:
    unique = sorted({str(value) for value in values.dropna() if str(value).strip()})
    return ";".join(unique) if unique else pd.NA


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").astype(float)


def _safe_ratio(
    numerator: pd.Series,
    denominator: pd.Series,
    *,
    scale: float = 1.0,
) -> pd.Series:
    """Return a finite ratio only where both inputs and a positive denominator exist."""

    top = pd.to_numeric(numerator, errors="coerce").astype(float)
    bottom = pd.to_numeric(denominator, errors="coerce").astype(float)
    valid = np.isfinite(top) & np.isfinite(bottom) & bottom.gt(0)
    result = pd.Series(np.nan, index=top.index, dtype=float)
    result.loc[valid] = scale * top.loc[valid] / bottom.loc[valid]
    return result


def _complete_sum(frame: pd.DataFrame, columns: Sequence[str]) -> pd.Series:
    """Add row components only when every component is observed."""

    values = pd.concat([_numeric(frame, column) for column in columns], axis=1)
    values.columns = list(columns)
    complete = values.notna().all(axis=1)
    result = values.sum(axis=1, min_count=len(columns)).astype(float)
    result.loc[~complete] = np.nan
    return result


def _strict_totals(
    frame: pd.DataFrame,
    columns: Sequence[str],
    keys: Sequence[str],
) -> pd.DataFrame:
    """Sum enumerated totals, nulling a season if any constituent row is missing."""

    numeric = frame.loc[:, columns].apply(pd.to_numeric, errors="coerce")
    key_values = [frame[column] for column in keys]
    totals = numeric.groupby(key_values, sort=False, dropna=False).sum(min_count=1)
    observed = numeric.notna().groupby(key_values, sort=False, dropna=False).sum()
    expected = frame.groupby(list(keys), sort=False, dropna=False).size()
    totals = totals.mask(observed.ne(expected, axis=0))
    totals.index.names = list(keys)
    return totals


def _aggregate_weekly_stats(frame: pd.DataFrame) -> pd.DataFrame:
    """Collapse regular-season weekly stat rows to one strict player-season row."""

    missing = sorted(_WEEKLY_REQUIRED.difference(frame.columns))
    if missing:
        raise ValueError(f"NFL weekly statistics are missing columns: {missing}")
    regular = frame.loc[frame["season_type"].eq("REG") & frame["player_id"].notna()].copy()
    if regular.empty:
        return pd.DataFrame(
            columns=[
                "player_id",
                "season",
                "raw_name",
                "raw_position",
                "raw_team",
                "weekly_stats_games",
                *WEEKLY_TOTAL_COLUMNS,
                "passing_cpoe",
                "stats_observed",
            ]
        )
    regular["player_id"] = regular["player_id"].astype("string")
    regular["season"] = pd.to_numeric(regular["season"], errors="raise").astype(int)
    if regular.duplicated(["player_id", "season", "game_id"]).any():
        raise ValueError("NFL weekly statistics contain duplicate player-game rows")

    numeric = regular.loc[:, WEEKLY_TOTAL_COLUMNS].apply(pd.to_numeric, errors="coerce")
    passing_plays = numeric["attempts"] + numeric["sacks_suffered"]
    for metric, exposure in [
        ("passing_epa", passing_plays),
        ("rushing_epa", numeric["carries"]),
        ("receiving_epa", numeric["targets"]),
    ]:
        # nflverse uses NaN for EPA on a row with no applicable play.  That is
        # a known zero contribution, not a missing observation.
        numeric.loc[numeric[metric].isna() & exposure.eq(0), metric] = 0.0
    regular.loc[:, WEEKLY_TOTAL_COLUMNS] = numeric

    keys = ["player_id", "season"]
    grouped = regular.groupby(keys, sort=False, dropna=False)
    base = grouped.agg(
        raw_name=("player_display_name", _mode),
        raw_position=("position", _mode),
        raw_team=("team", _join_unique),
        weekly_stats_games=("game_id", "nunique"),
    )
    totals = _strict_totals(regular, WEEKLY_TOTAL_COLUMNS, keys)

    attempts = pd.to_numeric(regular["attempts"], errors="coerce").astype(float)
    cpoe = pd.to_numeric(regular["passing_cpoe"], errors="coerce").astype(float)
    positive_attempts = attempts.gt(0)
    invalid = attempts.isna() | (positive_attempts & cpoe.isna())
    weights = attempts.where(positive_attempts, 0.0)
    weighted = cpoe.fillna(0.0) * weights
    key_values = [regular[column] for column in keys]
    weight_sum = weights.groupby(key_values, sort=False, dropna=False).sum(min_count=1)
    weighted_sum = weighted.groupby(key_values, sort=False, dropna=False).sum(min_count=1)
    invalid_group = invalid.groupby(key_values, sort=False, dropna=False).any()
    annual_cpoe = (weighted_sum / weight_sum.replace(0, np.nan)).mask(invalid_group)
    annual_cpoe.name = "passing_cpoe"

    result = base.join(totals).join(annual_cpoe).reset_index()
    result["stats_observed"] = True
    return result


def _aggregate_charged_offensive_penalties(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a conservative PBP proxy for charged offensive penalties.

    The nflverse PBP has one primary ``penalty_player_id`` per play, not a
    complete official ledger for every participant on multi-penalty plays.
    This helper therefore counts only regular-season rows whose primary
    penalty is player-attributed, charged to ``posteam``, and not marked as a
    special-teams play.  Duplicate player/play attributions count once.

    If any required field is absent, an empty result is returned with
    ``result.attrs["source_usable"] == False``.  The builder then leaves the
    numerator and rate as NaN; it never substitutes a zero for unusable PBP.
    When the schema is usable, the metric should still be read as an
    attributed-penalty discipline proxy, not an offensive-line performance
    grade or a complete official charged-penalty total.
    """

    missing = sorted(set(_PBP_PENALTY_COLUMNS).difference(frame.columns))
    columns = ["player_id", "season", "charged_offensive_penalties"]
    if missing:
        result = pd.DataFrame(columns=columns)
        result.attrs["source_usable"] = False
        result.attrs["reason"] = f"missing columns: {missing}"
        return result

    special_teams = pd.to_numeric(frame["special_teams_play"], errors="coerce").fillna(0)
    player_id = frame["penalty_player_id"].astype("string")
    valid = (
        frame["season_type"].eq("REG")
        & pd.to_numeric(frame["penalty"], errors="coerce").eq(1)
        & frame["penalty_team"].notna()
        & frame["penalty_team"].eq(frame["posteam"])
        & player_id.str.match(r"^00-\d+$", na=False)
        & special_teams.ne(1)
    )
    events = frame.loc[valid, ["season", "game_id", "play_id", "penalty_player_id"]].copy()
    events = events.rename(columns={"penalty_player_id": "player_id"})
    events["player_id"] = events["player_id"].astype("string")
    events["season"] = pd.to_numeric(events["season"], errors="raise").astype(int)
    events = events.drop_duplicates(["player_id", "season", "game_id", "play_id"])
    if events.empty:
        result = pd.DataFrame(columns=columns)
    else:
        result = (
            events.groupby(["player_id", "season"], as_index=False)
            .size()
            .rename(columns={"size": "charged_offensive_penalties"})
        )
    result.attrs["source_usable"] = True
    result.attrs["reason"] = "primary player-attributed offense-side non-special-teams PBP penalties"
    return result


def _canonical_profiles(
    processed: pd.DataFrame,
    seasons: set[int],
    seasonal_roles: pd.DataFrame | None = None,
) -> pd.DataFrame:
    required = {
        "player_id",
        "season",
        "name",
        "position",
        "depth_chart_position",
        "height_cm",
        "weight_kg",
        "age",
        "opportunity",
        "games_with_participation",
        *DEFENSIVE_TOTAL_COLUMNS,
    }
    missing = sorted(required.difference(processed.columns))
    if missing:
        raise ValueError(f"Processed NFL roster panel is missing columns: {missing}")

    canonical = processed.copy()
    canonical["season"] = pd.to_numeric(canonical["season"], errors="raise").astype(int)
    canonical = canonical.loc[canonical["season"].isin(seasons)].copy()
    canonical["player_id"] = canonical["player_id"].astype("string")
    if canonical.duplicated(["player_id", "season"]).any():
        raise ValueError("Processed NFL roster panel has duplicate player-seasons")
    canonical["role"] = [
        map_nfl_role(position, depth)
        for position, depth in zip(
            canonical["position"], canonical["depth_chart_position"], strict=True
        )
    ]
    canonical["role"] = canonical["role"].astype("string")
    if seasonal_roles is not None:
        assignments = seasonal_roles.copy()
        assignments["player_id"] = assignments["player_id"].astype("string")
        assignments["season"] = pd.to_numeric(assignments["season"], errors="raise").astype(int)
        if assignments.duplicated(["player_id", "season"]).any():
            raise ValueError("NFL seasonal role assignments contain duplicate player-seasons")
        canonical = canonical.merge(
            assignments,
            on=["player_id", "season"],
            how="left",
            validate="one_to_one",
        )
    else:
        canonical["seasonal_role"] = pd.NA
        canonical["seasonal_depth_chart_position"] = pd.NA
        canonical["role_roster_observations"] = pd.NA
        canonical["role_specific_observations"] = pd.NA
        canonical["role_assignment_tied"] = False

    seasonal_specific = canonical["seasonal_role"].notna()
    canonical.loc[seasonal_specific, "role"] = canonical.loc[
        seasonal_specific, "seasonal_role"
    ].astype("string")
    canonical.loc[seasonal_specific, "depth_chart_position"] = canonical.loc[
        seasonal_specific, "seasonal_depth_chart_position"
    ]
    has_roster_history = canonical["role_roster_observations"].notna()
    canonical["role_assignment_source"] = np.select(
        [
            seasonal_specific,
            has_roster_history & canonical["role"].isna(),
            has_roster_history & canonical["role"].notna(),
            ~has_roster_history & canonical["role"].notna(),
        ],
        [
            "weekly_roster_seasonal_modal_specific_depth",
            "weekly_roster_unmapped_unresolved",
            "weekly_roster_position_fallback",
            "processed_profile_position_fallback",
        ],
        default="no_specific_role_signal",
    )
    canonical["role_roster_observations"] = pd.to_numeric(
        canonical["role_roster_observations"], errors="coerce"
    ).astype("Int64")
    canonical["role_specific_observations"] = pd.to_numeric(
        canonical["role_specific_observations"], errors="coerce"
    ).fillna(0).astype("Int64")
    canonical["role_assignment_tied"] = (
        canonical["role_assignment_tied"].astype("boolean").fillna(False)
    )
    if "teams" in canonical:
        canonical["team"] = canonical["teams"]
    elif "team" not in canonical:
        canonical["team"] = pd.NA
    canonical = canonical.rename(
        columns={
            "opportunity": "defensive_opportunity",
            "games_with_participation": "defensive_games",
        }
    )

    for column in [
        "height",
        "weight",
        "rostered_weeks",
        "opportunity_complete",
        "opportunity_observed",
        "participation_provider",
    ]:
        if column not in canonical:
            canonical[column] = pd.NA
    if canonical["opportunity_observed"].isna().all():
        canonical["defense_observed"] = canonical["defensive_opportunity"].notna()
    else:
        canonical["defense_observed"] = canonical["opportunity_observed"].astype("boolean")

    zero_game = (
        canonical["defensive_games"].isna()
        & pd.to_numeric(canonical["defensive_opportunity"], errors="coerce").eq(0)
        & canonical["defense_observed"].fillna(False)
    )
    canonical.loc[zero_game, "defensive_games"] = 0
    columns = [
        "player_id",
        "season",
        "name",
        "position",
        "depth_chart_position",
        "role",
        "role_assignment_source",
        "role_roster_observations",
        "role_specific_observations",
        "role_assignment_tied",
        "team",
        "height",
        "weight",
        "height_cm",
        "weight_kg",
        "age",
        "rostered_weeks",
        *DEFENSIVE_TOTAL_COLUMNS,
        "defensive_opportunity",
        "defensive_games",
        "defense_observed",
        "opportunity_complete",
        "participation_provider",
    ]
    return canonical.loc[:, columns]


def _derive_rates(frame: pd.DataFrame) -> pd.DataFrame:
    """Add role-specific registry metrics using explicit, aligned denominators."""

    result = frame.copy()
    role = result["role"].astype("string")
    result["dropbacks"] = _complete_sum(result, ["attempts", "sacks_suffered"])
    result["touches"] = _complete_sum(result, ["carries", "receptions"])
    result["total_tackles"] = _complete_sum(result, ["solo_tackles", "tackle_assists"])
    for column in RATE_COLUMNS:
        result[column] = np.nan

    qb = role.eq("QB")
    result.loc[qb, "passing_epa_per_play"] = _safe_ratio(
        _numeric(result, "passing_epa"), result["dropbacks"]
    ).loc[qb]
    result.loc[qb, "passing_yards_per_attempt"] = _safe_ratio(
        _numeric(result, "passing_yards"), _numeric(result, "attempts")
    ).loc[qb]
    result.loc[qb, "completion_over_expected"] = _numeric(result, "passing_cpoe").loc[qb]
    result.loc[qb, "passing_first_down_rate"] = _safe_ratio(
        _numeric(result, "passing_first_downs"), _numeric(result, "attempts")
    ).loc[qb]
    result.loc[qb, "passing_air_yards_per_attempt"] = _safe_ratio(
        _numeric(result, "passing_air_yards"), _numeric(result, "attempts")
    ).loc[qb]
    result.loc[qb, "touchdown_rate"] = _safe_ratio(
        _numeric(result, "passing_tds"), _numeric(result, "attempts")
    ).loc[qb]
    passing_turnovers = _complete_sum(result, ["passing_interceptions", "sack_fumbles_lost"])
    result.loc[qb, "turnover_rate"] = _safe_ratio(passing_turnovers, result["dropbacks"]).loc[qb]
    result.loc[qb, "sack_rate"] = _safe_ratio(
        _numeric(result, "sacks_suffered"), result["dropbacks"]
    ).loc[qb]

    rb = role.eq("RB_FB")
    result.loc[rb, "rushing_epa_per_carry"] = _safe_ratio(
        _numeric(result, "rushing_epa"), _numeric(result, "carries")
    ).loc[rb]
    result.loc[rb, "rushing_yards_per_carry"] = _safe_ratio(
        _numeric(result, "rushing_yards"), _numeric(result, "carries")
    ).loc[rb]
    result.loc[rb, "rushing_first_down_rate"] = _safe_ratio(
        _numeric(result, "rushing_first_downs"), _numeric(result, "carries")
    ).loc[rb]

    receiving = rb | role.isin(RECEIVING_ROLES)
    result.loc[receiving, "receiving_epa_per_target"] = _safe_ratio(
        _numeric(result, "receiving_epa"), _numeric(result, "targets")
    ).loc[receiving]
    result.loc[receiving, "receiving_yards_per_target"] = _safe_ratio(
        _numeric(result, "receiving_yards"), _numeric(result, "targets")
    ).loc[receiving]

    receiver = role.isin(RECEIVING_ROLES)
    result.loc[receiver, "receiving_first_down_rate"] = _safe_ratio(
        _numeric(result, "receiving_first_downs"), _numeric(result, "targets")
    ).loc[receiver]
    result.loc[receiver, "catch_rate"] = _safe_ratio(
        _numeric(result, "receptions"), _numeric(result, "targets")
    ).loc[receiver]
    result.loc[receiver, "yards_after_catch_per_reception"] = _safe_ratio(
        _numeric(result, "receiving_yards_after_catch"), _numeric(result, "receptions")
    ).loc[receiver]

    rb_touchdowns = _complete_sum(result, ["rushing_tds", "receiving_tds"])
    rb_turnovers = _complete_sum(result, ["rushing_fumbles_lost", "receiving_fumbles_lost"])
    result.loc[rb, "touchdown_rate"] = _safe_ratio(rb_touchdowns, result["touches"]).loc[rb]
    result.loc[rb, "turnover_rate"] = _safe_ratio(rb_turnovers, result["touches"]).loc[rb]
    result.loc[receiver, "touchdown_rate"] = _safe_ratio(
        _numeric(result, "receiving_tds"), _numeric(result, "targets")
    ).loc[receiver]
    result.loc[receiver, "turnover_rate"] = _safe_ratio(
        _numeric(result, "receiving_fumbles_lost"), _numeric(result, "targets")
    ).loc[receiver]

    defense = role.isin(DEFENSIVE_ROLES)
    defensive_opportunity = _numeric(result, "defensive_opportunity")
    for metric, numerator in [
        ("sack_rate", "sacks"),
        ("qb_hit_rate", "qb_hits"),
        ("negative_play_rate", "negative_play_tackle_credits"),
        ("forced_fumble_rate", "forced_fumbles"),
        ("tackle_rate", "total_tackles"),
        ("interception_rate", "interceptions"),
        ("pass_defended_rate", "passes_defended"),
    ]:
        result.loc[defense, metric] = _safe_ratio(
            _numeric(result, numerator), defensive_opportunity
        ).loc[defense]

    kicker = role.eq("K")
    result.loc[kicker, "field_goal_pct"] = _safe_ratio(
        _numeric(result, "fg_made"), _numeric(result, "fg_att")
    ).loc[kicker]
    long_makes = _complete_sum(result, ["fg_made_50_59", "fg_made_60_"])
    result.loc[kicker, "long_field_goal_rate"] = _safe_ratio(
        long_makes, _numeric(result, "fg_att")
    ).loc[kicker]
    result.loc[kicker, "extra_point_pct"] = _safe_ratio(
        _numeric(result, "pat_made"), _numeric(result, "pat_att")
    ).loc[kicker]

    punter = role.eq("P")
    for metric, numerator in [
        ("net_yards_per_punt", "pt_net_yards"),
        ("inside_20_rate", "pt_inside_20"),
        ("touchback_rate", "pt_touchback"),
        ("punt_block_rate", "pt_blocked"),
    ]:
        result.loc[punter, metric] = _safe_ratio(
            _numeric(result, numerator), _numeric(result, "pt_att")
        ).loc[punter]
    return result


def _assign_role_exposure(frame: pd.DataFrame) -> pd.DataFrame:
    """Set release-safe role opportunities and role-appropriate games.

    OT, IOL, and LS are intentionally left without an opportunity or games
    value.  Their roster visibility is retained separately in
    ``rostered_weeks`` and must not be treated as an individual performance
    label.
    """

    result = frame.copy()
    role = result["role"].astype("string")
    result["opportunity"] = np.nan
    for mask, source in [
        (role.eq("QB"), "dropbacks"),
        (role.eq("RB_FB"), "touches"),
        (role.isin(RECEIVING_ROLES), "targets"),
        (role.isin(DEFENSIVE_ROLES), "defensive_opportunity"),
        (role.eq("K"), "fg_att"),
        (role.eq("P"), "pt_att"),
    ]:
        result.loc[mask, "opportunity"] = _numeric(result, source).loc[mask]

    game_sources = pd.concat(
        [
            _numeric(result, "weekly_stats_games"),
            _numeric(result, "defensive_games"),
        ],
        axis=1,
    )
    result["games"] = game_sources.max(axis=1, skipna=True)
    result.loc[game_sources.isna().all(axis=1), "games"] = np.nan
    for mask, source in [
        (role.isin({"QB", "RB_FB", "WR", "TE", "K", "P"}), "weekly_stats_games"),
        (role.isin(DEFENSIVE_ROLES), "defensive_games"),
    ]:
        result.loc[mask, "games"] = _numeric(result, source).loc[mask]
    result.loc[role.isin({*OFFENSIVE_LINE_ROLES, "LS"}), "games"] = np.nan
    return result


def _assign_performance_source_status(frame: pd.DataFrame) -> pd.DataFrame:
    """Expose which role families have a release-safe performance source."""

    result = frame.copy()
    role = result["role"].astype("string")
    weekly = role.isin({"QB", "RB_FB", "WR", "TE", "K", "P"})
    defense = role.isin(DEFENSIVE_ROLES)
    identity_only = role.isin({*OFFENSIVE_LINE_ROLES, "LS"})
    result["performance_source"] = np.select(
        [weekly, defense, identity_only],
        [
            "nflverse_weekly_player_stats",
            "nflverse_pbp_participation",
            "none_release_safe",
        ],
        default="none_unregistered",
    )
    result["performance_label_status"] = np.select(
        [weekly | defense, identity_only, role.isna()],
        [
            "candidate_metrics_available",
            "abstain_no_release_safe_individual_label",
            "abstain_unregistered_role",
        ],
        default="abstain_no_registered_metric_source",
    )
    return result


def _prefer(primary: pd.Series, fallback: pd.Series) -> pd.Series:
    present = primary.notna() & primary.astype("string").str.strip().ne("")
    return primary.where(present, fallback)


def build_nfl_all_roles_panel(
    root: Path,
    seasons: Iterable[int] = range(2021, 2026),
) -> pd.DataFrame:
    """Return one roster-inclusive NFL all-role row per player-season.

    The role signal is the modal specific depth-chart role across all cached
    regular-season weekly rosters.  A count tie is resolved by latest week and
    then canonical role string.  Generic-only DB/DL/OL histories remain null
    so the scorer can explicitly skip them rather than manufacture a peer
    group.

    The weekly-stat, roster, defensive-event, and PBP inputs are cached
    nflverse snapshots.  Conditional PFR-derived snaps are never read;
    OT/IOL/LS rows therefore preserve identity and roster visibility but
    explicitly abstain from an individual performance label.
    """

    root = Path(root)
    requested = sorted({int(season) for season in seasons})
    if not requested:
        raise ValueError("At least one NFL season is required")

    processed_path = root / "data" / "processed" / "nfl" / "all_rostered_player_seasons.parquet"
    if not processed_path.exists():
        raise FileNotFoundError(f"Processed NFL roster panel not found: {processed_path}")
    processed = pd.read_parquet(processed_path)
    processed_season = pd.to_numeric(processed["season"], errors="coerce")
    observed_seasons = sorted(
        int(value) for value in processed_season.loc[processed_season.isin(requested)].unique()
    )
    if not observed_seasons:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    role_parts: list[pd.DataFrame] = []
    for season in observed_seasons:
        roster_path = root / "data" / "raw" / "nfl" / str(season) / f"roster_weekly_{season}.parquet"
        if not roster_path.exists():
            raise FileNotFoundError(f"Cached NFL weekly roster not found: {roster_path}")
        role_parts.append(
            _seasonal_role_assignments(
                pd.read_parquet(
                    roster_path,
                    columns=["gsis_id", "season", "game_type", "week", "depth_chart_position"],
                )
            )
        )
    seasonal_roles = pd.concat(role_parts, ignore_index=True)
    canonical = _canonical_profiles(processed, set(requested), seasonal_roles)

    weekly_parts: list[pd.DataFrame] = []
    for season in observed_seasons:
        path = root / "data" / "raw" / "nfl" / str(season) / f"stats_player_week_{season}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Cached NFL weekly statistics not found: {path}")
        weekly_parts.append(_aggregate_weekly_stats(pd.read_parquet(path)))
    weekly = pd.concat(weekly_parts, ignore_index=True)
    if weekly.duplicated(["player_id", "season"]).any():
        raise ValueError("NFL weekly aggregation produced duplicate player-seasons")

    penalty_parts: list[pd.DataFrame] = []
    usable_penalty_seasons: set[int] = set()
    for season in observed_seasons:
        path = root / "data" / "raw" / "nfl" / str(season) / f"play_by_play_{season}.parquet"
        if not path.exists():
            continue
        schema = set(pq.read_schema(path).names)
        if not set(_PBP_PENALTY_COLUMNS).issubset(schema):
            continue
        penalties = _aggregate_charged_offensive_penalties(
            pd.read_parquet(path, columns=list(_PBP_PENALTY_COLUMNS))
        )
        if not penalties.attrs.get("source_usable", False):
            continue
        usable_penalty_seasons.add(int(season))
        penalty_parts.append(penalties)
    penalties = (
        pd.concat(penalty_parts, ignore_index=True)
        if penalty_parts
        else pd.DataFrame(columns=["player_id", "season", "charged_offensive_penalties"])
    )
    if penalties.duplicated(["player_id", "season"]).any():
        raise ValueError("NFL penalty aggregation produced duplicate player-seasons")

    panel = canonical.merge(
        weekly,
        on=["player_id", "season"],
        how="left",
        validate="one_to_one",
    )
    panel = panel.merge(
        penalties,
        on=["player_id", "season"],
        how="left",
        validate="one_to_one",
    )
    panel["name"] = _prefer(panel["name"], panel["raw_name"])
    panel["position"] = _prefer(panel["position"], panel["raw_position"])
    panel["team"] = _prefer(panel["team"], panel["raw_team"])
    panel["stats_observed"] = panel["stats_observed"].astype("boolean").fillna(False)
    for column in [
        "offense_snaps",
        "defense_snaps",
        "st_snaps",
        "snap_count_games",
        "offense_snap_games",
        "defense_snap_games",
        "st_snap_games",
    ]:
        panel[column] = np.nan
    panel["snaps_observed"] = False
    panel["snap_fields_status"] = "not_loaded_conditional_pfr_source"
    panel["defense_observed"] = panel["defense_observed"].astype("boolean").fillna(False)
    panel["penalty_source_observed"] = panel["season"].isin(usable_penalty_seasons)

    panel = _derive_rates(panel)
    panel = _assign_role_exposure(panel)
    panel = _assign_performance_source_status(panel)
    panel["sport"] = "nfl"
    panel = panel.loc[:, OUTPUT_COLUMNS]
    if panel.duplicated(["player_id", "season"]).any():
        raise ValueError("NFL all-role panel has duplicate player-seasons")
    return panel.sort_values(["season", "player_id"]).reset_index(drop=True)
