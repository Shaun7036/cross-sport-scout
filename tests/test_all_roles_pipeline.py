import pandas as pd

from possession_lab.all_roles_pipeline import _canonicalize_panel, frozen_nba_sanity_checks


def test_canonicalize_panel_preserves_sport_identity_and_rejects_duplicates():
    frame = pd.DataFrame(
        {
            "player_id": [1],
            "name": ["A"],
            "season": [2025],
            "role": ["guard"],
            "opportunity": [100],
        }
    )
    result = _canonicalize_panel(frame, "nba")
    assert result.loc[0, "sport"] == "nba"
    assert result.loc[0, "player_id"] == "1"
    assert result.loc[0, "position"] == "guard"


def test_canonicalize_panel_quarantines_implausible_physical_values():
    frame = pd.DataFrame(
        {
            "player_id": ["a"],
            "name": ["A"],
            "season": [2025],
            "role": ["QB"],
            "opportunity": [10],
            "height_cm": [190],
            "weight_kg": [813.7],
        }
    )
    result = _canonicalize_panel(frame, "nfl")
    assert pd.isna(result.loc[0, "weight_kg"])
    assert result.loc[0, "weight_kg_rejected_raw"] == 813.7
    assert result.loc[0, "weight_quality_flag"] == "implausible_set_missing"


def test_frozen_star_checks_use_exact_ids_not_names():
    scored = pd.DataFrame(
        {
            "sport": ["nba", "nba", "nba"],
            "player_id": ["3975", "2326307", "1966"],
            "name": ["Stephen Curry", "Seth Curry", "LeBron James"],
            "season": [2025, 2025, 2025],
            "domain_scoring_percentile": [96.0, 99.0, 80.0],
            "domain_creation_percentile": [70.0, 50.0, 95.0],
        }
    )
    checks = frozen_nba_sanity_checks(scored)
    assert checks["stephen_curry"]["value"] == 96.0
    assert checks["lebron_james"]["value"] == 95.0
    assert checks["identity_guard"]["status"] == "pass"
