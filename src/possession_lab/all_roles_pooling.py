"""Small, explicit helpers for evidence-gated partial pooling.

The role model remains the primary estimator.  A related-role family model may
shrink it only when a predeclared family and held-out evidence support that
choice.  Unique roles such as goalkeepers, kickers, punters, and hockey goalies
are intentionally not assigned to a family.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

POOLING_VERSION = "related-role-shrinkage-v1"
POOLING_TAUS = (0.0, 10.0, 25.0, 50.0, 100.0, 200.0)
POOLING_MIN_FROZEN_N = 20
ROLE_FAMILIES = {
    "nba:skill_roles": ("nba:guard", "nba:forward", "nba:center"),
    "nfl:receivers": ("nfl:WR", "nfl:TE"),
    "nfl:secondary": ("nfl:CB", "nfl:S"),
    "nhl:forwards": ("nhl:center", "nhl:left_wing", "nhl:right_wing"),
    "epl:attackers": ("epl:MID", "epl:FWD"),
}


def effective_sample_size(sample_weight) -> float:
    weights = pd.to_numeric(pd.Series(np.asarray(sample_weight)), errors="coerce").to_numpy(float)
    weights = weights[np.isfinite(weights) & (weights > 0)]
    if not len(weights):
        return 0.0
    return float(weights.sum() ** 2 / np.square(weights).sum())


def role_blend_weight(effective_rows: float, tau: float) -> float:
    if effective_rows < 0 or tau < 0:
        raise ValueError("effective_rows and tau must be non-negative")
    if tau == 0:
        return 1.0
    return float(effective_rows / (effective_rows + tau))


def role_dummy_name(role_key: str) -> str:
    return "pool_role__" + role_key.replace(":", "__").replace("-", "_")


def family_for_role(role_key: str) -> tuple[str, tuple[str, ...]] | None:
    """Return the single predeclared related-role family for ``role_key``."""
    matches = [
        (family, tuple(role_keys))
        for family, role_keys in ROLE_FAMILIES.items()
        if role_key in role_keys
    ]
    if len(matches) > 1:
        raise ValueError(f"Role {role_key!r} belongs to more than one pooling family")
    return matches[0] if matches else None


def add_role_dummies(
    frame: pd.DataFrame,
    *,
    role_column: str,
    family_role_keys: tuple[str, ...],
) -> pd.DataFrame:
    """Attach a stable one-hot contract for a predeclared role family."""
    result = frame.copy()
    roles = result[role_column].astype("string")
    for role_key in family_role_keys:
        result[role_dummy_name(role_key)] = roles.eq(role_key).astype(float)
    return result


def pooling_gate(frozen_n: int, advantage: dict) -> str:
    """Apply the predeclared frozen-test deployment gate."""
    if int(frozen_n) < POOLING_MIN_FROZEN_N:
        return "insufficient_frozen_evidence"
    ci90 = advantage.get("ci90", [None, None])
    ci_low = ci90[0] if isinstance(ci90, (list, tuple)) and ci90 else None
    if ci_low is None or not np.isfinite(ci_low):
        return "insufficient_frozen_evidence"
    return "supported" if float(ci_low) > 0 else "not_supported"


@dataclass
class BlendedPercentileModel:
    """Blend a role-specific model with a fixed related-role family model."""

    role_model: Any
    family_model: Any
    role_weight: float
    family: str
    role_key: str
    family_role_keys: tuple[str, ...]
    tau: float
    effective_rows: float

    @property
    def features(self) -> tuple[str, ...]:
        internal = {role_dummy_name(key) for key in self.family_role_keys}
        ordered = [*self.role_model.features]
        ordered.extend(feature for feature in self.family_model.features if feature not in internal)
        return tuple(dict.fromkeys(ordered))

    @property
    def training_rows(self) -> int:
        return int(self.role_model.training_rows)

    @property
    def training_weight_sum(self) -> float:
        return float(self.role_model.training_weight_sum)

    def _family_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        for role_key in self.family_role_keys:
            result[role_dummy_name(role_key)] = float(role_key == self.role_key)
        return result

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        role = self.role_model.predict(frame)
        family = self.family_model.predict(self._family_frame(frame))
        return np.clip(self.role_weight * role + (1.0 - self.role_weight) * family, 0, 100)

    def explain(self, frame: pd.DataFrame) -> list[list[dict]]:
        role_rows = self.role_model.explain(frame)
        family_rows = self.family_model.explain(self._family_frame(frame))
        output = []
        internal = {role_dummy_name(key) for key in self.family_role_keys}
        for role_items, family_items in zip(role_rows, family_rows):
            combined: dict[str, dict] = {}
            for item in role_items:
                combined[item["feature"]] = {
                    "feature": item["feature"],
                    "contribution": self.role_weight * float(item["contribution"]),
                    "imputed": bool(item["imputed"]),
                }
            for item in family_items:
                if item["feature"] in internal:
                    continue
                entry = combined.setdefault(
                    item["feature"],
                    {"feature": item["feature"], "contribution": 0.0, "imputed": False},
                )
                entry["contribution"] += (1.0 - self.role_weight) * float(
                    item["contribution"]
                )
                entry["imputed"] = bool(entry["imputed"] or item["imputed"])
            output.append(
                sorted(combined.values(), key=lambda item: abs(item["contribution"]), reverse=True)
            )
        return output

    def metadata(self) -> dict:
        return {
            "model_type": "partially_pooled_role_family_blend",
            "features": list(self.features),
            "training_rows": self.training_rows,
            "training_weight_sum": self.training_weight_sum,
            "role_weight": float(self.role_weight),
            "family_weight": float(1.0 - self.role_weight),
            "family": self.family,
            "role_key": self.role_key,
            "family_role_keys": list(self.family_role_keys),
            "tau": float(self.tau),
            "effective_role_rows": float(self.effective_rows),
            "role_model": self.role_model.metadata(),
            "family_model": self.family_model.metadata(),
            "version": POOLING_VERSION,
        }
