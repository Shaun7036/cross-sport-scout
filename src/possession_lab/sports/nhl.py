"""NHL skater acquisition and canonical possession/disruption panels.

MoneyPuck's designated downloads are the statistical source.  The provider's
``all`` situation already contains 5-on-5 play, so the two views are widened
into separate columns and are never added together.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from possession_lab.io import fetch, read_frame, save_frame, write_json

MONEYPUCK_LICENSE = (
    "MoneyPuck data are free for non-commercial use and ad-hoc journalism with "
    "clear MoneyPuck attribution; contact MoneyPuck for other uses."
)
NHL_LICENSE = (
    "Official NHL statistics used for research validation/enrichment; NHL data and "
    "marks remain subject to NHL terms."
)
MONEYPUCK_SUMMARY_URL = (
    "https://www.moneypuck.com/moneypuck/playerData/seasonSummary/{season}/regular/skaters.csv"
)
MONEYPUCK_GAMES_URL = "https://peter-tanner.com/moneypuck/downloads/seasonPlayersSummary/skaters/{season}.zip"
MONEYPUCK_BIOS_URL = "https://www.moneypuck.com/moneypuck/playerData/playerBios/allPlayersLookup.csv"
NHL_BIOS_URL = (
    "https://api.nhle.com/stats/rest/en/skater/bios?isAggregate=true&isGame=false"
    "&start=0&limit=-1&cayenneExp=seasonId={season_id}%20and%20gameTypeId=2"
)

EVENT_SOURCE_COLUMNS = {
    "takeaways": "I_F_takeaways",
    "blocks": "shotsBlockedByPlayer",
    "hits": "I_F_hits",
    "giveaways": "I_F_giveaways",
    "faceoff_wins": "faceoffsWon",
}
SITUATIONS = ("all", "5on5")
PHYSICAL_TEMPORALITY = (
    "NHL bios report for a season-filtered athlete universe; profile values are "
    "current/undated, their measurement date is unavailable, and repeated values "
    "must not be interpreted as annual measurements"
)


def _clean_id(series: pd.Series) -> pd.Series:
    """Return stable string identifiers without float-style ``.0`` suffixes."""
    values = series.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    return values.mask(values.isin(["", "nan", "None", "<NA>"]))


def _parse_height_cm(value: Any) -> float:
    """Parse MoneyPuck's feet/inches bio value; return NaN when not defensible."""
    if value is None or pd.isna(value):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        # Numeric MoneyPuck values are normally total inches.
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


def _role(position: Any) -> str:
    value = "" if pd.isna(position) else str(position).strip().upper()
    if value == "D":
        return "defense"
    if value == "C":
        return "center"
    if value in {"L", "R", "LW", "RW"}:
        return "wing"
    return "skater_other"


def _age_on_october_first(birth_dates: pd.Series, seasons: pd.Series) -> pd.Series:
    births = pd.to_datetime(birth_dates, errors="coerce")
    years = pd.to_numeric(seasons, errors="coerce").astype("Int64")
    result = pd.Series(pd.NA, index=birth_dates.index, dtype="Int64")
    valid = births.notna() & years.notna()
    if valid.any():
        birthdays_passed = (births[valid].dt.month < 10) | (
            (births[valid].dt.month == 10) & (births[valid].dt.day <= 1)
        )
        result.loc[valid] = (years[valid] - births[valid].dt.year - (~birthdays_passed).astype(int)).astype(
            "Int64"
        )
    return result


def _existing_columns(frame: pd.DataFrame, columns: Iterable[str]) -> list[str]:
    return [column for column in columns if column in frame.columns]


