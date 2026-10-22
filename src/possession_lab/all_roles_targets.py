"""Observed all-role percentiles and transferable dimension profiles.

These targets are descriptive.  They compare an athlete with eligible peers in
the same sport, broad role and season.  Small samples are shrunk toward the
reference mean before ranking, and availability remains visibly separate from
per-opportunity quality.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from possession_lab.all_roles_context import add_team_context
from possession_lab.all_roles_registry import RoleSpec, role_specs
from possession_lab.ensemble_targets import WeightedECDF

IDENTITY_COLUMNS = [
    "sport",
    "player_id",
    "name",
    "season",
    "role",
    "position",
    "team",
    "games",
    "opportunity",
    "height_cm",
    "weight_kg",
    "age",
]


@dataclass(frozen=True)
class TargetFitSummary:
    sport: str
    role: str
    season: int
    reference_athletes: int
    scored_athletes: int
    min_opportunity: float
    prior_exposure: float
    status: str


def _numeric(frame: pd.DataFrame, column: str) -> np.ndarray:
    if column not in frame:
        return np.full(len(frame), np.nan)
    return pd.to_numeric(frame[column], errors="coerce").to_numpy(float)


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not valid.any():
        return float("nan")
    return float(np.average(values[valid], weights=weights[valid]))


def _combine_available(frame: pd.DataFrame, columns: list[str], weights: list[float]) -> np.ndarray:
    """Weighted row mean that never invents values for absent components."""
    values = frame.reindex(columns=columns).to_numpy(float)
    component_weights = np.asarray(weights, dtype=float)
    valid = np.isfinite(values)
    numerator = np.nansum(values * component_weights, axis=1)
    denominator = np.sum(valid * component_weights, axis=1)
    return np.divide(
        numerator,
        denominator,
        out=np.full(len(frame), np.nan),
        where=denominator > 0,
    )


class ObservedRoleTarget:
    """Fit one role-season reference and score observed athletes."""

    def __init__(self, spec: RoleSpec):
        if not spec.domains:
            raise ValueError(f"{spec.key} has no public performance label and must abstain")
        self.spec = spec

    @property
    def metric_columns(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(metric.column for domain in self.spec.domains for metric in domain.metrics)
        )

    def fit(self, frame: pd.DataFrame) -> "ObservedRoleTarget":
        if frame.empty:
            raise ValueError("Observed target requires a non-empty role-season frame")
        opportunity = _numeric(frame, "opportunity")
        eligible = np.isfinite(opportunity) & (opportunity >= self.spec.min_opportunity)
        self.reference_mask_ = eligible
        if int(eligible.sum()) < 5:
            raise ValueError(
                f"{self.spec.key} needs at least five eligible role-season athletes; "
                f"found {int(eligible.sum())}"
            )

        reference_opportunity = opportunity[eligible]
        self.prior_exposure_ = max(
            float(np.nanmedian(reference_opportunity) * 0.5),
            float(self.spec.min_opportunity * 0.5),
            1.0,
        )
        # One athlete-season has one vote in the contemporaneous peer cohort.
        reference_weights = np.ones(int(eligible.sum()), dtype=float)
        self.metric_models_: dict[str, dict] = {}
        for column in self.metric_columns:
            values = _numeric(frame, column)
            valid_reference = eligible & np.isfinite(values)
            if int(valid_reference.sum()) < 5:
                self.metric_models_[column] = {
                    "status": "insufficient_metric_coverage",
                    "reference_n": int(valid_reference.sum()),
                }
                continue
            prior = _weighted_mean(values[valid_reference], opportunity[valid_reference])
            reliability = opportunity / (opportunity + self.prior_exposure_)
            shrunk = reliability * values + (1.0 - reliability) * prior
            cdf = WeightedECDF().fit(shrunk[valid_reference], reference_weights[: int(valid_reference.sum())])
            self.metric_models_[column] = {
                "status": "fit",
                "reference_n": int(valid_reference.sum()),
                "prior": prior,
                "cdf": cdf,
            }

        provisional = self._component_scores(frame)
        composite = self._domain_composite(provisional)
        valid_composite = eligible & np.isfinite(composite)
        if int(valid_composite.sum()) < 5:
            raise ValueError(f"{self.spec.key} has insufficient complete domain scores")
        self.quality_cdf_ = WeightedECDF().fit(composite[valid_composite])
        self.availability_cdf_ = WeightedECDF().fit(opportunity[np.isfinite(opportunity) & (opportunity > 0)])
        quality = self.quality_cdf_.transform(composite)
        availability = self.availability_cdf_.transform(opportunity)
        impact_raw = 0.75 * quality + 0.25 * availability
        self.impact_cdf_ = WeightedECDF().fit(impact_raw[valid_composite])
        self.reference_n_ = int(valid_composite.sum())
        return self

    def _component_scores(self, frame: pd.DataFrame) -> pd.DataFrame:
        opportunity = _numeric(frame, "opportunity")
        reliability = opportunity / (opportunity + self.prior_exposure_)
        output = pd.DataFrame(index=frame.index)
        for domain in self.spec.domains:
            for metric in domain.metrics:
                model = self.metric_models_.get(metric.column, {})
                column = f"metric_{metric.column}_percentile"
                if model.get("status") != "fit":
                    output[column] = np.nan
                    continue
                values = _numeric(frame, metric.column)
                shrunk = reliability * values + (1.0 - reliability) * model["prior"]
                ranked = model["cdf"].transform(shrunk)
                if not metric.higher_is_better:
                    ranked = 100.0 - ranked
                ranked[~np.isfinite(values) | ~(opportunity > 0)] = np.nan
                output[column] = ranked
        return output

    def _domain_composite(self, component_scores: pd.DataFrame) -> np.ndarray:
        domain_values: list[np.ndarray] = []
        domain_weights: list[float] = []
        for domain in self.spec.domains:
            columns = [f"metric_{metric.column}_percentile" for metric in domain.metrics]
            weights = [metric.weight for metric in domain.metrics]
            values = _combine_available(component_scores, columns, weights)
            domain_values.append(values)
            domain_weights.append(domain.weight)
        matrix = np.column_stack(domain_values)
        valid = np.isfinite(matrix)
        weights = np.asarray(domain_weights, dtype=float)
        numerator = np.nansum(matrix * weights, axis=1)
        denominator = np.sum(valid * weights, axis=1)
        return np.divide(
            numerator,
            denominator,
            out=np.full(len(component_scores), np.nan),
            where=denominator > 0,
        )

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        opportunity = _numeric(frame, "opportunity")
        result = self._component_scores(frame)
        domain_columns: list[str] = []
        domain_weights: list[float] = []
        component_coverage_numerator = np.zeros(len(frame), dtype=float)
        component_coverage_denominator = 0.0
        for domain in self.spec.domains:
            columns = [f"metric_{metric.column}_percentile" for metric in domain.metrics]
            weights = [metric.weight for metric in domain.metrics]
            column = f"domain_{domain.name}_percentile"
            result[column] = _combine_available(result, columns, weights)
            domain_columns.append(column)
            domain_weights.append(domain.weight)

            # Metric weights are meaningful within a domain, while domain
            # weights are meaningful across domains.  Normalising each level
            # keeps a domain with several metrics from counting as more
            # complete merely because it has more columns.
            metric_weights = np.asarray(weights, dtype=float)
            metric_total = float(metric_weights.sum())
            if metric_total > 0:
                available = np.isfinite(result.reindex(columns=columns).to_numpy(float))
                within_domain = (available * metric_weights).sum(axis=1) / metric_total
                component_coverage_numerator += domain.weight * within_domain
                component_coverage_denominator += domain.weight

        raw_composite = _combine_available(result, domain_columns, domain_weights)
        quality = self.quality_cdf_.transform(raw_composite)
        availability = self.availability_cdf_.transform(opportunity)
        impact_raw = 0.75 * quality + 0.25 * availability
        total_impact = self.impact_cdf_.transform(impact_raw)

        positive = np.isfinite(opportunity) & (opportunity > 0)
        reliability = np.divide(
            opportunity,
            opportunity + self.prior_exposure_,
            out=np.zeros(len(frame), dtype=float),
            where=positive,
        )
        component_coverage = np.divide(
            component_coverage_numerator,
            component_coverage_denominator,
            out=np.zeros(len(frame), dtype=float),
            where=component_coverage_denominator > 0,
        )
        domain_matrix = result.reindex(columns=domain_columns).to_numpy(float)
        declared_domain_weights = np.asarray(domain_weights, dtype=float)
        domain_weight_total = float(declared_domain_weights.sum())
        domain_coverage = np.divide(
            (np.isfinite(domain_matrix) * declared_domain_weights).sum(axis=1),
            domain_weight_total,
            out=np.zeros(len(frame), dtype=float),
            where=domain_weight_total > 0,
        )
        training_weight = reliability * component_coverage
        training_weight = np.where(
            positive & np.isfinite(quality),
            np.clip(training_weight, 0.05, 1.0),
            np.nan,
        )
        quality[~positive] = np.nan
        availability[~positive] = np.nan
        total_impact[~positive] = np.nan
        result["quality_percentile"] = quality
        result["observed_role_percentile"] = quality
        result["availability_percentile"] = availability
        result["total_impact_percentile"] = total_impact
        result["opportunity_reliability"] = reliability
        result["component_coverage_fraction"] = component_coverage
        result["domain_coverage_fraction"] = domain_coverage
        result["training_sample_weight"] = training_weight
        result["target_status"] = np.select(
            [~positive, opportunity < self.spec.min_opportunity],
            ["not_observed", "low_sample"],
            default="eligible",
        )
        result["reference_athletes"] = self.reference_n_
        result["minimum_opportunity"] = self.spec.min_opportunity
        result["evidence_status"] = self.spec.evidence_status

        for dimension in self.spec.dimensions:
            domains = [domain for domain in self.spec.domains if domain.dimension == dimension]
            columns = [f"domain_{domain.name}_percentile" for domain in domains]
            weights = [domain.weight for domain in domains]
            result[f"dimension_{dimension}_percentile"] = _combine_available(
                result, columns, weights
            )
        return result

    def describe(self) -> dict:
        return {
            "sport": self.spec.sport,
            "role": self.spec.role,
            "minimum_opportunity": self.spec.min_opportunity,
            "opportunity_unit": self.spec.opportunity_unit,
            "prior_exposure": self.prior_exposure_,
            "reference_athletes": self.reference_n_,
            "evidence_status": self.spec.evidence_status,
            "limitation": self.spec.limitation,
            "metrics": {
                key: {k: v for k, v in model.items() if k != "cdf"}
                for key, model in self.metric_models_.items()
            },
        }


def _role_season_key(frame: pd.DataFrame) -> pd.Series:
    return frame["sport"].astype(str) + ":" + frame["role"].astype(str)


def score_observed_panel(
    panel: pd.DataFrame,
    *,
    specs: dict[str, RoleSpec] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Score every supported sport-role-season cohort in a canonical panel."""
    required = {"sport", "player_id", "name", "season", "role", "opportunity"}
    missing = sorted(required.difference(panel.columns))
    if missing:
        raise ValueError(f"All-role panel is missing columns: {missing}")
    if panel.duplicated(["sport", "player_id", "season"]).any():
        raise ValueError("All-role panel has duplicate sport-player-season rows")

    available_specs = role_specs() if specs is None else specs
    source = panel.copy()
    source["season"] = pd.to_numeric(source["season"], errors="raise").astype(int)
    source["role_key"] = _role_season_key(source)
    pieces: list[pd.DataFrame] = []
    descriptions: dict[str, dict] = {}
    skipped: list[dict] = []

    def unscored(part: pd.DataFrame, status: str, evidence: str) -> pd.DataFrame:
        output = part.copy()
        output["target_status"] = status
        output["evidence_status"] = evidence
        output["observed_role_percentile"] = np.nan
        output["quality_percentile"] = np.nan
        output["availability_percentile"] = np.nan
        output["total_impact_percentile"] = np.nan
        output["reference_athletes"] = 0
        output["opportunity_reliability"] = np.nan
        output["component_coverage_fraction"] = np.nan
        output["domain_coverage_fraction"] = np.nan
        output["training_sample_weight"] = np.nan
        return output

    for (key, season), part in source.groupby(["role_key", "season"], sort=True):
        spec = available_specs.get(str(key))
        if spec is None:
            pieces.append(unscored(part, "unregistered_role", "withheld"))
            skipped.append({"key": str(key), "season": int(season), "reason": "unregistered_role"})
            continue
        if not spec.domains:
            pieces.append(unscored(part, spec.evidence_status, spec.evidence_status))
            skipped.append({"key": str(key), "season": int(season), "reason": spec.evidence_status})
            continue
        try:
            target = ObservedRoleTarget(spec).fit(part)
        except ValueError as error:
            pieces.append(unscored(part, "withheld_insufficient_evidence", spec.evidence_status))
            skipped.append({"key": str(key), "season": int(season), "reason": str(error)})
            continue
        scores = target.transform(part)
        pieces.append(pd.concat([part, scores], axis=1))
        descriptions[f"{key}:{season}"] = target.describe()

    if not pieces:
        raise ValueError("No registered role-season cohort could be scored")
    result = pd.concat(pieces, ignore_index=True, sort=False)
    result = add_sustained_index(result)
    result, context_audit = add_team_context(result)
    result = result.drop(columns=["role_key"], errors="ignore")
    return result, {
        "cohorts": descriptions,
        "skipped": skipped,
        "rows": int(len(result)),
        "scored_rows": int(result["observed_role_percentile"].notna().sum()),
        "team_context": context_audit,
    }


