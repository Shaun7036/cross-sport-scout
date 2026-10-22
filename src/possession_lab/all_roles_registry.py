"""Versioned role and metric contract for the all-role project.

The registry is intentionally data rather than model code.  A score is only
meaningful when its peer group, opportunity threshold, atomic metrics and
directions are fixed before fitting.  Cross-sport bridges use the ``dimension``
labels as explicitly documented analogies; they are not claims that two sports
measure an identical latent trait.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

SCHEMA_VERSION = "2.2.0"
ROLE_TAXONOMY_VERSION = "all-roles-broad-v2"
TARGET_VERSION = "role-season-reliability-weighted-percentiles-v2"
BRIDGE_VERSION = "lagged-ordered-pair-dimension-intersection-v3"
FROZEN_TEST_SEASON = 2025


@dataclass(frozen=True)
class MetricSpec:
    column: str
    weight: float = 1.0
    higher_is_better: bool = True
    description: str = ""


@dataclass(frozen=True)
class DomainSpec:
    name: str
    dimension: str
    weight: float
    metrics: tuple[MetricSpec, ...]


@dataclass(frozen=True)
class RoleSpec:
    sport: str
    role: str
    label: str
    min_opportunity: float
    opportunity_unit: str
    domains: tuple[DomainSpec, ...]
    evidence_status: str = "research_proxy"
    limitation: str = "Observed public-stat composite; not a complete measure of player quality."

    @property
    def key(self) -> str:
        return f"{self.sport}:{self.role}"

    @property
    def dimensions(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(domain.dimension for domain in self.domains))


def metric(
    column: str,
    weight: float = 1.0,
    *,
    higher_is_better: bool = True,
    description: str = "",
) -> MetricSpec:
    return MetricSpec(column, weight, higher_is_better, description)


def domain(
    name: str,
    dimension: str,
    weight: float,
    *metrics: MetricSpec,
) -> DomainSpec:
    return DomainSpec(name, dimension, weight, tuple(metrics))


def _nfl_specs() -> list[RoleSpec]:
    return [
        RoleSpec(
            "nfl",
            "QB",
            "Quarterback",
            150,
            "dropbacks",
            (
                domain(
                    "passing_value",
                    "progression_territory",
                    0.38,
                    metric("passing_epa_per_play", 0.45),
                    metric("passing_yards_per_attempt", 0.20),
                    metric("completion_over_expected", 0.20),
                    metric("explosive_pass_rate", 0.15),
                ),
                domain(
                    "creation",
                    "creation_distribution",
                    0.22,
                    metric("passing_first_down_rate", 0.65),
                    metric("passing_air_yards_per_attempt", 0.35),
                ),
                domain(
                    "scoring",
                    "scoring_finishing",
                    0.20,
                    metric("touchdown_rate"),
                ),
                domain(
                    "security",
                    "possession_security",
                    0.20,
                    metric("turnover_rate", 0.65, higher_is_better=False),
                    metric("sack_rate", 0.35, higher_is_better=False),
                ),
            ),
        ),
        RoleSpec(
            "nfl",
            "RB_FB",
            "Running back / fullback",
            60,
            "touches",
            (
                domain(
                    "ground_value",
                    "progression_territory",
                    0.34,
                    metric("rushing_epa_per_carry", 0.35),
                    metric("rushing_yards_per_carry", 0.25),
                    metric("rushing_first_down_rate", 0.25),
                    metric("explosive_run_rate", 0.15),
                ),
                domain(
                    "receiving",
                    "creation_distribution",
                    0.23,
                    metric("receiving_epa_per_target", 0.45),
                    metric("receiving_yards_per_target", 0.35),
                    metric("explosive_target_rate", 0.20),
                ),
                domain(
                    "scoring",
                    "scoring_finishing",
                    0.23,
                    metric("touchdown_rate"),
                ),
                domain(
                    "security",
                    "possession_security",
                    0.20,
                    metric("turnover_rate", higher_is_better=False),
                ),
            ),
        ),
        *[
            RoleSpec(
                "nfl",
                role,
                label,
                minimum,
                "targets",
                (
                    domain(
                        "receiving_value",
                        "progression_territory",
                        0.36,
                        metric("receiving_epa_per_target", 0.35),
                        metric("receiving_yards_per_target", 0.25),
                        metric("receiving_first_down_rate", 0.25),
                        metric("explosive_target_rate", 0.15),
                    ),
                    domain(
                        "conversion",
                        "creation_distribution",
                        0.20,
                        metric("catch_rate", 0.60),
                        metric("yards_after_catch_per_reception", 0.40),
                    ),
                    domain(
                        "scoring",
                        "scoring_finishing",
                        0.24,
                        metric("touchdown_rate"),
                    ),
                    domain(
                        "security",
                        "possession_security",
                        0.20,
                        metric("turnover_rate", higher_is_better=False),
                    ),
                ),
            )
            for role, label, minimum in [
                ("WR", "Wide receiver", 40),
                ("TE", "Tight end", 30),
            ]
        ],
        *[
            RoleSpec(
                "nfl",
                role,
                label,
                0,
                "offensive snaps",
                (),
                "abstain_source_rights_and_label_limit",
                "Roster rows are retained, but no numeric target is released: the available "
                "exposure is derived from a red-posture PFR source and charged penalties are "
                "not a credible proxy for blocking quality.",
            )
            for role, label in [("OT", "Offensive tackle"), ("IOL", "Interior offensive line")]
        ],
        *[
            RoleSpec(
                "nfl",
                role,
                label,
                150,
                "defensive snaps / charted plays",
                domains,
            )
            for role, label, domains in [
                (
                    "EDGE",
                    "Edge defender",
                    (
                        domain("pass_rush", "defensive_disruption", 0.50, metric("sack_rate", 0.55), metric("qb_hit_rate", 0.45)),
                        domain("backfield_stops", "recovery_rebounding", 0.30, metric("negative_play_rate")),
                        domain("turnovers", "possession_security", 0.20, metric("forced_fumble_rate")),
                    ),
                ),
                (
                    "IDL",
                    "Interior defensive line",
                    (
                        domain("backfield_stops", "defensive_disruption", 0.45, metric("negative_play_rate")),
                        domain("pass_rush", "progression_territory", 0.40, metric("sack_rate", 0.55), metric("qb_hit_rate", 0.45)),
                        domain("turnovers", "possession_security", 0.15, metric("forced_fumble_rate")),
                    ),
                ),
                (
                    "LB",
                    "Off-ball linebacker",
                    (
                        domain("stops", "defensive_disruption", 0.40, metric("negative_play_rate", 0.55), metric("tackle_rate", 0.45)),
                        domain("coverage", "recovery_rebounding", 0.35, metric("interception_rate", 0.40), metric("pass_defended_rate", 0.60)),
                        domain("turnovers", "possession_security", 0.25, metric("forced_fumble_rate")),
                    ),
                ),
                (
                    "CB",
                    "Cornerback",
                    (
                        domain("coverage", "defensive_disruption", 0.68, metric("interception_rate", 0.40), metric("pass_defended_rate", 0.60)),
                        domain("stops", "recovery_rebounding", 0.17, metric("negative_play_rate", 0.45), metric("tackle_rate", 0.55)),
                        domain("turnovers", "possession_security", 0.15, metric("forced_fumble_rate")),
                    ),
                ),
                (
                    "S",
                    "Safety",
                    (
                        domain("coverage", "defensive_disruption", 0.52, metric("interception_rate", 0.45), metric("pass_defended_rate", 0.55)),
                        domain("stops", "recovery_rebounding", 0.28, metric("negative_play_rate", 0.40), metric("tackle_rate", 0.60)),
                        domain("turnovers", "possession_security", 0.20, metric("forced_fumble_rate")),
                    ),
                ),
            ]
        ],
        RoleSpec(
            "nfl",
            "K",
            "Placekicker",
            12,
            "field-goal attempts",
            (
                domain("field_goals", "scoring_finishing", 0.70, metric("field_goal_pct", 0.70), metric("long_field_goal_rate", 0.30)),
                domain("extra_points", "discipline_efficiency", 0.30, metric("extra_point_pct")),
            ),
        ),
        RoleSpec(
            "nfl",
            "P",
            "Punter",
            25,
            "punts",
            (
                domain("field_position", "progression_territory", 0.65, metric("net_yards_per_punt", 0.65), metric("inside_20_rate", 0.35)),
                domain("error_avoidance", "possession_security", 0.35, metric("touchback_rate", 0.55, higher_is_better=False), metric("punt_block_rate", 0.45, higher_is_better=False)),
            ),
        ),
        RoleSpec(
            "nfl",
            "LS",
            "Long snapper",
            0,
            "special-team snaps",
            (),
            "abstain_no_public_label",
            "The public sources identify long snappers but do not provide a credible individual performance label.",
        ),
    ]


def _nba_specs() -> list[RoleSpec]:
    shared_security = domain(
        "ball_security",
        "possession_security",
        0.13,
        metric("turnovers_per_36", higher_is_better=False),
        metric("assist_turnover_ratio", 0.6),
    )
    discipline = domain(
        "discipline",
        "discipline_efficiency",
        0.05,
        metric("fouls_per_36", higher_is_better=False),
    )
    return [
        RoleSpec(
            "nba",
            "guard",
            "Guard",
            500,
            "minutes",
            (
                domain("scoring", "scoring_finishing", 0.30, metric("points_per_36", 0.40), metric("true_shooting_pct", 0.32), metric("effective_fg_pct", 0.18), metric("free_throw_attempt_rate", 0.10)),
                domain("creation", "creation_distribution", 0.28, metric("assists_per_36", 0.65), metric("assist_turnover_ratio", 0.35)),
                shared_security,
                domain("disruption", "defensive_disruption", 0.15, metric("steals_per_36", 0.75), metric("blocks_per_36", 0.25)),
                domain("recovery", "recovery_rebounding", 0.09, metric("defensive_rebounds_per_36")),
                discipline,
            ),
        ),
        RoleSpec(
            "nba",
            "forward",
            "Forward / wing",
            500,
            "minutes",
            (
                domain("scoring", "scoring_finishing", 0.28, metric("points_per_36", 0.40), metric("true_shooting_pct", 0.32), metric("effective_fg_pct", 0.18), metric("free_throw_attempt_rate", 0.10)),
                domain("creation", "creation_distribution", 0.19, metric("assists_per_36", 0.70), metric("assist_turnover_ratio", 0.30)),
                shared_security,
                domain("disruption", "defensive_disruption", 0.17, metric("steals_per_36", 0.55), metric("blocks_per_36", 0.45)),
                domain("recovery", "recovery_rebounding", 0.18, metric("defensive_rebounds_per_36", 0.70), metric("offensive_rebounds_per_36", 0.30)),
                discipline,
            ),
        ),
        RoleSpec(
            "nba",
            "center",
            "Center / interior big",
            400,
            "minutes",
            (
                domain("finishing", "scoring_finishing", 0.25, metric("points_per_36", 0.32), metric("true_shooting_pct", 0.58), metric("free_throw_attempt_rate", 0.10)),
                domain("creation", "creation_distribution", 0.11, metric("assists_per_36", 0.65), metric("assist_turnover_ratio", 0.35)),
                shared_security,
                domain("rim_disruption", "defensive_disruption", 0.23, metric("blocks_per_36", 0.75), metric("steals_per_36", 0.25)),
                domain("recovery", "recovery_rebounding", 0.23, metric("defensive_rebounds_per_36", 0.65), metric("offensive_rebounds_per_36", 0.35)),
                discipline,
            ),
        ),
    ]


def _nhl_specs() -> list[RoleSpec]:
    specs: list[RoleSpec] = []
    for role, label, weights in [
        ("center", "Center", (0.27, 0.23, 0.16, 0.16, 0.18)),
        ("left_wing", "Left wing", (0.34, 0.24, 0.15, 0.17, 0.10)),
        ("right_wing", "Right wing", (0.34, 0.24, 0.15, 0.17, 0.10)),
        ("defense", "Defense", (0.16, 0.25, 0.14, 0.28, 0.17)),
    ]:
        scoring, creation, security, disruption, territory = (value * 0.95 for value in weights)
        specs.append(
            RoleSpec(
                "nhl",
                role,
                label,
                400,
                "minutes",
                (
                    domain("scoring", "scoring_finishing", scoring, metric("goals_per_60", 0.35), metric("expected_goals_per_60", 0.30), metric("shots_on_goal_per_60", 0.15), metric("high_danger_shots_per_60", 0.20)),
                    domain("creation", "creation_distribution", creation, metric("primary_assists_per_60", 0.65), metric("secondary_assists_per_60", 0.35)),
                    domain("puck_security", "possession_security", security, metric("giveaways_per_60", higher_is_better=False), metric("takeaway_giveaway_ratio", 0.6)),
                    domain("disruption", "defensive_disruption", disruption, metric("takeaways_per_60", 0.45), metric("blocks_per_60", 0.35), metric("hits_per_60", 0.20)),
                    domain("territory", "progression_territory", territory, metric("on_ice_xgoal_pct", 0.40), metric("relative_xgoal_pct", 0.30), metric("on_ice_corsi_pct", 0.15), metric("relative_corsi_pct", 0.15)),
                    domain("discipline", "discipline_efficiency", 0.05, metric("penalty_differential_per_60")),
                ),
            )
        )
    specs.append(
        RoleSpec(
            "nhl",
            "goalie",
            "Goalie",
            900,
            "minutes",
            (
                domain("shot_prevention", "defensive_disruption", 0.62, metric("goals_saved_above_expected_per_60", 0.60), metric("save_pct", 0.40)),
                domain("danger_control", "recovery_rebounding", 0.28, metric("high_danger_save_pct")),
                domain("rebound_control", "possession_security", 0.10, metric("rebound_rate", higher_is_better=False)),
            ),
        )
    )
    return specs


def _epl_specs() -> list[RoleSpec]:
    return [
        RoleSpec(
            "epl",
            "GK",
            "Goalkeeper",
            900,
            "minutes",
            (
                domain("shot_stopping", "defensive_disruption", 0.48, metric("saves_per_90", 0.35), metric("goals_conceded_per_90", 0.25, higher_is_better=False), metric("goal_prevention_over_expected_per_90", 0.40)),
                domain("clean_sheets", "recovery_rebounding", 0.32, metric("clean_sheet_rate")),
                domain("penalties", "possession_security", 0.20, metric("penalties_saved_per_90")),
            ),
            "research_proxy",
            "Goals conceded and clean sheets are team-dependent; historical public data do not isolate post-shot shot-stopping quality.",
        ),
        RoleSpec(
            "epl",
            "DEF",
            "Defender",
            900,
            "minutes",
            (
                domain("defensive_outcome", "defensive_disruption", 0.40, metric("clean_sheet_rate", 0.55), metric("goals_conceded_per_90", 0.45, higher_is_better=False)),
                domain("attacking_output", "creation_distribution", 0.28, metric("assists_per_90", 0.30), metric("creativity_per_90", 0.25), metric("expected_assists_per_90", 0.45)),
                domain("finishing", "scoring_finishing", 0.17, metric("goals_per_90", 0.35), metric("threat_per_90", 0.20), metric("expected_goals_per_90", 0.30), metric("finishing_over_expected_per_90", 0.15)),
                domain("discipline", "discipline_efficiency", 0.15, metric("cards_per_90", higher_is_better=False)),
            ),
            "limited_team_context_proxy",
            "Broad FPL defender role; clean sheets and goals conceded contain substantial team context and do not separate center-backs from fullbacks.",
        ),
        RoleSpec(
            "epl",
            "MID",
            "Midfielder",
            900,
            "minutes",
            (
                domain("creation", "creation_distribution", 0.45, metric("assists_per_90", 0.25), metric("creativity_per_90", 0.25), metric("expected_assists_per_90", 0.35), metric("expected_goal_involvements_per_90", 0.15)),
                domain("scoring", "scoring_finishing", 0.40, metric("goals_per_90", 0.30), metric("threat_per_90", 0.25), metric("expected_goals_per_90", 0.30), metric("finishing_over_expected_per_90", 0.15)),
                domain("discipline", "discipline_efficiency", 0.15, metric("cards_per_90", higher_is_better=False)),
            ),
            "research_proxy",
            "Broad FPL midfielder role combines defensive, central, attacking and wide midfield roles.",
        ),
        RoleSpec(
            "epl",
            "FWD",
            "Forward",
            700,
            "minutes",
            (
                domain("finishing", "scoring_finishing", 0.55, metric("goals_per_90", 0.30), metric("threat_per_90", 0.25), metric("expected_goals_per_90", 0.30), metric("finishing_over_expected_per_90", 0.15)),
                domain("creation", "creation_distribution", 0.35, metric("assists_per_90", 0.25), metric("creativity_per_90", 0.25), metric("expected_assists_per_90", 0.35), metric("expected_goal_involvements_per_90", 0.15)),
                domain("discipline", "discipline_efficiency", 0.10, metric("cards_per_90", higher_is_better=False)),
            ),
        ),
    ]


def role_specs() -> dict[str, RoleSpec]:
    specs = _nfl_specs() + _nba_specs() + _nhl_specs() + _epl_specs()
    result = {spec.key: spec for spec in specs}
    if len(result) != len(specs):
        raise AssertionError("Duplicate sport-role key in all-role registry")
    return result


def registry_payload() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "role_taxonomy_version": ROLE_TAXONOMY_VERSION,
        "target_version": TARGET_VERSION,
        "bridge_version": BRIDGE_VERSION,
        "frozen_test_season": FROZEN_TEST_SEASON,
        "roles": {key: asdict(spec) for key, spec in role_specs().items()},
        "score_contract": {
            "observed_role_percentile": "Retrospective role-season peer comparison.",
            "native_forecast_percentile": "Next-season estimate using only information available before that season.",
            "native_build_profile_forecast_percentile": "Next-season benchmark using only build and canonical playing-profile dimensions; checked against build alone.",
            "cross_sport_physical_estimate": "Target-role model using build only.",
            "cross_sport_transfer_guesstimate": "Unvalidated target-role analogy using build plus a fixed intersection of sport-relative performance dimensions.",
        },
    }