def _normalise_source(frame: pd.DataFrame, *, game_level: bool) -> pd.DataFrame:
    required = {"playerId", "season", "name", "position", "situation", "icetime"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"MoneyPuck table is missing required columns: {missing}")

    output = pd.DataFrame(index=frame.index)
    output["player_id"] = _clean_id(frame["playerId"])
    output["season"] = pd.to_numeric(frame["season"], errors="coerce").astype("Int64")
    output["name"] = frame["name"].astype("string")
    output["position"] = frame["position"].astype("string")
    output["situation"] = frame["situation"].astype("string").str.lower()
    output["team"] = frame.get("playerTeam" if game_level else "team", pd.NA)
    output["icetime"] = pd.to_numeric(frame["icetime"], errors="coerce")
    if "games_played" in frame:
        output["games_played"] = pd.to_numeric(frame["games_played"], errors="coerce")
    for canonical, source_column in EVENT_SOURCE_COLUMNS.items():
        output[canonical] = pd.to_numeric(frame.get(source_column), errors="coerce")

    if game_level:
        output["game_id"] = _clean_id(frame["gameId"])
        output["game_date"] = pd.to_datetime(frame.get("gameDate"), errors="coerce")
        output["opponent"] = frame.get("opposingTeam", pd.NA)
        output["home_away"] = frame.get("home_or_away", pd.NA)
    return output.loc[output["situation"].isin(SITUATIONS) & output["player_id"].notna()].copy()


def _combine_stints(
    frame: pd.DataFrame,
    *,
    keys: list[str],
    metadata: list[str],
) -> pd.DataFrame:
    """Collapse team stints while preferring an explicit provider total row."""
    group_keys = keys + ["situation"]
    frame = frame.copy()
    team_upper = frame["team"].astype("string").str.upper()
    total_row = team_upper.isin({"TOT", "TOTAL", "ALL"})
    any_total = total_row.groupby([frame[column] for column in group_keys], dropna=False).transform("max")
    frame = frame.loc[~any_total | total_row].copy()

    numeric = _existing_columns(frame, ["games_played", "icetime", *EVENT_SOURCE_COLUMNS])
    totals = frame.groupby(group_keys, as_index=False, dropna=False)[numeric].sum(min_count=1)

    dominant = (
        frame.sort_values("icetime", ascending=False, na_position="last")
        .groupby(group_keys, as_index=False, dropna=False)
        .first()[group_keys + _existing_columns(frame, metadata)]
    )
    teams = (
        frame.groupby(group_keys, dropna=False)["team"]
        .agg(lambda values: "|".join(sorted({str(v) for v in values.dropna() if str(v)})))
        .rename("teams")
        .reset_index()
    )
    return totals.merge(dominant, on=group_keys, how="left").merge(teams, on=group_keys, how="left")


def _widen_situations(combined: pd.DataFrame, *, keys: list[str], metadata: list[str]) -> pd.DataFrame:
    all_rows = combined.loc[combined["situation"] == "all"].drop(columns="situation")
    five_rows = combined.loc[combined["situation"] == "5on5"].drop(columns="situation")
    value_columns = _existing_columns(
        combined, ["games_played", "icetime", *EVENT_SOURCE_COLUMNS, "teams", *metadata]
    )
    all_rows = all_rows[keys + value_columns].rename(
        columns={column: f"{column}_all" for column in value_columns}
    )
    five_rows = five_rows[keys + value_columns].rename(
        columns={column: f"{column}_5v5" for column in value_columns}
    )
    panel = all_rows.merge(five_rows, on=keys, how="outer", validate="one_to_one")

    for column in ["teams", *metadata]:
        all_column, five_column = f"{column}_all", f"{column}_5v5"
        if all_column in panel or five_column in panel:
            left = panel[all_column] if all_column in panel else pd.Series(pd.NA, index=panel.index)
            right = panel[five_column] if five_column in panel else pd.Series(pd.NA, index=panel.index)
            panel[column] = left.combine_first(right)
            panel = panel.drop(columns=[all_column, five_column], errors="ignore")

    panel["coverage_all"] = panel.get("icetime_all", pd.Series(np.nan, index=panel.index)).notna()
    panel["coverage_5v5"] = panel.get("icetime_5v5", pd.Series(np.nan, index=panel.index)).notna()
    panel["opportunity"] = panel.pop("icetime_all") / 60.0
    panel["opportunity_5v5"] = panel.pop("icetime_5v5") / 60.0
    for canonical in EVENT_SOURCE_COLUMNS:
        if f"{canonical}_all" in panel:
            panel = panel.rename(columns={f"{canonical}_all": canonical})
    if "games_played_all" in panel:
        panel = panel.rename(columns={"games_played_all": "games_played"})
    return panel