def add_sustained_index(scored: pd.DataFrame) -> pd.DataFrame:
    """Add an inclusive, exponentially weighted three-season native index."""
    result = scored.sort_values(["sport", "player_id", "season"]).copy()
    sustained = pd.Series(np.nan, index=result.index, dtype=float)
    for _, group in result.groupby(["sport", "player_id"], sort=False):
        values = pd.to_numeric(group["observed_role_percentile"], errors="coerce").to_numpy(float)
        seasons = pd.to_numeric(group["season"], errors="coerce").to_numpy(int)
        output = np.full(len(group), np.nan)
        for index, season in enumerate(seasons):
            include = (seasons <= season) & (seasons >= season - 2) & np.isfinite(values)
            if not include.any():
                continue
            age = season - seasons[include]
            weights = np.power(0.70, age)
            output[index] = float(np.average(values[include], weights=weights))
        sustained.loc[group.index] = output
    result["sustained_3y_percentile"] = sustained
    return result.sort_index()


def dimension_columns(frame: pd.DataFrame) -> list[str]:
    return sorted(column for column in frame if column.startswith("dimension_") and column.endswith("_percentile"))


def domain_columns(frame: pd.DataFrame) -> list[str]:
    return sorted(column for column in frame if column.startswith("domain_") and column.endswith("_percentile"))
