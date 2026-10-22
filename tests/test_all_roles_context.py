import numpy as np
import pandas as pd
import pytest

from possession_lab.all_roles_context import CONTEXT_FEATURES, add_team_context


def _frame():
    rows = []
    for index in range(10):
        rows.append(
            {
                "sport": "nba",
                "role": "guard",
                "season": 2024,
                "team": "A" if index < 5 else "B",
                "opportunity": float(100 + 10 * index),
                "observed_role_percentile": float(10 + 8 * index),
                "training_sample_weight": 1.0,
            }
        )
    return pd.DataFrame(rows)


def test_team_context_uses_same_role_opportunity_and_leave_one_out_strength():
    result, audit = add_team_context(_frame())

    first = result.iloc[0]
    assert first["context_role_opportunity_share"] == pytest.approx(100 / 600)
    assert first["context_team_peer_strength_loo"] == pytest.approx(
        np.mean([18, 26, 34, 42])
    )
    assert all(result[column].notna().all() for column in CONTEXT_FEATURES)
    assert audit["available_rows"] == 10


def test_team_context_withholds_multi_team_rows_and_does_not_change_target():
    frame = _frame()
    frame.loc[0, "team"] = "A;B"
    original = frame["observed_role_percentile"].copy()

    result, _ = add_team_context(frame)

    assert result.loc[0, "context_status"] == "withheld_multi_or_missing_team"
    assert pd.isna(result.loc[0, "context_role_opportunity_share"])
    pd.testing.assert_series_equal(result["observed_role_percentile"], original)


def test_team_context_requires_at_least_five_role_season_references():
    frame = _frame().iloc[:4].copy()

    result, _ = add_team_context(frame)

    assert result[list(CONTEXT_FEATURES)].isna().all(axis=None)
    assert result["context_status"].eq("insufficient_peer_context").all()