def _build_season_panel(frame: pd.DataFrame) -> pd.DataFrame:
    normalised = _normalise_source(frame, game_level=False)
    combined = _combine_stints(
        normalised,
        keys=["player_id", "season"],
        metadata=["name", "position"],
    )
    panel = _widen_situations(
        combined,
        keys=["player_id", "season"],
        metadata=["name", "position"],
    )
    panel["role"] = panel["position"].map(_role)
    return panel


def _build_game_panel(frame: pd.DataFrame) -> pd.DataFrame:
    normalised = _normalise_source(frame, game_level=True)
    # NHL game ids encode game type in positions 5-6: 02 is regular season.
    normalised = normalised.loc[normalised["game_id"].str.slice(4, 6) == "02"].copy()
    combined = _combine_stints(
        normalised,
        keys=["player_id", "season", "game_id"],
        metadata=["name", "position", "game_date", "opponent", "home_away"],
    )
    panel = _widen_situations(
        combined,
        keys=["player_id", "season", "game_id"],
        metadata=["name", "position", "game_date", "opponent", "home_away"],
    )
    panel["role"] = panel["position"].map(_role)
    panel["game_type"] = "regular"
    return panel


def _read_game_zip(path: Path) -> pd.DataFrame:
    required = {
        "playerId",
        "name",
        "gameId",
        "season",
        "playerTeam",
        "opposingTeam",
        "home_or_away",
        "gameDate",
        "position",
        "situation",
        "icetime",
        *EVENT_SOURCE_COLUMNS.values(),
    }
    pieces: list[pd.DataFrame] = []
    with zipfile.ZipFile(path) as archive:
        members = [member for member in archive.namelist() if member.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"Expected one CSV in {path}, found {members}")
        header = pd.read_csv(archive.open(members[0]), nrows=0).columns
        missing = sorted(required.difference(header))
        if missing:
            raise ValueError(f"MoneyPuck game archive is missing columns: {missing}")
        with archive.open(members[0]) as stream:
            for chunk in pd.read_csv(stream, usecols=sorted(required), chunksize=250_000, low_memory=False):
                keep = chunk["situation"].astype("string").str.lower().isin(SITUATIONS)
                game_ids = _clean_id(chunk["gameId"])
                keep &= game_ids.str.slice(4, 6) == "02"
                if keep.any():
                    pieces.append(chunk.loc[keep].copy())
    if not pieces:
        return pd.DataFrame(columns=sorted(required))
    return pd.concat(pieces, ignore_index=True)


def _load_latest_lookup(path: Path) -> pd.DataFrame:
    source = read_frame(path)
    required = {"playerId", "name", "birthDate"}
    missing = sorted(required.difference(source.columns))
    if missing:
        raise ValueError(f"MoneyPuck player lookup is missing columns: {missing}")
    result = pd.DataFrame(
        {
            "player_id": _clean_id(source["playerId"]),
            "name_latest_profile": source["name"].astype("string"),
            "birth_date_latest_profile": pd.to_datetime(source["birthDate"], errors="coerce"),
            "position_latest_profile": source.get("position", pd.Series(pd.NA, index=source.index)),
            "nationality": source.get("nationality", pd.Series(pd.NA, index=source.index)),
            "shoots_catches": source.get("shootsCatches", pd.Series(pd.NA, index=source.index)),
        }
    )
    if "height" in source:
        result["height_cm_latest_profile"] = source["height"].map(_parse_height_cm)
    else:
        result["height_cm_latest_profile"] = np.nan
    result["weight_kg_latest_profile"] = pd.to_numeric(source.get("weight"), errors="coerce") * 0.45359237
    result["profile_temporality"] = "current/undated MoneyPuck lookup; not season history"
    return result.dropna(subset=["player_id"]).drop_duplicates("player_id", keep="last")


def _load_official_bios(path: Path, season: int) -> pd.DataFrame:
    payload = json.loads(path.read_text())
    records = payload.get("data", []) if isinstance(payload, dict) else []
    source = pd.DataFrame.from_records(records)
    if source.empty or "playerId" not in source:
        return pd.DataFrame(columns=["player_id", "season", "birth_date_official", "height_cm", "weight_kg"])
    height_inches = pd.to_numeric(source.get("height"), errors="coerce")
    weight_pounds = pd.to_numeric(source.get("weight"), errors="coerce")
    result = pd.DataFrame(
        {
            "player_id": _clean_id(source["playerId"]),
            "season": int(season),
            "birth_date_official": pd.to_datetime(source.get("birthDate"), errors="coerce"),
            "height_cm": height_inches * 2.54,
            "weight_kg": weight_pounds * 0.45359237,
        }
    )
    return result.dropna(subset=["player_id"]).drop_duplicates(["player_id", "season"], keep="last")


