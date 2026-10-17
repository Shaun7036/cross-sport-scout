from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from possession_lab.analysis import build_forecast_pairs, forecast_models


def synthetic_panel() -> pd.DataFrame:
    rng = np.random.default_rng(2025)
    rows = []
    for season in range(2021, 2026):
        for player in range(100):
            opportunity = 0 if (player + season) % 11 == 0 else int(rng.integers(100, 900))
            rows.append(
                {
                    "player_id": str(player),
                    "name": f"Player {player}",
                    "season": season,
                    "role": "guard" if player % 2 else "forward",
                    "opportunity": opportunity,
                    "steals": rng.poisson(opportunity * 0.015),
                    "height_cm": 185 + player % 30,
                    "weight_kg": 80 + player % 40,
                    "age": 20 + (season - 2021) + player % 12,
                }
            )
    return pd.DataFrame(rows)


def test_future_values_do_not_enter_earlier_features():
    before = synthetic_panel()
    after = before.copy()
    after.loc[after.season.eq(2025), "steals"] = 99999
    a = build_forecast_pairs(before, {"steals": "steals"})
    b = build_forecast_pairs(after, {"steals": "steals"})
    features = ["lag_steals_rate", "ewma_steals_rate", "log_lag_opportunity", "ewma_log_opportunity"]
    pd.testing.assert_frame_equal(a[features], b[features])


def test_forecast_fit_save_reload_and_feature_contract(tmp_path: Path):
    (tmp_path / "reports" / "fixture").mkdir(parents=True)
    result = forecast_models(synthetic_panel(), {"steals": "steals"}, tmp_path, "fixture")
    assert result["status"] == "trained"
    assert result["split"]["training_target_seasons"] == [2022, 2023]
    assert result["split"]["test_target_season"] == 2025
    assert (tmp_path / "reports" / "fixture" / "predictions_2025.parquet").exists()
    saved = joblib.load(tmp_path / "models" / "fixture" / "effectiveness_steals.joblib")
    assert saved["training_cutoff"] == 2024
    assert "player_id" not in saved["features"]
    assert "height_cm" not in saved["features"]
    assert "weight_kg" not in saved["features"]
    assert all("target_" not in feature for feature in saved["features"])
    assert all(np.isfinite(row["mae"]) for row in result["metrics"] if "mae" in row)
    assert result["opportunity_selection"] in {"persistence", "hurdle_ridge"}
    assert result["availability_selection"] in {"prevalence", "logistic"}
    opportunity = joblib.load(tmp_path / "models" / "fixture" / "opportunity.joblib")
    assert opportunity["selection"] == result["opportunity_selection"]
    validation_opportunity = [
        row for row in result["metrics"] if row["task"] == "opportunity" and row["fold"] == "validation"
    ]
    assert min(validation_opportunity, key=lambda row: row["mae"])["model"] == result["opportunity_selection"]
    validation_availability = [
        row for row in result["metrics"] if row["task"] == "availability" and row["fold"] == "validation"
    ]
    assert (
        min(validation_availability, key=lambda row: row["brier"])["model"]
        == result["availability_selection"]
    )
