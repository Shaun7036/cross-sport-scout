import pandas as pd

from possession_lab.all_roles_eda import role_summary


def test_role_summary_separates_coverage_eligibility_and_scores():
    frame = pd.DataFrame(
        {
            "sport": ["x", "x", "x"],
            "role": ["r", "r", "r"],
            "player_id": ["a", "b", "a"],
            "season": [2024, 2024, 2025],
            "opportunity": [100.0, 0.0, 200.0],
            "height_cm": [190.0, None, 191.0],
            "weight_kg": [90.0, None, 91.0],
            "target_status": ["eligible", "not_observed", "eligible"],
            "observed_role_percentile": [40.0, None, 60.0],
        }
    )
    row = role_summary(frame).iloc[0]
    assert row.player_seasons == 3
    assert row.athletes == 2
    assert row.positive_opportunity_rows == 2
    assert row.eligible_rows == 2
    assert row.scored_rows == 2
    assert row.height_coverage == 2 / 3
    assert row.observed_score_mean == 50
