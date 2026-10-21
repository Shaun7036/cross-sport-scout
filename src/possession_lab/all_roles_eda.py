"""Compact, reproducible EDA for the all-role panels and model evidence."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from possession_lab.io import write_json


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


def _model_evidence_rows(report: dict) -> pd.DataFrame:
    rows = []
    for family in ["physical_models", "native_forecast_models"]:
        for key, head in report.get(family, {}).items():
            evaluation = head.get("evaluation", {})
            frozen = evaluation.get("frozen", {})
            neutral = evaluation.get("neutral_50", {})
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
                    "forecast_support": head.get("forecast_support"),
                    "deployment_support": head.get("deployment_support"),
                    "test_n": frozen.get("n"),
                    "model_mae": frozen.get("mae"),
                    "neutral_mae": neutral.get("mae"),
                    "unseen_history_n": unseen_history.get("n"),
                    "usable_rows": head.get("usable_coverage", {}).get("usable_rows"),
                    "usable_fraction_of_eligible_labels": head.get(
                        "usable_coverage", {}
                    ).get("usable_fraction_of_eligible_labels"),
                }
            )
    return pd.DataFrame(rows)


def build_all_roles_eda(root: Path | str) -> dict:
    root = Path(root)
    scored_path = root / "data" / "processed" / "all_roles" / "observed_scores.parquet"
    if not scored_path.exists():
        raise FileNotFoundError(f"Build observed all-role scores first: {scored_path}")
    scored = pd.read_parquet(scored_path)
    report_dir = root / "reports" / "all_roles"
    figure_dir = report_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    summary = role_summary(scored)
    summary.to_csv(report_dir / "role_summary.csv", index=False)
    _save_role_counts(summary, figure_dir / "role_cohort_counts.png")
    _save_score_distributions(scored, figure_dir / "observed_score_distributions.png")
    _save_physical_map(scored, figure_dir / "listed_build_map.png")

    evaluation_path = report_dir / "model_evaluation.json"
    model_rows = pd.DataFrame()
    if evaluation_path.exists():
        model_rows = _model_evidence_rows(json.loads(evaluation_path.read_text()))
        model_rows.to_csv(report_dir / "model_evidence_summary.csv", index=False)

    result = {
        "rows": int(len(scored)),
        "scored_rows": int(scored["observed_role_percentile"].notna().sum()),
        "roles": int(len(summary)),
        "role_summary": str((report_dir / "role_summary.csv").relative_to(root)),
        "model_evidence_rows": int(len(model_rows)),
        "figures": [
            str(path.relative_to(root))
            for path in sorted(figure_dir.glob("*.png"))
        ],
    }
    write_json(report_dir / "eda_summary.json", result)
    return result
