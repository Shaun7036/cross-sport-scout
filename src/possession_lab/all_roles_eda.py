"""Compact, reproducible EDA for the all-role panels and model evidence."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from possession_lab.all_roles_paths import (
    observed_scores_missing_message,
    observed_scores_path,
)
from possession_lab.io import write_json

SPORT_INSIGHT_SEASON = 2025


def _numeric(source: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(source[column], errors="coerce")


def _weighted_rate(
    source: pd.DataFrame,
    metric: str,
    opportunity: str,
    multiplier: float,
) -> float | None:
    denominator = _numeric(source, opportunity).sum(min_count=1)
    numerator = _numeric(source, metric).sum(min_count=1)
    if pd.isna(denominator) or denominator <= 0 or pd.isna(numerator):
        return None
    return round(float(numerator / denominator * multiplier), 2)


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return round(float(numerator / denominator), 2)


def sport_insight_summaries(
    panel: pd.DataFrame,
    *,
    season: int = SPORT_INSIGHT_SEASON,
) -> dict:
    """Return the exact, opportunity-adjusted values used by the sport EDA charts.

    The summaries intentionally use one frozen season. This avoids counting the same
    athlete several times and makes every chart a transparent description of the
    2025 snapshot rather than a causal or cross-sport performance claim.
    """

    required = {
        "sport",
        "role",
        "season",
        "opportunity",
        "defensive_opportunity",
        "sacks",
        "passes_defended",
        "steals",
        "blocks",
        "hits",
        "height_cm",
        "weight_kg",
    }
    missing = sorted(required.difference(panel.columns))
    if missing:
        raise ValueError(f"All-role panel is missing sport-insight columns: {missing}")

    source = panel.loc[pd.to_numeric(panel["season"], errors="coerce").eq(season)].copy()
    nfl = source.loc[
        source["sport"].eq("nfl")
        & source["role"].isin(["EDGE", "IDL", "LB", "S", "CB"])
        & _numeric(source, "defensive_opportunity").ge(200)
    ].copy()
    nfl_rows = []
    for role in ["EDGE", "IDL", "LB", "S", "CB"]:
        part = nfl.loc[nfl["role"].eq(role)]
        nfl_rows.append(
            {
                "role": role,
                "players": int(len(part)),
                "defensive_opportunities": float(
                    _numeric(part, "defensive_opportunity").sum()
                ),
                "sacks_per_1000": _weighted_rate(
                    part, "sacks", "defensive_opportunity", 1000
                ),
                "passes_defended_per_1000": _weighted_rate(
                    part, "passes_defended", "defensive_opportunity", 1000
                ),
            }
        )
    nfl_by_role = {row["role"]: row for row in nfl_rows}

    nba = source.loc[
        source["sport"].eq("nba") & _numeric(source, "opportunity").ge(500)
    ].copy()
    nba_rows = []
    for role in ["guard", "forward", "center"]:
        part = nba.loc[nba["role"].eq(role)]
        nba_rows.append(
            {
                "role": role,
                "players": int(len(part)),
                "minutes": float(_numeric(part, "opportunity").sum()),
                "steals_per_36": _weighted_rate(part, "steals", "opportunity", 36),
                "blocks_per_36": _weighted_rate(part, "blocks", "opportunity", 36),
            }
        )
    nba_by_role = {row["role"]: row for row in nba_rows}

    nhl = source.loc[
        source["sport"].eq("nhl")
        & source["role"].isin(["defense", "center", "left_wing", "right_wing"])
        & _numeric(source, "opportunity").ge(600)
    ].copy()
    nhl_rows = []
    for role in ["defense", "center", "left_wing", "right_wing"]:
        part = nhl.loc[nhl["role"].eq(role)]
        nhl_rows.append(
            {
                "role": role,
                "players": int(len(part)),
                "minutes": float(_numeric(part, "opportunity").sum()),
                "blocks_per_60": _weighted_rate(part, "blocks", "opportunity", 60),
                "hits_per_60": _weighted_rate(part, "hits", "opportunity", 60),
            }
        )
    nhl_by_role = {row["role"]: row for row in nhl_rows}

    epl_season = source.loc[source["sport"].eq("epl")].copy()
    epl = epl_season.dropna(subset=["height_cm", "weight_kg"]).copy()
    epl = epl.loc[
        _numeric(epl, "height_cm").between(140, 230)
        & _numeric(epl, "weight_kg").between(35, 230)
    ]
    epl_rows = []
    for role in ["GK", "DEF", "FWD", "MID"]:
        part = epl.loc[epl["role"].eq(role)]
        epl_rows.append(
            {
                "role": role,
                "players": int(len(part)),
                "median_height_cm": round(float(_numeric(part, "height_cm").median()), 2)
                if len(part)
                else None,
                "median_weight_kg": round(float(_numeric(part, "weight_kg").median()), 2)
                if len(part)
                else None,
            }
        )
    epl_by_role = {row["role"]: row for row in epl_rows}
    epl_correlation = _numeric(epl, "height_cm").corr(_numeric(epl, "weight_kg"))
    epl_coverage = len(epl) / len(epl_season) if len(epl_season) else 0.0

    return {
        "schema_version": "1.0.0",
        "season": int(season),
        "nfl": {
            "filter": "At least 200 observed defensive opportunities",
            "unit": "events per 1,000 defensive opportunities",
            "players": int(len(nfl)),
            "roles": nfl_rows,
            "edge_to_cornerback_sack_rate_ratio": _ratio(
                nfl_by_role["EDGE"]["sacks_per_1000"],
                nfl_by_role["CB"]["sacks_per_1000"],
            ),
            "cornerback_to_edge_pass_defended_rate_ratio": _ratio(
                nfl_by_role["CB"]["passes_defended_per_1000"],
                nfl_by_role["EDGE"]["passes_defended_per_1000"],
            ),
        },
        "nba": {
            "filter": "At least 500 minutes",
            "unit": "events per 36 minutes",
            "players": int(len(nba)),
            "roles": nba_rows,
            "center_to_guard_block_rate_ratio": _ratio(
                nba_by_role["center"]["blocks_per_36"],
                nba_by_role["guard"]["blocks_per_36"],
            ),
            "guard_to_center_steal_rate_ratio": _ratio(
                nba_by_role["guard"]["steals_per_36"],
                nba_by_role["center"]["steals_per_36"],
            ),
        },
        "nhl": {
            "filter": "Non-goalies with at least 600 minutes",
            "unit": "events per 60 minutes",
            "players": int(len(nhl)),
            "roles": nhl_rows,
            "defense_to_left_wing_block_rate_ratio": _ratio(
                nhl_by_role["defense"]["blocks_per_60"],
                nhl_by_role["left_wing"]["blocks_per_60"],
            ),
            "left_wing_to_defense_hit_rate_ratio": _ratio(
                nhl_by_role["left_wing"]["hits_per_60"],
                nhl_by_role["defense"]["hits_per_60"],
            ),
        },
        "epl": {
            "filter": "Rows with both a plausible listed height and listed weight",
            "unit": "centimeters and kilograms",
            "season_rows": int(len(epl_season)),
            "complete_build_rows": int(len(epl)),
            "complete_build_coverage": round(float(epl_coverage), 4),
            "height_weight_correlation": round(float(epl_correlation), 3)
            if pd.notna(epl_correlation)
            else None,
            "roles": epl_rows,
            "goalkeeper_minus_midfielder_median_height_cm": round(
                float(
                    epl_by_role["GK"]["median_height_cm"]
                    - epl_by_role["MID"]["median_height_cm"]
                ),
                2,
            )
            if epl_by_role["GK"]["median_height_cm"] is not None
            and epl_by_role["MID"]["median_height_cm"] is not None
            else None,
            "goalkeeper_minus_midfielder_median_weight_kg": round(
                float(
                    epl_by_role["GK"]["median_weight_kg"]
                    - epl_by_role["MID"]["median_weight_kg"]
                ),
                2,
            )
            if epl_by_role["GK"]["median_weight_kg"] is not None
            and epl_by_role["MID"]["median_weight_kg"] is not None
            else None,
        },
    }


def role_summary(scored: pd.DataFrame) -> pd.DataFrame:
    required = {"sport", "role", "player_id", "season", "opportunity"}
    missing = sorted(required.difference(scored.columns))
    if missing:
        raise ValueError(f"Observed all-role table is missing columns: {missing}")
    source = scored.copy()
    source["positive_opportunity"] = pd.to_numeric(
        source["opportunity"], errors="coerce"
    ).gt(0)
    source["scored"] = pd.to_numeric(
        source.get("observed_role_percentile"), errors="coerce"
    ).notna()
    source["eligible"] = source.get("target_status", pd.Series(index=source.index)).eq(
        "eligible"
    )
    source["height_observed"] = pd.to_numeric(
        source.get("height_cm"), errors="coerce"
    ).notna()
    source["weight_observed"] = pd.to_numeric(
        source.get("weight_kg"), errors="coerce"
    ).notna()
    grouped = source.groupby(["sport", "role"], dropna=False)
    summary = grouped.agg(
        player_seasons=("player_id", "size"),
        athletes=("player_id", "nunique"),
        first_season=("season", "min"),
        last_season=("season", "max"),
        positive_opportunity_rows=("positive_opportunity", "sum"),
        eligible_rows=("eligible", "sum"),
        scored_rows=("scored", "sum"),
        median_opportunity=("opportunity", "median"),
        height_coverage=("height_observed", "mean"),
        weight_coverage=("weight_observed", "mean"),
        observed_score_mean=("observed_role_percentile", "mean"),
        observed_score_median=("observed_role_percentile", "median"),
    ).reset_index()
    return summary.sort_values(["sport", "role"], na_position="last").reset_index(drop=True)


def _save_role_counts(summary: pd.DataFrame, path: Path) -> None:
    labels = summary["sport"].astype(str).str.upper() + " · " + summary["role"].astype(str)
    order = np.argsort(summary["player_seasons"].to_numpy())
    figure, axis = plt.subplots(figsize=(10, max(6, len(summary) * 0.28)))
    axis.barh(labels.iloc[order], summary["player_seasons"].iloc[order], color="#315f72")
    axis.set_xlabel("Player-seasons")
    axis.set_title("All-role cohort size, 2021–2025")
    axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _save_score_distributions(scored: pd.DataFrame, path: Path) -> None:
    sports = ["nfl", "nba", "nhl", "epl"]
    figure, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True, sharey=True)
    for sport, axis in zip(sports, axes.flat):
        part = scored.loc[scored["sport"].eq(sport)]
        for role, role_part in part.groupby("role"):
            values = pd.to_numeric(
                role_part["observed_role_percentile"], errors="coerce"
            ).dropna()
            if len(values):
                axis.hist(values, bins=np.linspace(0, 100, 21), histtype="step", label=str(role))
        axis.set_title(sport.upper())
        axis.set_xlim(0, 100)
        axis.grid(axis="y", alpha=0.2)
        axis.legend(fontsize=7, ncol=2, frameon=False)
    figure.supxlabel("Observed role percentile")
    figure.supylabel("Player-seasons")
    figure.suptitle("Observed quality distributions include eligible and shrunk low-sample rows")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _save_physical_map(scored: pd.DataFrame, path: Path) -> None:
    latest = scored.sort_values("season").groupby(["sport", "player_id"], as_index=False).tail(1)
    latest = latest.dropna(subset=["height_cm", "weight_kg"])
    latest = latest.loc[
        latest["height_cm"].between(140, 230) & latest["weight_kg"].between(35, 230)
    ]
    figure, axis = plt.subplots(figsize=(9, 6))
    colors = {"nfl": "#1f4e5f", "nba": "#aa4a44", "nhl": "#447a57", "epl": "#8b6b3f"}
    for sport, part in latest.groupby("sport"):
        axis.scatter(
            part["height_cm"],
            part["weight_kg"],
            s=10,
            alpha=0.28,
            label=sport.upper(),
            color=colors.get(str(sport)),
        )
    axis.set_xlabel("Listed height (cm)")
    axis.set_ylabel("Listed weight (kg)")
    axis.set_title("Latest listed builds by league (not annual body measurements)")
    axis.legend(frameon=False)
    axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _save_dual_rate_chart(
    rows: list[dict],
    path: Path,
    *,
    title: str,
    panels: list[tuple[str, str, str]],
    role_labels: dict[str, str] | None = None,
    method_note: str,
) -> None:
    role_labels = role_labels or {}
    labels = [role_labels.get(str(row["role"]), str(row["role"])) for row in rows]
    figure, axes = plt.subplots(1, 2, figsize=(10.5, 5.5), sharey=True)
    for axis, (column, panel_title, color) in zip(axes, panels):
        values = [
            np.nan if row.get(column) is None else float(row[column])
            for row in rows
        ]
        bars = axis.barh(labels, values, color=color)
        axis.bar_label(bars, fmt="%.2f", padding=3, fontsize=9)
        finite = [value for value in values if np.isfinite(value)]
        upper = max(finite, default=1.0)
        axis.set_xlim(0, upper * 1.22 if upper > 0 else 1.0)
        axis.set_title(panel_title)
        axis.set_xlabel("Rate")
        axis.grid(axis="x", alpha=0.18)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].invert_yaxis()
    figure.suptitle(title)
    figure.text(0.5, 0.015, method_note, ha="center", fontsize=9, color="#4d5a5f")
    figure.tight_layout(rect=(0, 0.055, 1, 0.94))
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _save_nfl_role_disruption(insights: dict, path: Path) -> None:
    _save_dual_rate_chart(
        insights["nfl"]["roles"],
        path,
        title="NFL disruption is role-specific (2025)",
        panels=[
            ("sacks_per_1000", "Sacks per 1,000 defensive opportunities", "#315f72"),
            (
                "passes_defended_per_1000",
                "Passes defended per 1,000 defensive opportunities",
                "#a8643f",
            ),
        ],
        role_labels={
            "EDGE": "Edge",
            "IDL": "Interior line",
            "LB": "Linebacker",
            "S": "Safety",
            "CB": "Cornerback",
        },
        method_note="Players with at least 200 observed defensive opportunities; rates use role totals, not averages of player rates.",
    )


def _save_nba_role_disruption(insights: dict, path: Path) -> None:
    _save_dual_rate_chart(
        insights["nba"]["roles"],
        path,
        title="NBA roles create turnovers in different ways (2025)",
        panels=[
            ("steals_per_36", "Steals per 36 minutes", "#315f72"),
            ("blocks_per_36", "Blocks per 36 minutes", "#a8643f"),
        ],
        role_labels={"guard": "Guard", "forward": "Forward", "center": "Center"},
        method_note="Players with at least 500 minutes; rates use role totals, not averages of player rates.",
    )


def _save_nhl_role_physicality(insights: dict, path: Path) -> None:
    _save_dual_rate_chart(
        insights["nhl"]["roles"],
        path,
        title="NHL physical play splits between blocking and contact (2025)",
        panels=[
            ("blocks_per_60", "Blocks per 60 minutes", "#315f72"),
            ("hits_per_60", "Hits per 60 minutes", "#a8643f"),
        ],
        role_labels={
            "defense": "Defense",
            "center": "Center",
            "left_wing": "Left wing",
            "right_wing": "Right wing",
        },
        method_note="Non-goalies with at least 600 minutes; rates use role totals, not averages of player rates.",
    )


def _save_epl_build_by_role(
    scored: pd.DataFrame,
    insights: dict,
    path: Path,
    *,
    season: int = SPORT_INSIGHT_SEASON,
) -> None:
    source = scored.loc[
        scored["sport"].eq("epl")
        & pd.to_numeric(scored["season"], errors="coerce").eq(season)
    ].copy()
    source["height_cm"] = _numeric(source, "height_cm")
    source["weight_kg"] = _numeric(source, "weight_kg")
    source = source.dropna(subset=["height_cm", "weight_kg"])
    source = source.loc[
        source["height_cm"].between(140, 230)
        & source["weight_kg"].between(35, 230)
    ].sort_values(["role", "height_cm", "weight_kg"])

    colors = {"GK": "#315f72", "DEF": "#4f8064", "FWD": "#a8643f", "MID": "#8b6b3f"}
    labels = {"GK": "Goalkeeper", "DEF": "Defender", "FWD": "Forward", "MID": "Midfielder"}
    figure, axis = plt.subplots(figsize=(9, 6))
    role_handles: list[Line2D] = []
    for role in ["GK", "DEF", "FWD", "MID"]:
        part = source.loc[source["role"].eq(role)]
        if part.empty:
            continue
        axis.scatter(
            part["height_cm"],
            part["weight_kg"],
            s=18,
            alpha=0.30,
            color=colors[role],
        )
        axis.scatter(
            [part["height_cm"].median()],
            [part["weight_kg"].median()],
            s=105,
            marker="X",
            color=colors[role],
            edgecolor="white",
            linewidth=0.9,
            zorder=5,
        )
        role_handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="none",
                markerfacecolor=colors[role],
                markeredgecolor="none",
                label=labels[role],
            )
        )
    role_handles.append(
        Line2D(
            [0],
            [0],
            marker="X",
            linestyle="none",
            markerfacecolor="#263238",
            markeredgecolor="white",
            label="Role median",
        )
    )
    epl = insights["epl"]
    coverage = float(epl["complete_build_coverage"]) * 100
    axis.set_xlabel("Listed height (cm)")
    axis.set_ylabel("Listed weight (kg)")
    axis.set_title("Premier League listed build by broad role (2025)")
    axis.legend(handles=role_handles, frameon=False, ncol=2)
    axis.grid(alpha=0.16)
    axis.spines[["top", "right"]].set_visible(False)
    figure.text(
        0.5,
        0.015,
        f"{epl['complete_build_rows']:,} of {epl['season_rows']:,} rows have both fields ({coverage:.1f}% coverage); X marks each role median.",
        ha="center",
        fontsize=9,
        color="#4d5a5f",
    )
    figure.tight_layout(rect=(0, 0.055, 1, 1))
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _model_evidence_rows(report: dict) -> pd.DataFrame:
    rows = []
    for family in [
        "physical_models",
        "native_forecast_models",
        "native_profile_models",
    ]:
        for key, head in report.get(family, {}).items():
            evaluation = head.get("evaluation", {})
            frozen = evaluation.get("frozen", {})
            neutral = evaluation.get("neutral_50", {})
            build_only = evaluation.get("build_only", {})
            unseen_history = evaluation.get(
                "unseen_history_slice",
                evaluation.get("frozen_newcomers", {}),
            )
            rows.append(
                {
                    "family": family,
                    "role_key": key,
                    "status": head.get("status"),
                    "evidence_gate": head.get("evidence_gate"),
                    "profile_increment_gate": head.get("profile_increment_gate"),
                    "forecast_support": head.get("forecast_support"),
                    "deployment_support": head.get("deployment_support"),
                    "test_n": frozen.get("n"),
                    "model_mae": frozen.get("mae"),
                    "neutral_mae": neutral.get("mae"),
                    "build_only_mae": build_only.get("mae"),
                    "unseen_history_n": unseen_history.get("n"),
                    "usable_rows": head.get("usable_coverage", {}).get("usable_rows"),
                    "usable_fraction_of_eligible_labels": head.get(
                        "usable_coverage", {}
                    ).get("usable_fraction_of_eligible_labels"),
                }
            )
    return pd.DataFrame(rows)


def _save_profile_increment_chart(model_rows: pd.DataFrame, path: Path) -> None:
    profile = model_rows.loc[
        model_rows["family"].eq("native_profile_models")
        & pd.to_numeric(model_rows["model_mae"], errors="coerce").notna()
        & pd.to_numeric(model_rows["build_only_mae"], errors="coerce").notna()
    ].copy()
    if profile.empty:
        return
    profile["mae_improvement"] = (
        pd.to_numeric(profile["build_only_mae"], errors="coerce")
        - pd.to_numeric(profile["model_mae"], errors="coerce")
    )
    profile = profile.sort_values("mae_improvement")
    supported = profile["profile_increment_gate"].eq("supported")
    colors = np.where(supported, "#2f765d", "#9b7b50")
    figure, axis = plt.subplots(figsize=(10, max(6, len(profile) * 0.30)))
    axis.barh(profile["role_key"], profile["mae_improvement"], color=colors)
    axis.axvline(0, color="#263238", linewidth=1)
    axis.set_xlabel("Held-out MAE improvement over build alone (percentile points)")
    axis.set_title("Does the prior playing profile add next-season signal?")
    axis.legend(
        handles=[
            Patch(color="#2f765d", label="Passed the profile-over-build evidence gate"),
            Patch(color="#9b7b50", label="Did not pass or lacked enough evidence"),
        ],
        frameon=False,
        loc="lower right",
    )
    axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def build_all_roles_eda(root: Path | str) -> dict:
    root = Path(root)
    scored_path = observed_scores_path(root)
    if not scored_path.exists():
        raise FileNotFoundError(observed_scores_missing_message(root, scored_path))
    scored = pd.read_parquet(scored_path)
    report_dir = root / "reports" / "all_roles"
    figure_dir = report_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    summary = role_summary(scored)
    summary.to_csv(report_dir / "role_summary.csv", index=False)
    _save_role_counts(summary, figure_dir / "role_cohort_counts.png")
    _save_score_distributions(scored, figure_dir / "observed_score_distributions.png")
    _save_physical_map(scored, figure_dir / "listed_build_map.png")

    sport_insights = sport_insight_summaries(scored)
    sport_insights_path = report_dir / "sport_insights.json"
    write_json(sport_insights_path, sport_insights)
    _save_nfl_role_disruption(
        sport_insights,
        figure_dir / "nfl_role_disruption_2025.png",
    )
    _save_nba_role_disruption(
        sport_insights,
        figure_dir / "nba_role_disruption_2025.png",
    )
    _save_nhl_role_physicality(
        sport_insights,
        figure_dir / "nhl_role_physicality_2025.png",
    )
    _save_epl_build_by_role(
        scored,
        sport_insights,
        figure_dir / "epl_build_by_role_2025.png",
    )

    evaluation_path = report_dir / "model_evaluation.json"
    model_rows = pd.DataFrame()
    if evaluation_path.exists():
        model_rows = _model_evidence_rows(json.loads(evaluation_path.read_text()))
        model_rows.to_csv(report_dir / "model_evidence_summary.csv", index=False)
        _save_profile_increment_chart(
            model_rows,
            figure_dir / "profile_increment_vs_build.png",
        )

    result = {
        "rows": int(len(scored)),
        "scored_rows": int(scored["observed_role_percentile"].notna().sum()),
        "roles": int(len(summary)),
        "role_summary": str((report_dir / "role_summary.csv").relative_to(root)),
        "sport_insights": str(sport_insights_path.relative_to(root)),
        "model_evidence_rows": int(len(model_rows)),
        "figures": [
            str(path.relative_to(root))
            for path in sorted(figure_dir.glob("*.png"))
        ],
    }
    write_json(report_dir / "eda_summary.json", result)
    return result