def _attach_bios(
    panel: pd.DataFrame,
    official_bios: pd.DataFrame,
    latest_lookup: pd.DataFrame,
) -> pd.DataFrame:
    output = panel.merge(official_bios, on=["player_id", "season"], how="left", validate="many_to_one")
    stable = latest_lookup[["player_id", "birth_date_latest_profile", "nationality", "shoots_catches"]]
    output = output.merge(stable, on="player_id", how="left", validate="many_to_one")
    output["birth_date"] = output["birth_date_official"]
    missing_birth = output["birth_date"].isna()
    output.loc[missing_birth, "birth_date"] = output.loc[missing_birth, "birth_date_latest_profile"]
    output["age"] = _age_on_october_first(output["birth_date"], output["season"])
    output["age_anchor"] = output["season"].astype("Int64").astype("string") + "-10-01"
    has_physical = output[["height_cm", "weight_kg"]].notna().any(axis=1)
    output["physical_source"] = np.where(
        has_physical, "NHL Stats bios report for season-filtered skater universe", pd.NA
    )
    output["physical_measurement_scope"] = np.where(has_physical, PHYSICAL_TEMPORALITY, pd.NA)
    output["physical_is_confirmed_season_measurement"] = False
    return output.drop(columns=["birth_date_official", "birth_date_latest_profile"])


def _add_provenance(frame: pd.DataFrame, *, grain: str) -> pd.DataFrame:
    output = frame.copy()
    output["sport"] = "NHL"
    output["source"] = "MoneyPuck designated skater downloads"
    output["source_grain"] = grain
    output["coverage_scope"] = "appearance-based NHL regular-season skaters"
    output["zero_game_roster_players_included"] = False
    output["situations_included"] = "all and 5on5 retained separately; never summed"
    output["license_note"] = MONEYPUCK_LICENSE
    return output


