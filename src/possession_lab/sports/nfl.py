"""NFL 2021--2025 roster, event, participation, and physical measurement panel."""

from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from possession_lab.io import fetch, read_frame, save_frame, write_json

BASE = "https://github.com/nflverse/nflverse-data/releases/download"
CORE_NOTE = "nflverse CC BY 4.0; preserve upstream attribution. Research snapshot, no data relicensing."
PART_NOTE = (
    "CC BY-SA 4.0; NFL NextGenStats via nflverse (through 2022), FTN Data via nflverse (2023 onwards)."
)
PFR_NOTE = (
    "PFR-derived conditional enrichment. Sports Reference upstream AI/ML terms require review. "
    "Downloaded for source inspection; excluded from default model features/targets."
)
EVENTS = {
    "sacks": "def_sacks",
    "qb_hits": "def_qb_hits",
    "interceptions": "def_interceptions",
    "forced_fumbles": "def_fumbles_forced",
    "passes_defended": "def_pass_defended",
    "tackles_for_loss": "def_tackles_for_loss",
    "solo_tackles": "def_tackles_solo",
    "tackle_assists": "def_tackle_assists",
    "opponent_fumble_recoveries": "fumble_recovery_opp",
    "safeties": "def_safeties",
}
METRICS = {
    x: x
    for x in [
        "sacks",
        "qb_hits",
        "interceptions",
        "forced_fumbles",
        "passes_defended",
        "negative_play_tackle_credits",
    ]
}
CORE_COLUMNS = [
    "sacks",
    "qb_hits",
    "interceptions",
    "forced_fumbles",
    "passes_defended",
    "negative_play_tackle_credits",
    "solo_tackles",
    "tackle_assists",
    "opponent_fumble_recoveries",
    "safeties",
    "pass_disruption_plays",
]


def download(root: Path, seasons: list[int]) -> dict:
    raw = root / "data" / "raw" / "nfl"
    tasks = []
    for year in seasons:
        for release, name, note in [
            ("weekly_rosters", f"roster_weekly_{year}.parquet", CORE_NOTE),
            ("stats_player", f"stats_player_week_{year}.parquet", CORE_NOTE),
            ("snap_counts", f"snap_counts_{year}.parquet", PFR_NOTE),
            ("pfr_advstats", f"advstats_week_def_{year}.parquet", PFR_NOTE),
            ("pbp", f"play_by_play_{year}.parquet", CORE_NOTE),
            ("pbp_participation", f"pbp_participation_{year}.parquet", PART_NOTE),
        ]:
            tasks.append((f"{BASE}/{release}/{name}", raw / str(year) / name, note))
    for release, name, note in [
        ("players", "players.parquet", CORE_NOTE),
        ("schedules", "games.parquet", CORE_NOTE),
        ("combine", "combine.parquet", PFR_NOTE),
    ]:
        tasks.append((f"{BASE}/{release}/{name}", raw / name, note))
    for name in ["combine_official.parquet", "combine_pro_day.parquet"]:
        tasks.append(
            (
                f"https://raw.githubusercontent.com/array-carpenter/nfl-draft-data/master/data/{name}",
                raw / "optional" / name,
                "Community NFL combine/pro-day extraction. No clear data reuse license; optional inventory, excluded from model training.",
            )
        )
    failures = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(fetch, url, dest, source="nflverse/" + url.split("/")[-2], license_note=note): dest
            for url, dest, note in tasks
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                failures.append({"path": str(futures[future]), "error": str(exc)})
    write_json(
        root / "reports" / "nfl" / "download_status.json",
        {
            "expected_files": len(tasks),
            "failures": failures,
        },
    )
    if failures:
        raise RuntimeError(f"NFL downloads incomplete: {failures}")
    return {"files": len(tasks)}


