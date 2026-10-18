"""Role-relative possession/disruption targets with train-only reference scales."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class HeadSpec:
    sport: str
    role: str
    min_opportunity: float
    domains: dict
    evaluation: str = "contemporaneous_2025_unseen_athletes"

    @property
    def key(self) -> str:
        return f"{self.sport}:{self.role}"


def _domain(weight, **metrics):
    return {"weight": float(weight), "metrics": metrics}


def head_specs() -> dict[str, HeadSpec]:
    rush = {"sacks": 0.5, "qb_hits": 0.5}
    ball = {"passes_defended": 0.5, "interceptions": 0.5}
    negative = {"negative_play_tackle_credits": 1.0}
    force = {"forced_fumbles": 1.0}
    nfl = {
        "EDGE": {
            "rush_disruption": _domain(0.55, **rush),
            "negative_play_stops": _domain(0.25, **negative),
            "fumble_creation": _domain(0.20, **force),
        },
        "IDL": {
            "rush_disruption": _domain(0.55, **rush),
            "negative_play_stops": _domain(0.35, **negative),
            "fumble_creation": _domain(0.10, **force),
        },
        "LB": {
            "negative_play_stops": _domain(0.40, **negative),
            "ball_disruption": _domain(0.30, **ball),
            "rush_disruption": _domain(0.15, **rush),
            "fumble_creation": _domain(0.15, **force),
        },
        "OLB_HYBRID": {
            "rush_disruption": _domain(0.40, **rush),
            "negative_play_stops": _domain(0.35, **negative),
            "ball_disruption": _domain(0.15, **ball),
            "fumble_creation": _domain(0.10, **force),
        },
        "CB": {
            "ball_disruption": _domain(0.75, **ball),
            "negative_play_stops": _domain(0.10, **negative),
            "fumble_creation": _domain(0.15, **force),
        },
        "S": {
            "ball_disruption": _domain(0.55, **ball),
            "negative_play_stops": _domain(0.25, **negative),
            "rush_disruption": _domain(0.05, **rush),
            "fumble_creation": _domain(0.15, **force),
        },
    }
    nba = {
        "guard": {
            "possession_recovery": _domain(0.55, steals=1.0),
            "shot_disruption": _domain(0.15, blocks=1.0),
            "defensive_recovery": _domain(0.30, defensive_rebounds=1.0),
        },
        "forward": {
            "possession_recovery": _domain(0.40, steals=1.0),
            "shot_disruption": _domain(0.30, blocks=1.0),
            "defensive_recovery": _domain(0.30, defensive_rebounds=1.0),
        },
        "center": {
            "possession_recovery": _domain(0.15, steals=1.0),
            "shot_disruption": _domain(0.45, blocks=1.0),
            "defensive_recovery": _domain(0.40, defensive_rebounds=1.0),
        },
    }
    nhl = {
        "defense": {
            "puck_acquisition": _domain(0.60, takeaways=1.0),
            "shot_disruption": _domain(0.30, blocks=1.0),
            "contact_disruption": _domain(0.10, hits=1.0),
        },
        "center": {
            "puck_acquisition": _domain(0.45, takeaways=1.0),
            "faceoff_acquisition_activity": _domain(0.45, faceoff_wins=1.0),
            "shot_disruption": _domain(0.10, blocks=1.0),
        },
        "wing": {
            "puck_acquisition": _domain(0.65, takeaways=1.0),
            "shot_disruption": _domain(0.20, blocks=1.0),
            "contact_disruption": _domain(0.15, hits=1.0),
        },
    }
    epl = {
        "DEF": {
            "ball_recovery": _domain(0.35, recoveries=1.0),
            "tackle_wins": _domain(0.35, tackles_won=1.0),
            "interceptions": _domain(0.20, interceptions=1.0),
            "shot_disruption": _domain(0.10, blocks=1.0),
        },
        "MID": {
            "ball_recovery": _domain(0.40, recoveries=1.0),
            "tackle_wins": _domain(0.35, tackles_won=1.0),
            "interceptions": _domain(0.25, interceptions=1.0),
        },
        "FWD": {
            "ball_recovery": _domain(0.50, recoveries=1.0),
            "tackle_wins": _domain(0.30, tackles_won=1.0),
            "interceptions": _domain(0.20, interceptions=1.0),
        },
    }
    result = {}
    for sport, roles, minimum in [("nfl", nfl, 150), ("nba", nba, 300), ("nhl", nhl, 300), ("epl", epl, 450)]:
        for role, domains in roles.items():
            spec = HeadSpec(
                sport,
                role,
                minimum,
                domains,
                "same_season_2025_unseen_athletes"
                if sport == "epl"
                else "contemporaneous_2025_unseen_athletes",
            )
            result[spec.key] = spec
    return result


def athlete_weights(frame: pd.DataFrame) -> np.ndarray:
    """Each athlete has total weight one, irrespective of career length."""
    key = "athlete_id" if "athlete_id" in frame else "player_id"
    counts = frame.groupby(key)[key].transform("size").to_numpy(float)
    weights = 1.0 / counts
    return weights / weights.mean()


class WeightedECDF:
    """Weighted mid-ranks, including exact tie handling at the boundaries."""

    def fit(self, values, sample_weight=None):
        values = np.asarray(values, dtype=float)
        weights = np.ones(len(values)) if sample_weight is None else np.asarray(sample_weight, dtype=float)
        valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
        if not valid.any():
            raise ValueError("ECDF needs finite observations and positive weight")
        unique, inverse = np.unique(values[valid], return_inverse=True)
        mass = np.bincount(inverse, weights=weights[valid])
        self.values_ = unique
        self.mass_ = mass / mass.sum()
        self.cumulative_ = np.r_[0.0, np.cumsum(self.mass_)]
        return self

    def transform(self, values):
        values = np.asarray(values, dtype=float)
        left = np.searchsorted(self.values_, values, side="left")
        right = np.searchsorted(self.values_, values, side="right")
        result = 100 * (self.cumulative_[left] + self.cumulative_[right]) / 2
        result[~np.isfinite(values)] = np.nan
        return np.clip(result, 0, 100)


class RoleTarget:
    """Train-fitted shrunk rates -> domain ranks -> composite role percentile.

    All priors and ECDFs must be re-fitted inside every training fold. This
    target describes possession/disruption activity per opportunity, not overall
    defensive quality or cross-sport transition success.
    """

    def __init__(self, spec: HeadSpec):
        self.spec = spec

    @property
    def required_metrics(self):
        return sorted({m for d in self.spec.domains.values() for m in d["metrics"]})

    def fit(self, frame: pd.DataFrame):
        if not len(frame):
            raise ValueError("Target fitting needs observations")
        weights = athlete_weights(frame)
        opportunity = frame.opportunity.to_numpy(float)
        if np.any(~np.isfinite(opportunity)) or np.any(opportunity <= 0):
            raise ValueError("Target opportunities must be finite and positive")
        self.prior_exposure_ = float(np.median(opportunity) * 0.5)
        self.components_ = {}
        self.constant_components_ = []
        for metric in self.required_metrics:
            value = pd.to_numeric(frame[metric], errors="coerce").to_numpy(float)
            valid = np.isfinite(value)
            if not valid.all():
                raise ValueError(f"Missing target component in training: {metric}")
            if np.any(value < 0):
                raise ValueError(f"Negative target component: {metric}")
            prior = float(np.sum(weights * value) / np.sum(weights * opportunity))
            shrunk = (value + prior * self.prior_exposure_) / (opportunity + self.prior_exposure_)
            if np.ptp(shrunk) < 1e-12:
                self.constant_components_.append(metric)
            self.components_[metric] = {
                "prior": prior,
                "cdf": WeightedECDF().fit(shrunk, weights),
            }
        composite = self._domains(frame)["raw_composite"].to_numpy()
        self.composite_cdf_ = WeightedECDF().fit(composite, weights)
        self.reference_players_ = (
            frame.athlete_id.nunique() if "athlete_id" in frame else frame.player_id.nunique()
        )
        return self

    def _domains(self, frame):
        opportunity = pd.to_numeric(frame.opportunity, errors="coerce").to_numpy(float)
        valid = np.isfinite(opportunity) & (opportunity > 0)
        output = pd.DataFrame(index=frame.index)
        raw = np.zeros(len(frame))
        domain_total = sum(d["weight"] for d in self.spec.domains.values())
        for name, domain in self.spec.domains.items():
            component_score = np.zeros(len(frame))
            total = sum(domain["metrics"].values())
            for metric, weight in domain["metrics"].items():
                value = pd.to_numeric(frame[metric], errors="coerce").to_numpy(float)
                valid &= np.isfinite(value) & (value >= 0)
                prior = self.components_[metric]["prior"]
                shrunk = (value + prior * self.prior_exposure_) / (opportunity + self.prior_exposure_)
                component_score += self.components_[metric]["cdf"].transform(shrunk) * weight / total
            output[f"domain_{name}"] = component_score
            raw += component_score * domain["weight"] / domain_total
        output["raw_composite"] = raw
        output.loc[~valid, :] = np.nan
        return output

    def transform(self, frame):
        result = self._domains(frame)
        result["efficacy_target"] = self.composite_cdf_.transform(result.raw_composite.to_numpy())
        return result

    def describe(self):
        return {
            "role": self.spec.role,
            "sport": self.spec.sport,
            "domains": self.spec.domains,
            "minimum_opportunity": self.spec.min_opportunity,
            "shrinkage_prior_exposure": self.prior_exposure_,
            "reference_athletes": self.reference_players_,
            "constant_components_rank_at_50": self.constant_components_,
            "definition": "Observed percentile of a role-specific possession/disruption activity composite among eligible elite peers.",
            "sparse_components": "Constant components contribute a neutral tied mid-rank; they do not become fabricated signal.",
        }


class SeasonalRoleTarget:
    """Prevent scoring/provider drift from becoming a physical association.

    Fit the complete target independently within each season using only the
    reference athletes in the current training fold. Unseen seasons cannot be
    transformed: silently borrowing another season would imply comparability
    that has not been established. This is contemporaneous, not forecasting.
    """

    def __init__(self, spec: HeadSpec):
        self.spec = spec

    def fit(self, frame):
        self.seasons_ = {
            int(season): RoleTarget(self.spec).fit(part) for season, part in frame.groupby("season")
        }
        if not self.seasons_:
            raise ValueError("Seasonal target needs reference observations")
        return self

    def transform(self, frame):
        output = []
        for season, part in frame.groupby("season"):
            if int(season) not in self.seasons_:
                raise ValueError(f"No contemporaneous reference for season {season}")
            output.append(self.seasons_[int(season)].transform(part))
        if not output:
            return pd.DataFrame(index=frame.index, columns=["efficacy_target"], dtype=float)
        return pd.concat(output).reindex(frame.index)

    def describe(self):
        return {
            "normalization": "sport-role-season; training athletes only",
            "seasons": {str(s): t.describe() for s, t in self.seasons_.items()},
        }