def _qa(
    seasons_panel: pd.DataFrame,
    games_panel: pd.DataFrame,
    requested: list[int],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    event_columns = list(EVENT_SOURCE_COLUMNS)
    duplicate_seasons = int(seasons_panel.duplicated(["player_id", "season"]).sum())
    duplicate_games = int(games_panel.duplicated(["player_id", "season", "game_id"]).sum())
    negative_counts = {
        column: int((pd.to_numeric(seasons_panel[column], errors="coerce") < 0).sum())
        for column in event_columns
    }
    five_exceeds_all = {}
    for column in ["opportunity", *event_columns]:
        five = f"{column}_5v5"
        if five in seasons_panel:
            five_exceeds_all[column] = int(
                (
                    pd.to_numeric(seasons_panel[five], errors="coerce")
                    > pd.to_numeric(seasons_panel[column], errors="coerce") + 1e-9
                ).sum()
            )

    reconciliation: dict[str, Any] = {}
    if not games_panel.empty:
        game_totals = games_panel.groupby(["player_id", "season"], as_index=False)[
            ["opportunity", *event_columns]
        ].sum(min_count=1)
        comparison = seasons_panel[["player_id", "season", "opportunity", *event_columns]].merge(
            game_totals,
            on=["player_id", "season"],
            how="inner",
            suffixes=("_season", "_games"),
            validate="one_to_one",
        )
        for column in ["opportunity", *event_columns]:
            delta = (
                pd.to_numeric(comparison[f"{column}_season"], errors="coerce")
                - pd.to_numeric(comparison[f"{column}_games"], errors="coerce")
            ).abs()
            tolerance = 1e-5 if column == "opportunity" else 0.0
            reconciliation[column] = {
                "players_compared": int(delta.notna().sum()),
                "rows_different": int((delta.fillna(0) > tolerance).sum()),
                "max_absolute_difference": float(delta.max()) if delta.notna().any() else None,
            }

    requested_set = set(map(int, requested))
    observed_set = set(pd.to_numeric(seasons_panel["season"], errors="coerce").dropna().astype(int))
    multi_season_physical = seasons_panel.groupby("player_id").agg(
        seasons=("season", "nunique"),
        unique_heights=("height_cm", "nunique"),
        unique_weights=("weight_kg", "nunique"),
    )
    multi_season_physical = multi_season_physical.loc[multi_season_physical["seasons"] > 1]
    checks = {
        "season_player_unique": duplicate_seasons == 0,
        "game_player_unique": duplicate_games == 0,
        "no_negative_event_counts": not any(negative_counts.values()),
        "all_requested_seasons_present": requested_set.issubset(observed_set),
        "all_opportunity_nonnegative": bool((seasons_panel["opportunity"].dropna() >= 0).all()),
    }
    return {
        "checks": checks,
        "season_rows": int(len(seasons_panel)),
        "game_rows": int(len(games_panel)),
        "players": int(seasons_panel["player_id"].nunique()),
        "seasons_requested": sorted(requested_set),
        "seasons_observed": sorted(observed_set),
        "season_rows_by_year": {
            str(int(key)): int(value)
            for key, value in seasons_panel.groupby("season", dropna=False).size().items()
            if pd.notna(key)
        },
        "physical_coverage": {
            "height_pct": float(seasons_panel["height_cm"].notna().mean() * 100),
            "weight_pct": float(seasons_panel["weight_kg"].notna().mean() * 100),
            "age_pct": float(seasons_panel["age"].notna().mean() * 100),
        },
        "physical_temporality": {
            "interpretation": PHYSICAL_TEMPORALITY,
            "multi_season_players": int(len(multi_season_physical)),
            "players_with_height_variation": int((multi_season_physical["unique_heights"] > 1).sum()),
            "players_with_weight_variation": int((multi_season_physical["unique_weights"] > 1).sum()),
        },
        "duplicate_season_rows": duplicate_seasons,
        "duplicate_game_rows": duplicate_games,
        "negative_counts": negative_counts,
        "five_on_five_exceeds_all": five_exceeds_all,
        "game_to_season_reconciliation": reconciliation,
        "noncritical_source_errors": errors,
    }


def run(root: Path, seasons: list[int]) -> dict[str, Any]:
    """Download, process, validate, and analyse requested NHL start years."""
    root = Path(root).resolve()
    requested = sorted({int(season) for season in seasons})
    if not requested:
        raise ValueError("At least one NHL season start year is required")
    raw = root / "data" / "raw" / "nhl"
    processed = root / "data" / "processed" / "nhl"

    lookup_path = fetch(
        MONEYPUCK_BIOS_URL,
        raw / "moneypuck_all_players_lookup.csv",
        source="MoneyPuck player bios designated download",
        license_note=MONEYPUCK_LICENSE,
        timeout=180,
    )
    latest_lookup = _load_latest_lookup(lookup_path)
    save_frame(latest_lookup, processed / "latest_player_bios.parquet")

    season_panels: list[pd.DataFrame] = []
    game_panels: list[pd.DataFrame] = []
    official_pieces: list[pd.DataFrame] = []
    errors: list[dict[str, Any]] = []

    for season in requested:
        summary_path = fetch(
            MONEYPUCK_SUMMARY_URL.format(season=season),
            raw / f"moneypuck_skaters_{season}_regular.csv",
            source="MoneyPuck regular-season skater season summary designated download",
            license_note=MONEYPUCK_LICENSE,
            timeout=180,
        )
        season_panel = _build_season_panel(read_frame(summary_path))
        season_panel = season_panel.loc[season_panel["season"] == season].copy()
        season_panels.append(season_panel)

        season_id = f"{season}{season + 1}"
        try:
            official_path = fetch(
                NHL_BIOS_URL.format(season_id=season_id),
                raw / f"nhl_official_skater_bios_{season_id}.json",
                source="NHL Stats season-filtered skater bios report",
                license_note=NHL_LICENSE,
                timeout=180,
            )
            official_pieces.append(_load_official_bios(official_path, season))
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"season": season, "source": "NHL official bios", "error": str(exc)})

        try:
            game_path = fetch(
                MONEYPUCK_GAMES_URL.format(season=season),
                raw / f"moneypuck_skater_games_{season}.zip",
                source="MoneyPuck season player-game skater summary designated download",
                license_note=MONEYPUCK_LICENSE,
                timeout=600,
            )
            game_source = _read_game_zip(game_path)
            game_panel = _build_game_panel(game_source)
            game_panel = game_panel.loc[game_panel["season"] == season].copy()
            game_panels.append(game_panel)
        except (RuntimeError, ValueError, zipfile.BadZipFile) as exc:
            errors.append({"season": season, "source": "MoneyPuck player games", "error": str(exc)})

    seasons_panel = pd.concat(season_panels, ignore_index=True)
    games_panel = pd.concat(game_panels, ignore_index=True) if game_panels else pd.DataFrame()
    official_bios = (
        pd.concat(official_pieces, ignore_index=True)
        if official_pieces
        else pd.DataFrame(columns=["player_id", "season", "birth_date_official", "height_cm", "weight_kg"])
    )
    seasons_panel = _attach_bios(seasons_panel, official_bios, latest_lookup)
    seasons_panel = _add_provenance(seasons_panel, grain="one row per appearing skater-season")
    if not games_panel.empty:
        season_bios = seasons_panel[
            [
                "player_id",
                "season",
                "height_cm",
                "weight_kg",
                "age",
                "age_anchor",
                "physical_source",
                "physical_measurement_scope",
                "physical_is_confirmed_season_measurement",
                "nationality",
                "shoots_catches",
            ]
        ]
        games_panel = games_panel.merge(
            season_bios, on=["player_id", "season"], how="left", validate="many_to_one"
        )
        games_panel = _add_provenance(games_panel, grain="one row per appearing skater-regular-season game")
    else:
        # Preserve a useful schema even when optional game downloads fail.
        games_panel = pd.DataFrame(
            columns=[
                "player_id",
                "name",
                "season",
                "game_id",
                "role",
                "opportunity",
                "height_cm",
                "weight_kg",
                "age",
                *EVENT_SOURCE_COLUMNS,
            ]
        )

    seasons_panel = seasons_panel.sort_values(["season", "player_id"]).reset_index(drop=True)
    games_panel = games_panel.sort_values(
        _existing_columns(games_panel, ["season", "game_date", "game_id", "player_id"])
    ).reset_index(drop=True)
    save_frame(seasons_panel, processed / "player_seasons.parquet")
    save_frame(games_panel, processed / "player_games.parquet")

    qa = _qa(seasons_panel, games_panel, requested, errors)
    write_json(root / "reports" / "nhl" / "source_coverage.json", qa)
    write_json(root / "reports" / "nhl" / "qa.json", qa)
    analysis_result = analyze(root)
    result = {
        "sport": "nhl",
        "outputs": {
            "player_seasons": str((processed / "player_seasons.parquet").relative_to(root)),
            "player_games": str((processed / "player_games.parquet").relative_to(root)),
            "latest_player_bios": str((processed / "latest_player_bios.parquet").relative_to(root)),
        },
        "coverage": qa,
        "analysis": analysis_result,
    }
    write_json(root / "reports" / "nhl" / "pipeline.json", result)
    return result