def physical_enrichment(root: Path) -> dict:
    """Join optional prospect dimensions exactly by SMART ID; retain test year."""
    raw = root / "data" / "raw" / "nfl"
    out = root / "data" / "processed" / "nfl"
    identity = read_frame(out / "player_identity.parquet")
    bridge = identity[["player_id", "smart_id"]].dropna().drop_duplicates("smart_id")
    frames, coverage, long_rows = [], {}, []
    for name, protocol in [
        ("combine_official.parquet", "official_combine"),
        ("combine_pro_day.parquet", "coalesced_combine_or_pro_day"),
    ]:
        path = raw / "optional" / name
        if not path.exists():
            continue
        frame = read_frame(path)
        key = next((c for c in ["person_id", "nfl_person_id"] if c in frame), None)
        if key is None:
            raise ValueError(f"Optional physical source lacks NFL person ID: {path}")
        frame = frame.merge(bridge, left_on=key, right_on="smart_id", how="left", validate="many_to_one")
        frame["protocol"] = protocol
        frame["source"] = "array-carpenter/nfl-draft-data"
        frame["model_inclusion"] = "excluded_pending_data_rights_review"
        year_column = next((c for c in ["year", "Year", "YEAR", "combine_year", "season"] if c in frame), "")
        frame["test_year_column"] = year_column
        definitions = {
            "height_cm": (["height", "Height (in)"], 2.54),
            "weight_kg": (["weight", "Weight (lbs)"], 0.45359237),
            "arm_length_cm": (["arm_length", "Arm Length (in)"], 2.54),
            "hand_size_cm": (["hand_size", "Hand Size (in)"], 2.54),
            "wingspan_cm": (["wingspan", "Wingspan (in)"], 2.54),
            "forty_seconds": (["forty_yard_dash", "40 Yard"], 1),
            "ten_split_seconds": (["ten_yard_split", "10-Yard Split"], 1),
            "vertical_cm": (["vertical_jump", "Vert Leap (in)"], 2.54),
            "broad_jump_cm": (["broad_jump", "Broad Jump (in)"], 2.54),
            "three_cone_seconds": (["three_cone_drill", "3Cone"], 1),
            "shuttle_seconds": (["twenty_yard_shuttle", "Shuttle"], 1),
            "bench_repetitions": (["bench_press", "Bench Press"], 1),
        }
        for metric, (candidates, factor) in definitions.items():
            column = next((c for c in candidates if c in frame), None)
            if not column:
                continue
            observation = frame[
                ["player_id", column, year_column, "protocol", "source", "model_inclusion"]
            ].copy()
            observation = observation.rename(columns={column: "value", year_column: "measurement_year"})
            observation["metric"] = metric
            observation["value"] = pd.to_numeric(observation.value, errors="coerce") * factor
            observation["measurement_year"] = pd.to_numeric(observation.measurement_year, errors="coerce")
            observation["date_precision"] = "year_only"
            long_rows.append(observation.dropna(subset=["player_id", "value", "measurement_year"]))
        coverage[protocol] = {
            "rows": len(frame),
            "matched_nfl_players": frame.player_id.nunique(),
            "source_columns": list(frame.columns),
        }
        frames.append(frame)
    if frames:
        save_frame(pd.concat(frames, ignore_index=True), out / "conditional_anthropometrics.parquet")
    if long_rows:
        observed = pd.concat(long_rows, ignore_index=True)
        observed["protocol_priority"] = observed.protocol.map(
            {"official_combine": 0, "coalesced_combine_or_pro_day": 1}
        )
        save_frame(observed, out / "conditional_test_measurement_events.parquet")
        roster_panel = read_frame(out / "all_rostered_player_seasons.parquet")[["player_id", "season"]]
        selected = roster_panel.merge(observed, on="player_id", how="inner")
        selected = selected[selected.measurement_year.le(selected.season)]
        selected = selected.sort_values(["protocol_priority", "measurement_year"], ascending=[True, False])
        selected = selected.drop_duplicates(["player_id", "season", "metric"])
        selected["years_since_measurement"] = selected.season - selected.measurement_year
        save_frame(selected, out / "conditional_player_season_measurements.parquet")
        coverage["roster_2025_coverage"] = {
            "roster_players": int(roster_panel[roster_panel.season.eq(2025)].player_id.nunique()),
            "measured_players_by_metric": selected[selected.season.eq(2025)]
            .groupby("metric")
            .player_id.nunique()
            .to_dict(),
            "model_inclusion": "Excluded from default model training pending source data-rights review.",
        }
    write_json(root / "reports" / "nfl" / "physical_enrichment.json", coverage)
    return coverage


