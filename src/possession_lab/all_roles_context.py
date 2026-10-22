"""Leakage-safe, cross-league team-context descriptors.

These fields describe completed season *t* and may be used to forecast season
*t+1*.  They never use a future team, target-season aggregate, or team identity.
The calculations intentionally stay small and auditable across four sports:

* role opportunity share compares a player with teammates in the same broad
  role, where opportunity units are comparable;
* leave-one-player-out team strength averages the already role-normalized
  observed percentiles of other teammates.

Multi-team season rows are withheld because the canonical panel does not carry
stint-level opportunity for every sport.  Missing context stays missing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CONTEXT_VERSION = "team-context-v1"
CONTEXT_FEATURES = (
    "context_role_opportunity_share_percentile",
    "context_team_peer_strength_percentile",
)


def _single_team_mask(frame: pd.DataFrame) -> pd.Series:
    if "team" not in frame:
        return pd.Series(False, index=frame.index)
    values = frame["team"].astype("string").str.strip()
    return values.notna() & values.ne("") & ~values.str.contains(";", regex=False, na=False)


def _within_cohort_percentile(frame: pd.DataFrame, column: str) -> pd.Series:
    output = pd.Series(np.nan, index=frame.index, dtype=float)
    for _, indices in frame.groupby(["sport", "role", "season"], sort=False).groups.items():
        values = pd.to_numeric(frame.loc[indices, column], errors="coerce")
        valid = values.notna() & np.isfinite(values)
        if int(valid.sum()) < 5:
            continue
        output.loc[values.index[valid]] = values.loc[valid].rank(
            method="average", pct=True
        ) * 100.0
    return output


def add_team_context(scored: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Attach completed-season context without redefining the observed target."""
    required = {"sport", "role", "season", "team", "opportunity", "observed_role_percentile"}
    missing = sorted(required.difference(scored.columns))
    if missing:
        raise ValueError(f"Team context requires columns: {missing}")
    result = scored.copy()
    opportunity = pd.to_numeric(result["opportunity"], errors="coerce")
    valid_team = _single_team_mask(result)
    valid_opportunity = opportunity.notna() & np.isfinite(opportunity) & opportunity.gt(0)
    eligible = valid_team & valid_opportunity

    result["context_role_opportunity_share"] = np.nan
    role_subset = result.loc[eligible, ["sport", "season", "team", "role"]].copy()
    role_subset["opportunity"] = opportunity.loc[eligible]
    role_totals = role_subset.groupby(
        ["sport", "season", "team", "role"], dropna=False
    )["opportunity"].transform("sum")
    result.loc[role_subset.index, "context_role_opportunity_share"] = (
        role_subset["opportunity"] / role_totals.where(role_totals.gt(0))
    )

    target = pd.to_numeric(result["observed_role_percentile"], errors="coerce")
    if "training_sample_weight" in result:
        reliability = pd.to_numeric(result["training_sample_weight"], errors="coerce")
    else:
        reliability = pd.Series(1.0, index=result.index)
    reliability = reliability.where(reliability.gt(0) & np.isfinite(reliability), np.nan)
    peer_valid = valid_team & target.notna() & np.isfinite(target) & reliability.notna()
    result["context_team_peer_strength_loo"] = np.nan
    if peer_valid.any():
        peers = result.loc[peer_valid, ["sport", "season", "team"]].copy()
        peers["weighted_target"] = target.loc[peer_valid] * reliability.loc[peer_valid]
        peers["weight"] = reliability.loc[peer_valid]
        group_keys = [peers["sport"], peers["season"], peers["team"]]
        group_weighted = peers["weighted_target"].groupby(group_keys).transform("sum")
        group_weight = peers["weight"].groupby(group_keys).transform("sum")
        other_weight = group_weight - peers["weight"]
        loo = (group_weighted - peers["weighted_target"]) / other_weight.where(
            other_weight.gt(0)
        )
        result.loc[peers.index, "context_team_peer_strength_loo"] = loo

    result[CONTEXT_FEATURES[0]] = _within_cohort_percentile(
        result, "context_role_opportunity_share"
    )
    result[CONTEXT_FEATURES[1]] = _within_cohort_percentile(
        result, "context_team_peer_strength_loo"
    )
    context_matrix = result.reindex(columns=list(CONTEXT_FEATURES)).to_numpy(float)
    result["context_coverage_fraction"] = np.isfinite(context_matrix).mean(axis=1)
    result["context_status"] = np.select(
        [~valid_team, ~valid_opportunity, result["context_coverage_fraction"].eq(0)],
        ["withheld_multi_or_missing_team", "withheld_no_opportunity", "insufficient_peer_context"],
        default="available",
    )
    result["context_version"] = CONTEXT_VERSION
    audit = {
        "version": CONTEXT_VERSION,
        "rows": int(len(result)),
        "available_rows": int(result["context_status"].eq("available").sum()),
        "multi_or_missing_team_rows": int((~valid_team).sum()),
        "feature_coverage": {
            feature: float(result[feature].notna().mean()) for feature in CONTEXT_FEATURES
        },
        "leakage_rule": (
            "Completed-season context may predict only the next season; team strength is "
            "leave-one-player-out and future team identity is never used."
        ),
        "target_rule": "Observed role percentiles are unchanged; context is a parallel predictor.",
    }
    return result, audit
