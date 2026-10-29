import json

import pandas as pd
import pytest

from possession_lab.all_roles_eda import (
    build_all_roles_eda,
    role_summary,
    sport_insight_summaries,
)


def _sport_insight_frame() -> pd.DataFrame:
    rows: list[dict] = []

    def add(
        sport: str,
        role: str,
        player: str,
        opportunity: float,
        *,
        defensive_opportunity: float = 0,
        sacks: float = 0,
        passes_defended: float = 0,
        steals: float = 0,
        blocks: float = 0,
        hits: float = 0,
        height_cm: float = 185,
        weight_kg: float = 82,
    ) -> None:
        rows.append(
            {
                "sport": sport,
                "role": role,
                "player_id": player,
                "season": 2025,
                "opportunity": opportunity,
                "defensive_opportunity": defensive_opportunity,
                "sacks": sacks,
                "passes_defended": passes_defended,
                "steals": steals,
                "blocks": blocks,
                "hits": hits,
                "height_cm": height_cm,
                "weight_kg": weight_kg,
                "target_status": "eligible",
                "observed_role_percentile": 50.0,
            }
        )

    add("nfl", "EDGE", "edge-1", 200, defensive_opportunity=200, sacks=2, passes_defended=1)
    add("nfl", "EDGE", "edge-2", 800, defensive_opportunity=800, sacks=8, passes_defended=3)
    add("nfl", "IDL", "idl-1", 500, defensive_opportunity=500, sacks=3, passes_defended=2)
    add("nfl", "LB", "lb-1", 500, defensive_opportunity=500, sacks=1, passes_defended=3)
    add("nfl", "S", "s-1", 500, defensive_opportunity=500, sacks=1, passes_defended=4)
    add("nfl", "CB", "cb-1", 500, defensive_opportunity=500, sacks=1, passes_defended=5)

    add("nba", "guard", "guard-1", 500, steals=20, blocks=5)
    add("nba", "guard", "guard-2", 500, steals=20, blocks=5)
    add("nba", "forward", "forward-1", 500, steals=15, blocks=15)
    add("nba", "center", "center-1", 500, steals=10, blocks=20)

    add("nhl", "defense", "defense-1", 600, blocks=60, hits=30)
    add("nhl", "center", "center-2", 600, blocks=40, hits=40)
    add("nhl", "left_wing", "left-wing-1", 600, blocks=30, hits=60)
    add("nhl", "right_wing", "right-wing-1", 600, blocks=30, hits=45)

    add("epl", "GK", "gk-1", 900, height_cm=190, weight_kg=82)
    add("epl", "GK", "gk-2", 900, height_cm=194, weight_kg=88)
    add("epl", "DEF", "def-1", 900, height_cm=186, weight_kg=78)
    add("epl", "FWD", "fwd-1", 900, height_cm=184, weight_kg=77)
    add("epl", "MID", "mid-1", 900, height_cm=178, weight_kg=70)
    add("epl", "MID", "mid-2", 900, height_cm=182, weight_kg=74)
    return pd.DataFrame(rows)


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


def test_sport_insights_use_weighted_role_rates_and_report_build_coverage():
    insights = sport_insight_summaries(_sport_insight_frame())

    nfl = {row["role"]: row for row in insights["nfl"]["roles"]}
    assert insights["nfl"]["players"] == 6
    assert nfl["EDGE"]["sacks_per_1000"] == 10.0
    assert nfl["EDGE"]["passes_defended_per_1000"] == 4.0
    assert insights["nfl"]["edge_to_cornerback_sack_rate_ratio"] == 5.0

    nba = {row["role"]: row for row in insights["nba"]["roles"]}
    assert nba["guard"]["steals_per_36"] == 1.44
    assert nba["center"]["blocks_per_36"] == 1.44
    assert insights["nba"]["center_to_guard_block_rate_ratio"] == 4.0

    nhl = {row["role"]: row for row in insights["nhl"]["roles"]}
    assert nhl["defense"]["blocks_per_60"] == 6.0
    assert nhl["left_wing"]["hits_per_60"] == 6.0
    assert insights["nhl"]["defense_to_left_wing_block_rate_ratio"] == 2.0

    epl = insights["epl"]
    assert epl["complete_build_rows"] == 6
    assert epl["complete_build_coverage"] == 1.0
    assert epl["goalkeeper_minus_midfielder_median_height_cm"] == 12.0
    assert epl["goalkeeper_minus_midfielder_median_weight_kg"] == 13.0


def test_build_all_roles_eda_writes_reproducible_sport_insight_artifacts(tmp_path):
    observed = tmp_path / "data" / "processed" / "all_roles" / "observed_scores.parquet"
    observed.parent.mkdir(parents=True)
    _sport_insight_frame().to_parquet(observed, index=False)

    result = build_all_roles_eda(tmp_path)

    insight_path = tmp_path / result["sport_insights"]
    payload = json.loads(insight_path.read_text())
    assert payload["season"] == 2025
    assert payload["nfl"]["players"] == 6
    for filename in [
        "nfl_role_disruption_2025.png",
        "nba_role_disruption_2025.png",
        "nhl_role_physicality_2025.png",
        "epl_build_by_role_2025.png",
    ]:
        path = tmp_path / "reports" / "all_roles" / "figures" / filename
        assert path.exists()
        assert path.stat().st_size > 0


def test_sport_insights_require_the_documented_source_columns():
    with pytest.raises(ValueError, match="sport-insight columns"):
        sport_insight_summaries(pd.DataFrame({"sport": ["nfl"]}))
