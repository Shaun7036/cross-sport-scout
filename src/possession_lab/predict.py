"""Use fitted physical models to inspect role compatibility across sports."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import chi2

from possession_lab.io import read_frame, sha256


def score_physical_profile(
    root: Path, sport: str, *, height_cm: float, weight_kg: float, age: float | None = None
) -> dict:
    if not np.isfinite(height_cm) or not np.isfinite(weight_kg) or min(height_cm, weight_kg) <= 0:
        raise ValueError("Height and mass must be finite positive measurements")
    model_dir = root / "models" / sport
    path = model_dir / "physical_role_compatibility.joblib"
    if not path.exists():
        return {"sport": sport, "status": "physical_role_model_unavailable"}
    registry_path = model_dir / "model_registry.json"
    if not registry_path.exists():
        return {"sport": sport, "status": "rerun_analysis_to_register_models"}
    registry = json.loads(registry_path.read_text())
    model_hashes = {entry["filename"]: entry["sha256"] for entry in registry["files"]}

    def registered_model(model_path):
        if model_path.name not in model_hashes or sha256(model_path) != model_hashes[model_path.name]:
            raise ValueError(f"Model artifact differs from the registered run: {model_path}")
        return joblib.load(model_path)

    artifact = registered_model(path)
    inputs = {"height_cm": height_cm, "weight_kg": weight_kg, "age": age}
    frame = pd.DataFrame([inputs])
    probabilities = artifact["model"].predict_proba(frame[artifact["features"]])[0]
    panel = read_frame(root / "data" / "processed" / sport / "player_seasons.parquet")
    roles = []
    for role, probability in zip(artifact["roles"], probabilities):
        reference = panel[panel.role.eq(role) & panel.season.le(2024)].drop_duplicates("player_id")
        body = reference[["height_cm", "weight_kg"]].dropna()
        distance = None
        ood = True
        if len(body) >= 10:
            covariance = np.cov(body.to_numpy(), rowvar=False)
            # A small diagonal term prevents singular covariance in narrow roles.
            covariance = covariance + np.diag(np.diag(covariance)) * 0.05 + np.eye(2) * 1e-6
            delta = np.array([height_cm, weight_kg]) - body.mean().to_numpy()
            distance = float(delta @ np.linalg.pinv(covariance) @ delta)
            ood = distance > float(chi2.ppf(0.99, df=2))
        estimates = {}
        for filename in sorted(registry["physical_effectiveness_files"]):
            effectiveness_path = model_dir / filename
            effect = registered_model(effectiveness_path)
            metadata = effect["metadata"]
            # Age is optional only when the fitted feature contract permits it.
            if "age" in effect["features"] and age is None:
                continue
            row = pd.DataFrame([{**inputs, "prior_role": role}])
            estimate = float(np.maximum(0, np.expm1(effect["model"].predict(row[effect["features"]])[0])))
            label = effectiveness_path.stem.removeprefix("physical_effectiveness_")
            estimates[label] = {
                "associated_rate_per100_opportunity": estimate,
                "heldout_player_test_mae": metadata["model_test"]["mae"],
                "role_mean_test_mae": metadata["role_mean_test"]["mae"],
            }
        roles.append(
            {
                "role": str(role),
                "role_label_probability_within_this_sport": float(probability),
                "physical_out_of_distribution": bool(ood),
                "mahalanobis_distance_squared": distance,
                "reference_athletes_with_measured_size": len(body),
                "physical_rate_associations": estimates,
            }
        )
    return {
        "sport": sport,
        "status": "scored",
        "input": inputs,
        "interpretation": "Similarity to role labels among elite athletes; not a probability of entering or succeeding in a sport.",
        "physical_measurement_warning": artifact["metadata"]["physical_timing"],
        "roles": sorted(roles, key=lambda x: x["role_label_probability_within_this_sport"], reverse=True),
    }
