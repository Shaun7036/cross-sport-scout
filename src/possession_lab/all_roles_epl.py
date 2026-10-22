"""Build the broad-role Premier League research panel.

The cached five-season community archive supports only the public FPL role
families (GK/DEF/MID/FWD).  It does not justify pretending that center-back,
fullback, defensive midfield and winger are historically observed labels.  The
result is therefore a broad-role research prototype with an explicit rights and
team-context warning; no additional scraping occurs here.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from possession_lab.epl_wikidata import load_and_attach_wikidata
from possession_lab.io import write_json

ROLE_VALUES = {"GK", "DEF", "MID", "FWD"}
COUNT_COLUMNS = [
    "goals_scored",
    "assists",
    "clean_sheets",
    "goals_conceded",
    "saves",
    "yellow_cards",
    "red_cards",
    "penalties_saved",
]
ACTIVITY_COLUMNS = ["creativity", "threat"]
OPTIONAL_SUM_COLUMNS = [
    "expected_goals",
    "expected_assists",
    "expected_goal_involvements",
    "expected_goals_conceded",
    "influence",
    "ict_index",
    "starts",
    "clearances_blocks_interceptions",
    "defensive_contribution",
    "recoveries",
    "tackles",
]


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    left = pd.to_numeric(numerator, errors="coerce").astype(float)
    right = pd.to_numeric(denominator, errors="coerce").astype(float)
    return left.div(right.where(right > 0))


def _season_label(season: int) -> str:
    return f"{season}-{str(season + 1)[-2:]}"


def _mode_or_join(values: pd.Series) -> str | pd.NA:
    clean = values.dropna().astype(str)
    if clean.empty:
        return pd.NA
    modes = clean.mode()
    return modes.iloc[0] if len(modes) else clean.iloc[-1]


def _final_panel_wikidata_audit(
    merged: pd.DataFrame,
    supported_role: pd.Series,
    audit: dict,
) -> dict:
    """Align enrichment coverage with the rows retained by the model panel."""
    if audit.get("status") != "applied":
        return audit
    retained = merged.loc[supported_role]
    height_before = retained["_height_present_before_wikidata"].fillna(False).astype(bool)
    weight_before = retained["_weight_present_before_wikidata"].fillna(False).astype(bool)
    height_after = pd.to_numeric(retained["height_cm"], errors="coerce").notna()
    weight_after = pd.to_numeric(retained["weight_kg"], errors="coerce").notna()
    return {
        **audit,
        "canonical_rows_considered": int(len(merged)),
        "rows": int(len(retained)),
        "rows_excluded_no_supported_role": int((~supported_role).sum()),
        "rows_filled_height": int((~height_before & height_after).sum()),
        "rows_filled_weight": int((~weight_before & weight_after).sum()),
        "height_rows_before": int(height_before.sum()),
        "height_rows_after": int(height_after.sum()),
        "weight_rows_before": int(weight_before.sum()),
        "weight_rows_after": int(weight_after.sum()),
    }


def _aggregate_season(path: Path, season: int) -> pd.DataFrame:
    source = pd.read_csv(path, low_memory=False)
    required = {"element", "name", "position", "minutes", *COUNT_COLUMNS, *ACTIVITY_COLUMNS}
    missing = sorted(required.difference(source.columns))
    if missing:
        raise ValueError(f"EPL gameweek source is missing columns: {missing}")

    source["element"] = pd.to_numeric(source["element"], errors="coerce").astype("Int64")
    source["minutes"] = pd.to_numeric(source["minutes"], errors="coerce")
    present_optional = [column for column in OPTIONAL_SUM_COLUMNS if column in source]
    for column in COUNT_COLUMNS + ACTIVITY_COLUMNS + present_optional:
        source[column] = pd.to_numeric(source[column], errors="coerce")

    # FPL gameweek rows enumerate a player's fixture.  A true zero is observed
    # for the common-core count fields; absent cells remain missing.
    grouped = source.groupby("element", dropna=False)
    totals = grouped[
        ["minutes", *COUNT_COLUMNS, *ACTIVITY_COLUMNS, *present_optional]
    ].sum(min_count=1)
    for column in OPTIONAL_SUM_COLUMNS:
        if column not in totals:
            totals[column] = np.nan
    totals["games"] = grouped["minutes"].apply(lambda values: int(values.fillna(0).gt(0).sum()))
    totals["name"] = grouped["name"].agg(_mode_or_join)
    totals["position"] = grouped["position"].agg(_mode_or_join)
    if "team" in source:
        totals["team"] = grouped["team"].agg(_mode_or_join)
    else:
        totals["team"] = pd.NA
    totals = totals.reset_index().rename(columns={"element": "season_element_id"})
    totals["season"] = int(season)
    return totals


def _derive_rates(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    # Older FPL seasons do not expose every modern expected or defensive field.
    # Keep the historical rows usable while making the missing coverage explicit.
    for column in OPTIONAL_SUM_COLUMNS:
        if column not in result:
            result[column] = np.nan
    minutes = pd.to_numeric(result["opportunity"], errors="coerce")
    per_90 = minutes.div(90.0)
    result["goals_per_90"] = _safe_divide(result["goals_scored"], per_90)
    result["assists_per_90"] = _safe_divide(result["assists"], per_90)
    result["saves_per_90"] = _safe_divide(result["saves"], per_90)
    result["goals_conceded_per_90"] = _safe_divide(result["goals_conceded"], per_90)
    result["penalties_saved_per_90"] = _safe_divide(result["penalties_saved"], per_90)
    result["creativity_per_90"] = _safe_divide(result["creativity"], per_90)
    result["threat_per_90"] = _safe_divide(result["threat"], per_90)
    result["expected_goals_per_90"] = _safe_divide(result["expected_goals"], per_90)
    result["expected_assists_per_90"] = _safe_divide(
        result["expected_assists"], per_90
    )
    result["expected_goal_involvements_per_90"] = _safe_divide(
        result["expected_goal_involvements"], per_90
    )
    result["expected_goals_conceded_per_90"] = _safe_divide(
        result["expected_goals_conceded"], per_90
    )
    result["influence_per_90"] = _safe_divide(result["influence"], per_90)
    result["ict_index_per_90"] = _safe_divide(result["ict_index"], per_90)
    result["finishing_over_expected_per_90"] = _safe_divide(
        pd.to_numeric(result["goals_scored"], errors="coerce")
        - pd.to_numeric(result["expected_goals"], errors="coerce"),
        per_90,
    )
    result["goal_prevention_over_expected_per_90"] = _safe_divide(
        pd.to_numeric(result["expected_goals_conceded"], errors="coerce")
        - pd.to_numeric(result["goals_conceded"], errors="coerce"),
        per_90,
    )
    result["defensive_actions_per_90"] = _safe_divide(
        pd.to_numeric(result["clearances_blocks_interceptions"], errors="coerce")
        + pd.to_numeric(result["recoveries"], errors="coerce")
        + pd.to_numeric(result["tackles"], errors="coerce"),
        per_90,
    )
    result["defensive_contribution_per_90"] = _safe_divide(
        result["defensive_contribution"], per_90
    )
    result["start_rate"] = _safe_divide(result["starts"], result["games"])
    result["cards_per_90"] = _safe_divide(
        pd.to_numeric(result["yellow_cards"], errors="coerce")
        + 2.0 * pd.to_numeric(result["red_cards"], errors="coerce"),
        per_90,
    )
    result["clean_sheet_rate"] = _safe_divide(result["clean_sheets"], result["games"])
    return result


def build_epl_all_roles_panel(
    root: Path | str,
    seasons=range(2021, 2026),
) -> pd.DataFrame:
    root = Path(root)
    selected_seasons = {int(value) for value in seasons}
    canonical_path = root / "data" / "processed" / "epl" / "player_seasons.parquet"
    if not canonical_path.exists():
        raise FileNotFoundError(f"Run the base EPL pipeline first: {canonical_path}")
    canonical = pd.read_parquet(canonical_path)
    canonical = canonical.loc[canonical["season"].isin(selected_seasons)].copy()
    canonical["_height_present_before_wikidata"] = pd.to_numeric(
        canonical["height_cm"], errors="coerce"
    ).notna()
    canonical["_weight_present_before_wikidata"] = pd.to_numeric(
        canonical["weight_kg"], errors="coerce"
    ).notna()
    canonical, wikidata_audit = load_and_attach_wikidata(root, canonical)
    canonical["season_element_id"] = pd.to_numeric(
        canonical["season_element_id"], errors="coerce"
    ).astype("Int64")

    pieces: list[pd.DataFrame] = []
    for season in sorted(selected_seasons):
        source_path = (
            root
            / "data"
            / "raw"
            / "epl"
            / "vaastav"
            / _season_label(season)
            / "merged_gw.csv"
        )
        if not source_path.exists():
            raise FileNotFoundError(f"Missing cached EPL season source: {source_path}")
        pieces.append(_aggregate_season(source_path, season))
    aggregated = pd.concat(pieces, ignore_index=True)

    identity_columns = [
        "player_id",
        "season",
        "season_element_id",
        "name",
        "role",
        "team",
        "height_cm",
        "weight_kg",
        "age",
        "physical_temporality",
        "physical_source",
        "wikidata_qid",
        "wikidata_match_method",
        "wikidata_physical_used",
        "_height_present_before_wikidata",
        "_weight_present_before_wikidata",
    ]
    base = canonical.reindex(columns=identity_columns)
    merged = base.merge(
        aggregated,
        on=["season", "season_element_id"],
        how="left",
        suffixes=("", "_raw"),
        validate="one_to_one",
    )
    merged["name"] = merged["name_raw"].combine_first(merged["name"])
    merged["position"] = merged["position"].where(
        merged["position"].isin(ROLE_VALUES), merged["role"]
    )
    merged["role"] = merged["position"].where(merged["position"].isin(ROLE_VALUES))
    merged["team"] = merged["team_raw"].combine_first(merged["team"])
    merged["sport"] = "epl"
    merged["opportunity"] = pd.to_numeric(merged["minutes"], errors="coerce")
    merged = _derive_rates(merged)
    merged["source_tier"] = "cached_community_fpl_research_only"
    merged["rights_warning"] = (
        "Local research prototype; community archive accessibility is not a grant of EPL/FPL "
        "redistribution or commercial-model rights. Do not publish raw data without review."
    )
    merged["role_granularity_warning"] = (
        "Only broad FPL GK/DEF/MID/FWD labels are observed; granular deployment is withheld."
    )

    keep = [
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
        *COUNT_COLUMNS,
        *ACTIVITY_COLUMNS,
        *OPTIONAL_SUM_COLUMNS,
        "goals_per_90",
        "assists_per_90",
        "saves_per_90",
        "goals_conceded_per_90",
        "penalties_saved_per_90",
        "creativity_per_90",
        "threat_per_90",
        "expected_goals_per_90",
        "expected_assists_per_90",
        "expected_goal_involvements_per_90",
        "expected_goals_conceded_per_90",
        "influence_per_90",
        "ict_index_per_90",
        "finishing_over_expected_per_90",
        "goal_prevention_over_expected_per_90",
        "defensive_actions_per_90",
        "defensive_contribution_per_90",
        "start_rate",
        "cards_per_90",
        "clean_sheet_rate",
        "physical_temporality",
        "physical_source",
        "wikidata_qid",
        "wikidata_match_method",
        "wikidata_physical_used",
        "source_tier",
        "rights_warning",
        "role_granularity_warning",
    ]
    supported_role = merged["role"].isin(ROLE_VALUES)
    wikidata_audit = _final_panel_wikidata_audit(merged, supported_role, wikidata_audit)
    write_json(
        root / "reports" / "epl" / "wikidata_all_roles_application.json",
        wikidata_audit,
    )

    result = merged.reindex(columns=keep)
    result = result.loc[supported_role].copy()
    if result.duplicated(["player_id", "season"]).any():
        raise ValueError("EPL all-role panel has duplicate player-season rows")
    return result.sort_values(["season", "role", "player_id"]).reset_index(drop=True)