def analyze(root: Path) -> dict[str, Any]:
    """Run the shared EDA/model workflow against the processed NHL panel."""
    from possession_lab.analysis import analyze_sport

    root = Path(root).resolve()
    panel = read_frame(root / "data" / "processed" / "nhl" / "player_seasons.parquet")
    return analyze_sport(
        panel,
        "nhl",
        root,
        metrics={
            "takeaways": "takeaways",
            "blocks": "blocks",
            "hits": "hits",
            "faceoff_wins": "faceoff_wins",
        },
        physical_features=["height_cm", "weight_kg", "age"],
        limitations=[
            "Coverage is appearance-based; zero-game roster players are absent.",
            "MoneyPuck all-situations includes 5-on-5; the pipeline keeps the views separate.",
            "NHL bio height/weight measurement dates are unavailable and are not annual measurements.",
            "NHL EDGE top speed is not included: official pages expose leaderboards and per-player "
            "detail, not a supported full-roster bulk file; this baseline covers listed size and age, "
            "not current skating tests.",
            "League-wide NHL bios do not publish wingspan, arm length, or leg length.",
            "Public NHL data do not provide league-wide reaction time, agility, or cognitive tests.",
            "Takeaways are scorer-recorded events and do not capture every possession recovery.",
        ],
        opportunity_unit="minutes",
    )
