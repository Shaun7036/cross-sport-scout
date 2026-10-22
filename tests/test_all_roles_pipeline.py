import pandas as pd

from possession_lab.all_roles_pipeline import (
    _canonicalize_panel,
    _context_coverage_table,
    _context_pooling_counts,
    _model_report,
    _write_context_coverage,
    frozen_nba_sanity_checks,
)


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


def test_model_report_includes_native_transferable_profile_family():
    artifact = {
        "schema_version": "fixture",
        "role_taxonomy_version": "fixture",
        "target_version": "fixture",
        "bridge_version": "fixture",
        "frozen_test_season": 2025,
        "claims": {},
        "physical_models": {"a:role": {"status": "not_fit"}},
        "native_forecast_models": {"a:role": {"status": "not_fit"}},
        "native_profile_models": {
            "a:role": {
                "status": "not_fit",
                "profile_increment_gate": "not_supported",
            }
        },
        "bridge_models": {"a:role->b:role": {"status": "not_fit"}},
    }

    report = _model_report(artifact)

    assert report["native_profile_models"]["a:role"]["profile_increment_gate"] == (
        "not_supported"
    )


def test_context_coverage_report_is_deterministic_and_field_complete(tmp_path):
    scored = pd.DataFrame(
        {
            "sport": ["nba", "epl", "nba"],
            "role": ["guard", "FWD", "guard"],
            "context_status": ["available", "insufficient_peer_context", "available"],
            "context_role_opportunity_share_percentile": [80.0, None, 40.0],
            "context_team_peer_strength_percentile": [55.0, None, None],
        }
    )

    table = _context_coverage_table(scored)

    assert list(zip(table["sport"], table["role"])) == [("epl", "FWD"), ("nba", "guard")]
    nba = table.loc[table["sport"].eq("nba")].iloc[0]
    assert nba["total_rows"] == 2
    assert nba["context_available_rows"] == 2
    assert nba["context_role_opportunity_share_percentile_coverage"] == 1.0
    assert nba["context_team_peer_strength_percentile_coverage"] == 0.5

    path = _write_context_coverage(tmp_path, scored)
    lines = path.read_text().splitlines()
    assert lines[1].startswith("epl,FWD,1,0,")
    assert lines[2].startswith("nba,guard,2,2,")


def test_context_and_pooling_counts_use_only_declared_head_metadata():
    artifact = {
        "physical_models": {
            "nba:guard": {"model": object(), "features": ["height_cm", "weight_kg"]}
        },
        "native_forecast_models": {},
        "native_profile_models": {
            "nba:guard": {
                "model": object(),
                "features": [
                    "height_cm",
                    "context_role_opportunity_share_percentile",
                    "context_team_peer_strength_percentile",
                ],
                "partial_pooling": {"status": "deployed"},
            },
            "nba:center": {
                "model": object(),
                "features": ["height_cm"],
                "partial_pooling": {"status": "role_only_retained"},
            },
            "nhl:goalie": {"partial_pooling": {"status": "not_applicable"}},
        },
        "bridge_models": {},
    }

    counts = _context_pooling_counts(artifact)

    assert counts["heads_fit_with_any_team_context"] == 1
    assert counts["heads_fit_with_complete_team_context"] == 1
    assert counts["partial_pooling_heads_reported"] == 3
    assert counts["partial_pooling_deployed_heads"] == 1
    assert counts["partial_pooling_role_only_retained_heads"] == 1
    assert counts["partial_pooling_not_applicable_heads"] == 1