def advanced_enrichment(root: Path) -> None:
    """Prepare pressure/coverage/tackling features without changing model tiers."""
    out = root / "data" / "processed" / "nfl"
    advanced = read_frame(out / "conditional_advanced_defense.parquet")
    if advanced.duplicated(["player_id", "season", "game_id"]).any():
        raise ValueError("Duplicate advanced defensive player-game")
    counts = [
        "def_targets",
        "def_completions_allowed",
        "def_yards_allowed",
        "def_receiving_td_allowed",
        "def_yards_after_catch",
        "def_times_blitzed",
        "def_times_hurried",
        "def_times_hitqb",
        "def_sacks",
        "def_pressures",
        "def_tackles_combined",
        "def_missed_tackles",
    ]
    counts = [c for c in counts if c in advanced]
    annual = advanced.dropna(subset=["player_id"]).groupby(["player_id", "season"])[counts].sum(min_count=1)
    annual["advanced_games_observed"] = advanced.groupby(["player_id", "season"]).game_id.nunique()
    panel = read_frame(out / "player_seasons.parquet")
    annual = panel[["player_id", "season", "role", "opportunity", "on_field_dropbacks"]].merge(
        annual.reset_index(), on=["player_id", "season"], how="left", validate="one_to_one"
    )
    annual["advanced_source_observed"] = annual.advanced_games_observed.notna()
    denominator = annual.def_targets.replace(0, np.nan)
    annual["completion_rate_allowed"] = annual.def_completions_allowed / denominator
    annual["yards_allowed_per_target"] = annual.def_yards_allowed / denominator
    annual["td_allowed_per_target"] = annual.def_receiving_td_allowed / denominator
    annual["yac_per_completion_allowed"] = (
        annual.def_yards_after_catch / annual.def_completions_allowed.replace(0, np.nan)
    )
    annual["missed_tackle_rate"] = annual.def_missed_tackles / (
        annual.def_tackles_combined + annual.def_missed_tackles
    ).replace(0, np.nan)
    annual["pressures_per100_on_field_dropbacks"] = (
        100 * annual.def_pressures / annual.on_field_dropbacks.replace(0, np.nan)
    )
    annual["sacks_per_pressure"] = annual.def_sacks / annual.def_pressures.replace(0, np.nan)
    annual["definition"] = (
        "PFR-derived; pressure/coverage fields retain provider assignments; on-field dropbacks are an exposure proxy"
    )
    annual["model_inclusion"] = "excluded_pending_upstream_rights_review"
    save_frame(annual, out / "conditional_player_seasons.parquet")


def map_role(position: object, depth: object = None) -> str:
    """Conservative listed-position mapping; OLB remains ambiguous."""
    pos = str(position).upper() if pd.notna(position) else ""
    dep = str(depth).upper() if pd.notna(depth) else ""
    for candidate in [dep, pos]:
        if candidate in {"DT", "NT", "IDL"}:
            return "IDL"
        if candidate in {"DE", "EDGE"}:
            return "EDGE"
        if candidate in {"ILB", "MLB", "LB", "WLB", "SLB"}:
            return "LB"
        if candidate == "OLB":
            return "OLB_HYBRID"
        if candidate in {"CB", "RCB", "LCB", "NB"}:
            return "CB"
        if candidate in {"S", "FS", "SS", "SAF"}:
            return "S"
    if pos in {"DB", "DL"}:
        return pos + "_UNKNOWN"
    return "NON_DEFENSE"


def parse_height(value: object) -> float:
    if pd.isna(value):
        return np.nan
    text = str(value)
    if re.fullmatch(r"\d+-\d+(?:\.\d+)?", text):
        feet, inches = text.split("-")
        return (float(feet) * 12 + float(inches)) * 2.54
    number = pd.to_numeric(value, errors="coerce")
    return float(number * 2.54) if pd.notna(number) and 55 <= number <= 90 else np.nan


def _mode(series: pd.Series) -> object:
    valid = series.dropna()
    return valid.mode().iloc[0] if len(valid) else np.nan


def participation_opportunities(pbp: pd.DataFrame, participation: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Count observed scrimmage participation, without inventing rush assignments."""
    left = participation.rename(columns={"nflverse_game_id": "game_id"}).copy()
    if left.duplicated(["game_id", "play_id"]).any():
        raise ValueError("Duplicate participation game/play key")
    cols = [
        "game_id",
        "play_id",
        "season_type",
        "play_type",
        "defteam",
        "pass_attempt",
        "rush_attempt",
        "qb_dropback",
        "qb_scramble",
        "no_play",
        "down",
    ]
    cols = [x for x in cols if x in pbp]
    merged = left.merge(
        pbp[cols], on=["game_id", "play_id"], how="left", validate="one_to_one", indicator=True
    )
    qa = {"participation_rows": len(left), "unmatched_plays": int((merged["_merge"] != "both").sum())}
    valid = merged[
        merged["season_type"].eq("REG")
        & merged["play_type"].isin(["pass", "run"])
        & merged.get("no_play", pd.Series(0, index=merged.index)).fillna(0).eq(0)
    ].copy()
    valid["player_id"] = valid["defense_players"].fillna("").str.split(";")
    valid = valid.explode("player_id")
    valid["player_id"] = valid["player_id"].str.strip()
    valid = valid[valid["player_id"].str.match(r"00-\d+$", na=False)]
    duplicate = valid.duplicated(["game_id", "play_id", "player_id"])
    qa["duplicate_defender_play"] = int(duplicate.sum())
    valid = valid[~duplicate].copy()
    valid["opportunity"] = 1
    valid["on_field_dropbacks"] = pd.to_numeric(valid["qb_dropback"], errors="coerce").fillna(0)
    valid["on_field_designed_runs"] = (
        pd.to_numeric(valid["rush_attempt"], errors="coerce").fillna(0).eq(1)
        & pd.to_numeric(valid["qb_scramble"], errors="coerce").fillna(0).eq(0)
    ).astype(int)
    valid["late_down_exposure"] = valid["down"].isin([3, 4]).astype(int)
    valid["on_field_pressured_plays"] = valid["was_pressure"].astype("boolean").fillna(False).astype(int)
    aggregations = {
        x: "sum"
        for x in [
            "opportunity",
            "on_field_dropbacks",
            "on_field_designed_runs",
            "late_down_exposure",
            "on_field_pressured_plays",
        ]
    }
    result = valid.groupby(["player_id", "game_id", "defteam"], as_index=False).agg(aggregations)
    result = result.rename(columns={"defteam": "team"})
    qa["player_plays"] = len(valid)
    qa["games_with_scrimmage_participation"] = int(result.game_id.nunique())
    return result, qa


def scrimmage_events(pbp: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize credited defender events over the same play scope as exposure."""
    valid = pbp[
        pbp.season_type.eq("REG")
        & pbp.play_type.isin(["pass", "run"])
        & pbp.get("no_play", pd.Series(0, index=pbp.index)).fillna(0).eq(0)
    ].copy()
    mapping = {
        "sacks": [("sack_player_id", 1), ("half_sack_1_player_id", 0.5), ("half_sack_2_player_id", 0.5)],
        "qb_hits": [("qb_hit_1_player_id", 1), ("qb_hit_2_player_id", 1)],
        "interceptions": [("interception_player_id", 1)],
        "forced_fumbles": [("forced_fumble_player_1_player_id", 1), ("forced_fumble_player_2_player_id", 1)],
        "passes_defended": [("pass_defense_1_player_id", 1), ("pass_defense_2_player_id", 1)],
        "negative_play_tackle_credits": [
            ("tackle_for_loss_1_player_id", 1),
            ("tackle_for_loss_2_player_id", 1),
        ],
        "solo_tackles": [("solo_tackle_1_player_id", 1), ("solo_tackle_2_player_id", 1)],
        "tackle_assists": [
            ("assist_tackle_1_player_id", 1),
            ("assist_tackle_2_player_id", 1),
            ("assist_tackle_3_player_id", 1),
            ("assist_tackle_4_player_id", 1),
        ],
        "opponent_fumble_recoveries": [
            ("fumble_recovery_1_player_id", 1),
            ("fumble_recovery_2_player_id", 1),
        ],
        "safeties": [("safety_player_id", 1)],
    }
    rows = []
    for metric, fields in mapping.items():
        for field, value in fields:
            if field not in valid:
                continue
            credits = valid[valid[field].notna()].copy()
            event_team = field.replace("_player_id", "_team")
            if event_team in credits:
                credits = credits[credits[event_team].eq(credits.defteam)]
            if metric == "forced_fumbles":
                team_column = field.replace("_player_id", "_team")
                if team_column in credits:
                    credits = credits[credits[team_column].eq(credits.defteam)]
            if metric == "opponent_fumble_recoveries":
                team_column = field.replace("_player_id", "_team")
                fumble_number = field.split("_")[2]
                fumble_column = f"fumbled_{fumble_number}_team"
                # Only the defending team recovering an offense fumble qualifies.
                credits = credits[credits[team_column].eq(credits.defteam)]
                if fumble_column in credits:
                    fumbler_team = credits[fumble_column].copy()
                    if int(fumble_number) > 1:
                        previous_recovery = f"fumble_recovery_{int(fumble_number) - 1}_team"
                        if previous_recovery in credits:
                            fumbler_team = fumbler_team.fillna(credits[previous_recovery])
                    credits = credits[fumbler_team.eq(credits.posteam)]
            take = credits[
                ["game_id", "play_id", "defteam", field, "down", "ydstogo", "yards_gained", "epa"]
            ].copy()
            take = take.rename(columns={"defteam": "team", field: "player_id"})
            take["metric"] = metric
            take["value"] = value
            rows.append(take)
    credits = pd.concat(rows, ignore_index=True)
    credits = credits.drop_duplicates(["game_id", "play_id", "player_id", "metric"])
    counts = (
        credits.groupby(["player_id", "game_id", "team", "metric"])
        .value.sum()
        .unstack("metric", fill_value=0)
        .reset_index()
    )
    observed_metrics = [
        metric for metric, fields in mapping.items() if any(field in valid for field, _ in fields)
    ]
    for metric in CORE_COLUMNS:
        if metric not in counts:
            counts[metric] = 0 if metric in observed_metrics else np.nan
    disruption = credits[credits.metric.isin(["sacks", "qb_hits", "passes_defended"])]
    distinct = disruption.drop_duplicates(["player_id", "game_id", "play_id"])
    distinct = distinct.groupby(["player_id", "game_id", "team"]).size().rename("_unique_disruption")
    counts = counts.merge(distinct.reset_index(), on=["player_id", "game_id", "team"], how="left")
    counts["pass_disruption_plays"] = counts.pop("_unique_disruption").fillna(0)
    counts.attrs["observed_metrics"] = observed_metrics + ["pass_disruption_plays"]
    return counts, credits


def participation_credit_gaps(credits: pd.DataFrame, participation: pd.DataFrame) -> pd.DataFrame:
    keys = participation[["nflverse_game_id", "play_id", "defense_players"]].rename(
        columns={"nflverse_game_id": "game_id"}
    )
    keys = keys.copy()
    keys["player_id"] = keys.defense_players.fillna("").str.split(";")
    keys = keys.explode("player_id")
    keys["player_id"] = keys.player_id.str.strip()
    keys = keys[["game_id", "play_id", "player_id"]].drop_duplicates()
    tested = credits.merge(
        keys,
        on=["game_id", "play_id", "player_id"],
        how="left",
        indicator=True,
        validate="many_to_one",
    )
    return tested[tested["_merge"].eq("left_only")].drop(columns="_merge")


def process(root: Path, seasons: list[int]) -> pd.DataFrame:
    raw = root / "data" / "raw" / "nfl"
    out = root / "data" / "processed" / "nfl"
    out.mkdir(parents=True, exist_ok=True)
    players = read_frame(raw / "players.parquet")
    crosswalk = players.dropna(subset=["gsis_id"]).drop_duplicates("gsis_id").copy()
    crosswalk = crosswalk.rename(columns={"gsis_id": "player_id"})
    save_frame(crosswalk, out / "player_identity.parquet")
    pfr = crosswalk[["player_id", "pfr_id"]].dropna().drop_duplicates("pfr_id")
    schedules = read_frame(raw / "games.parquet")
    schedules = schedules[schedules.season.isin(seasons)].copy()
    regular_games = schedules[schedules.game_type.eq("REG")].copy()
    # Cancelled games have no final scores; completed-game counts drive QA.
    if {"home_score", "away_score"}.issubset(regular_games):
        regular_games = regular_games.dropna(subset=["home_score", "away_score"])
    save_frame(schedules, out / "games.parquet")
    qa = {"seasons": {}, "opportunity_definition": "Observed non-no-play scrimmage defender player-plays"}
    (
        all_panels,
        all_games,
        all_rosters,
        measurements,
        all_enhanced,
        all_credits,
        all_reported,
        all_snaps,
        all_gaps,
    ) = [], [], [], [], [], [], [], [], []

    for year in seasons:
        print(f"NFL processing season {year}", flush=True)
        season_path = raw / str(year)
        roster = read_frame(season_path / f"roster_weekly_{year}.parquet")
        roster = roster[roster.game_type.eq("REG")].copy()
        missing_ids = roster[roster.gsis_id.isna()].copy()
        save_frame(missing_ids, out / f"unresolved_roster_{year}.parquet")
        roster = roster[roster.gsis_id.notna()].rename(columns={"gsis_id": "player_id"})
        roster["player_id"] = roster.player_id.astype(str)
        roster = roster.sort_values(["player_id", "week"])
        roster["role"] = [map_role(p, d) for p, d in zip(roster.position, roster.depth_chart_position)]
        # Every weekly observation stays in the silver roster table.
        all_rosters.append(roster)
        # Earliest annual listing, not a retroactively assigned current bio.
        first = roster.groupby("player_id", sort=False).head(1).copy()
        panel = first[
            [
                "player_id",
                "season",
                "full_name",
                "birth_date",
                "height",
                "weight",
                "position",
                "depth_chart_position",
                "role",
                "week",
                "pfr_id",
            ]
        ].copy()
        panel = panel.rename(columns={"full_name": "name", "week": "physical_first_roster_week"})
        panel["height_cm"] = panel.height.map(parse_height)
        panel["weight_kg"] = pd.to_numeric(panel.weight, errors="coerce") * 0.45359237
        anchor = pd.Timestamp(f"{year}-09-01")
        panel["age"] = (anchor - pd.to_datetime(panel.birth_date, errors="coerce")).dt.days / 365.25
        panel["measurement_context"] = (
            "earliest archived weekly roster listing; date of actual measurement unknown"
        )
        panel["measurement_season"] = year
        panel["physical_asof_valid"] = False
        team_lists = roster.groupby("player_id").team.agg(lambda x: ";".join(sorted(x.dropna().unique())))
        panel["teams"] = panel.player_id.map(team_lists)
        panel["rostered_weeks"] = panel.player_id.map(roster.groupby("player_id").week.nunique())
        for metric, column, factor in [("height_cm", "height", 2.54), ("weight_kg", "weight", 0.45359237)]:
            m = roster[["player_id", "season", "week", "team", column]].dropna(subset=[column]).copy()
            m = m.drop_duplicates(["player_id", column], keep="first")
            m["metric"] = metric
            m["value"] = pd.to_numeric(m[column], errors="coerce") * factor
            m["source"] = "nflverse_weekly_rosters"
            m["protocol"] = "roster_listing_not_verified_measurement"
            measurements.append(
                m[["player_id", "season", "week", "team", "metric", "value", "source", "protocol"]]
            )

        stats = read_frame(season_path / f"stats_player_week_{year}.parquet")
        stats = stats[stats.season_type.eq("REG")].copy()
        event_cols = [v for v in EVENTS.values() if v in stats]
        stats = stats[["player_id", "game_id", "team", *event_cols]].copy()
        stats = stats.rename(columns={v: k for k, v in EVENTS.items()})
        stats["season"] = year
        all_reported.append(stats)
        pbp = read_frame(season_path / f"play_by_play_{year}.parquet")
        part = read_frame(season_path / f"pbp_participation_{year}.parquet")
        opportunities, pqa = participation_opportunities(pbp, part)
        events, credits = scrimmage_events(pbp)
        observed_metric_columns = events.attrs["observed_metrics"]
        credits["season"] = year
        all_credits.append(credits)
        gaps = participation_credit_gaps(credits, part)
        gaps["season"] = year
        all_gaps.append(gaps)
        gap_counts = (
            gaps.groupby(["player_id", "game_id"]).size().rename("event_credits_without_participation")
        )
        games = opportunities.merge(
            events,
            on=["player_id", "game_id", "team"],
            how="outer",
            validate="one_to_one",
            indicator="event_source_join",
        )
        games = games.merge(
            gap_counts.reset_index(), on=["player_id", "game_id"], how="left", validate="one_to_one"
        )
        games["season"] = year
        games["has_credited_event"] = games.event_source_join.ne("left_only")
        games["event_counts_observed"] = True
        games["participation_observed"] = games.opportunity.notna()
        games["event_credits_without_participation"] = games.event_credits_without_participation.fillna(
            0
        ).astype(int)
        games["games_missing_participation"] = games.event_credits_without_participation.gt(0).astype(int)
        games["opportunity_complete"] = games.games_missing_participation.eq(0)
        # The event child table suppresses all-zero players. A covered participant
        # with no credited event row has a confirmed zero on these covered plays.
        for metric in observed_metric_columns:
            if metric in games:
                games.loc[games.event_source_join.eq("left_only"), metric] = 0
        games["participation_provider"] = "NGS" if year <= 2022 else "FTN"
        all_games.append(games)
        numeric = [
            "opportunity",
            "on_field_dropbacks",
            "on_field_designed_runs",
            "late_down_exposure",
            "on_field_pressured_plays",
            "games_missing_participation",
            "event_credits_without_participation",
            *CORE_COLUMNS,
        ]
        numeric = [x for x in numeric if x in games]
        annual = games.groupby("player_id", as_index=False)[numeric].sum(min_count=1)
        annual["games_with_participation"] = annual.player_id.map(
            opportunities.groupby("player_id").game_id.nunique()
        ).fillna(0)
        unknown = annual[~annual.player_id.isin(panel.player_id)].copy()
        # Retain actual participants even if a roster snapshot omitted them.
        if len(unknown):
            extra = unknown[["player_id"]].merge(
                crosswalk[["player_id", "display_name", "birth_date", "position"]],
                how="left",
                on="player_id",
                validate="one_to_one",
            )
            extra["name"] = extra.display_name
            extra["season"] = year
            extra["role"] = extra.position.map(map_role)
            extra["universe_evidence"] = "participation_or_credited_event_only"
            panel["universe_evidence"] = "weekly_roster"
            panel = pd.concat([panel, extra], ignore_index=True)
        else:
            panel["universe_evidence"] = "weekly_roster"
        panel = panel.merge(annual, on="player_id", how="left", validate="one_to_one")
        # Complete annual roster plus complete participation season supports a
        # no-opportunity state for players never appearing in that feed.
        absent = panel.opportunity.isna() & ~panel.player_id.isin(games.player_id)
        zeroable = [
            column for column in numeric if column not in CORE_COLUMNS or column in observed_metric_columns
        ]
        panel.loc[absent, zeroable] = 0
        panel["observed_opportunity"] = panel.opportunity
        panel["opportunity_complete"] = panel.games_missing_participation.eq(0)
        panel.loc[~panel.opportunity_complete, "opportunity"] = np.nan
        panel["opportunity_observed"] = panel.opportunity.notna()
        panel["event_counts_observed"] = True
        panel["has_defensive_opportunity"] = panel.opportunity.gt(0)
        panel["direct_recovered_takeaways"] = panel.interceptions + panel.opponent_fumble_recoveries
        panel["official_tackles_for_loss"] = panel.player_id.map(
            stats.groupby("player_id").tackles_for_loss.sum(min_count=1)
        ).fillna(0)
        panel["roster_source"] = "nflverse_weekly_rosters"
        panel["participation_provider"] = "NGS" if year <= 2022 else "FTN"
        panel["role_confidence"] = np.where(
            panel.role.isin(["OLB_HYBRID", "DL_UNKNOWN", "DB_UNKNOWN"]), "low", "listed_position_only"
        )
        all_panels.append(panel)

        advanced = read_frame(season_path / f"advstats_week_def_{year}.parquet")
        advanced = advanced[advanced.game_type.eq("REG")].merge(
            pfr, left_on="pfr_player_id", right_on="pfr_id", how="left", validate="many_to_one"
        )
        advanced["conditional_source"] = "PFR; not used by default models"
        all_enhanced.append(advanced)
        snaps = read_frame(season_path / f"snap_counts_{year}.parquet")
        snaps = snaps[snaps.game_type.eq("REG")].merge(
            pfr, left_on="pfr_player_id", right_on="pfr_id", how="left", validate="many_to_one"
        )
        all_snaps.append(snaps)
        snaps = snaps.groupby("player_id").defense_snaps.sum()
        compare = panel.set_index("player_id")[["opportunity"]].join(snaps).dropna()
        qa["seasons"][str(year)] = {
            "roster_rows": len(roster),
            "roster_players": roster.player_id.nunique(),
            "roster_rows_missing_gsis_quarantined": len(missing_ids),
            "completed_regular_games": int(regular_games[regular_games.season.eq(year)].game_id.nunique()),
            "pbp_regular_games": int(pbp[pbp.season_type.eq("REG")].game_id.nunique()),
            "panel_rows": len(panel),
            "participant_not_rostered": len(unknown),
            "defensive_players": int(panel.role.ne("NON_DEFENSE").sum()),
            "zero_defensive_opportunity": int(panel.opportunity.eq(0).sum()),
            "missing_opportunity": int(panel.opportunity.isna().sum()),
            "participation_qa": pqa,
            "credit_participation_gaps": {
                "metric_credit_rows": len(gaps),
                "distinct_player_plays": len(gaps.drop_duplicates(["game_id", "play_id", "player_id"])),
                "player_games": len(gaps.drop_duplicates(["game_id", "player_id"])),
                "player_seasons_excluded_from_rate_modeling": int((~panel.opportunity_complete).sum()),
            },
            "negative_play_tackle_definition": {
                "pbp_negative_play_tackle_credits": float(events.negative_play_tackle_credits.sum()),
                "official_weekly_tfl": float(stats.tackles_for_loss.sum()),
                "note": "These historical definitions differ before 2024; never splice or label them as the same target.",
            },
            "unattributed_safety_plays": int(
                pbp[pbp.season_type.eq("REG") & pbp.play_type.isin(["pass", "run"])].safety.fillna(0).sum()
                - credits[credits.metric.eq("safeties")].value.sum()
            ),
            "event_scope_reconciliation": {
                metric: {
                    "scrimmage_pbp": float(events[metric].sum()),
                    "all_credited_weekly": float(stats[metric].sum()),
                    "note": "Differences include special teams, penalties/no-plays, and scoring conventions.",
                }
                for metric in METRICS
                if metric in stats
            },
            "snap_comparison": {
                "matched_players": len(compare),
                "mean_pfr_snaps_minus_scrimmage_participation": float(
                    (compare.defense_snaps - compare.opportunity).mean()
                ),
                "note": "Different scopes: PFR includes penalty snaps; core excludes no-plays and special teams.",
            },
        }
        del pbp, part, roster, advanced

    all_panel = pd.concat(all_panels, ignore_index=True)
    if all_panel.duplicated(["player_id", "season"]).any():
        raise ValueError("NFL duplicated player-season")
    save_frame(all_panel, out / "all_rostered_player_seasons.parquet")
    model_panel = all_panel[all_panel.role.ne("NON_DEFENSE")].copy()
    save_frame(model_panel, out / "player_seasons.parquet")
    save_frame(pd.concat(all_games, ignore_index=True), out / "player_games.parquet")
    save_frame(pd.concat(all_credits, ignore_index=True), out / "defender_event_credits.parquet")
    save_frame(pd.concat(all_gaps, ignore_index=True), out / "participation_credit_gaps.parquet")
    save_frame(pd.concat(all_reported, ignore_index=True), out / "reported_player_games.parquet")
    save_frame(pd.concat(all_rosters, ignore_index=True), out / "weekly_rosters.parquet")
    save_frame(pd.concat(measurements, ignore_index=True), out / "measurement_events.parquet")
    save_frame(pd.concat(all_enhanced, ignore_index=True), out / "conditional_advanced_defense.parquet")
    save_frame(pd.concat(all_snaps, ignore_index=True), out / "conditional_snap_counts.parquet")
    combine = read_frame(raw / "combine.parquet")
    combine = combine.merge(pfr, on="pfr_id", how="left", validate="many_to_one")
    combine["model_inclusion"] = "excluded_pending_upstream_rights_review"
    combine["protocol"] = np.where(
        combine.season.eq(2021), "pro_day_2021_format", "historical_combine_listing"
    )
    save_frame(combine, out / "conditional_combine.parquet")
    physical_enrichment(root)
    advanced_enrichment(root)
    qa["total_model_rows"] = len(model_panel)
    qa["unique_defenders"] = model_panel.player_id.nunique()
    qa["combine_matched_defenders"] = (
        model_panel.player_id.isin(combine.player_id.dropna()).groupby(model_panel.player_id).any().sum()
    )
    write_json(root / "reports" / "nfl" / "qa.json", qa)
    write_json(out / "qa.json", qa)
    return model_panel


def analyze(root: Path) -> dict:
    from possession_lab.analysis import analyze_sport

    panel = read_frame(root / "data" / "processed" / "nfl" / "player_seasons.parquet")
    return analyze_sport(
        panel,
        "nfl",
        root,
        metrics=METRICS,
        physical_features=["height_cm", "weight_kg", "age"],
        opportunity_unit="observed defensive scrimmage player-plays",
        limitations=[
            "Core opportunity counts observed non-no-play scrimmage participation, not exact pass-rush or coverage snaps.",
            "2021-2022 participation is NGS; 2023-2025 is FTN. Provider effects are retained and rates remain exposure proxies.",
            "OLB usage cannot be reliably split into edge/off-ball; OLB_HYBRID is explicit.",
            "PFR pressures, coverage targets, missed tackles, snaps and combine data are stored separately and excluded from default models.",
            "Roster physical fields are archived listings, not verified yearly measurements; forecast models exclude them unless as-of validity is established.",
            "Sacks, hits and pass breakups overlap in football value; they are modeled separately and are not added into an unvalidated total.",
            "Default event counts are normalized PBP credits on the same valid scrimmage scope as participation; official weekly all-phase credits are preserved separately.",
            "PBP negative_play_tackle_credits are broader than pre-2024 official TFL. Official weekly TFL is stored separately and is not spliced into the target.",
            "Three 2025 player-seasons have uncovered event credits in participation. Their observed partial exposure is retained, but rate-model opportunity is null.",
            "All-rostered universe includes zero-opportunity players with known GSIS IDs; unresolved roster identities are quarantined.",
            "Anticipation/reaction/awareness are not directly measured by public box-score or participation data.",
        ],
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
        result = function(arguments.root, arguments.seasons)
    if isinstance(result, dict):
        print(json.dumps(result, default=str, indent=2))
