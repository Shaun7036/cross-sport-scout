# Athlete Translation Lab: methodology and current state

- Status: all-role research prototype
- Project seasons: 2021–2025 (`2025` means 2025–26 for NBA, NHL, and EPL)
- Frozen evaluation season: 2025

## 1. Purpose

This project has two related, but scientifically different, aims:

1. describe how an athlete performed relative to same-role peers in the athlete's own sport and season; and
2. generate an auditable cross-sport analogy for target roles using the athlete's listed build and a fixed set of source-sport performance dimensions.

The second result is intentionally called a **transfer guesstimate**. No public dataset in this repository contains enough elite athletes who changed among the NFL, NBA, NHL, and Premier League to train or validate a direct sport-switch outcome model. The system therefore cannot estimate the probability that a player would make a roster, learn the sport, avoid injury, or perform at a given level after switching.

The implementation favors visible evidence states over false precision. Missing required inputs, absent model heads, failed bridge-proxy gates, and extreme out-of-domain profiles withhold values. Failed physical or native evidence gates may still return a numeric estimate, but only with an explicit experimental/unsupported label.

## 2. End-to-end workflow

~~~text
cached source snapshots + provenance sidecars
                    │
                    ▼
        sport-specific all-role adapters
                    │
                    ▼
 canonical player-season panel (one row per sport/player/season)
                    │
                    ▼
 role-season shrinkage, percentiles, dimensions, eligibility
             ┌──────┼────────┐
             ▼      ▼        ▼
       physical   native   bridge proxy
         heads   forecasts    heads
             └──────┼────────┘
                    ▼
 structured four-score response + static player explorer
~~~

The main orchestration is implemented in [`all_roles_pipeline.py`](../src/possession_lab/all_roles_pipeline.py). The role and metric contract is data-driven and versioned in [`all_roles_registry.py`](../src/possession_lab/all_roles_registry.py), with a generated JSON copy at [`metadata/all_roles_metric_registry.json`](../metadata/all_roles_metric_registry.json).

## 3. Current data universe

The current processed snapshot has 27,652 player-seasons and 10,311 distinct sport-athlete identities. These counts are derived from the present cache and may change after an upstream refresh or cleaning change.

| Sport | Rows | Athletes | Universe | Physical coverage note |
|---|---:|---:|---|---|
| NFL | 15,518 | 5,850 | Roster-inclusive; unresolved generic positions remain visible | Height/weight are usually season-attached roster listings, not measured dates |
| NBA | 2,866 | 1,030 | Confirmed regular-season appearances | Complete current/undated profile values, not annual weigh-ins |
| NHL | 5,263 | 1,654 | Appearance-based skaters and goalies | Near-complete current/undated bios |
| EPL | 4,005 | 1,777 | FPL player-season rows in broad roles | Sparse current ESPN profile matches; not historical measurements |

The canonical grain is `(sport, player_id, season)`. Duplicate keys fail the build. Height outside 140–230 cm and weight outside 35–230 kg are quarantined as missing, with the rejected raw value and quality flag retained for audit.

Raw sources and processed player tables are ignored by Git. Aggregate reports and registries are versioned. The exact current counts and coverage belong in [`data_build.json`](../reports/all_roles/data_build.json), not in application code.

## 4. Role taxonomy and opportunity gates

Roles are intentionally broad enough to be represented by the available sources across all five seasons. Registration or model fitting does not imply statistical support. Opportunity thresholds define the reference cohort for the observed target; they are not statements about roster value.

| Sport | Role | Minimum opportunity | Performance domains or status |
|---|---|---:|---|
| NFL | QB | 150 dropbacks | Passing value, creation, scoring, possession security |
| NFL | RB/FB | 60 touches | Ground value, receiving, scoring, possession security |
| NFL | WR | 40 targets | Receiving value, conversion, scoring, possession security |
| NFL | TE | 30 targets | Receiving value, conversion, scoring, possession security |
| NFL | OT | — | **Abstain:** no release-safe individual performance label |
| NFL | IOL | — | **Abstain:** no release-safe individual performance label |
| NFL | EDGE | 150 defensive snaps/charted plays | Pass rush, backfield stops, turnovers |
| NFL | IDL | 150 defensive snaps/charted plays | Backfield stops, pass rush, turnovers |
| NFL | LB | 150 defensive snaps/charted plays | Stops, coverage, turnovers |
| NFL | CB | 150 defensive snaps/charted plays | Coverage, stops, turnovers |
| NFL | S | 150 defensive snaps/charted plays | Coverage, stops, turnovers |
| NFL | K | 12 field-goal attempts | Field goals, extra points |
| NFL | P | 25 punts | Field position, error avoidance |
| NFL | LS | — | **Abstain:** no credible public individual performance label |
| NBA | Guard | 500 minutes | Scoring, creation, security, disruption, recovery |
| NBA | Forward | 500 minutes | Scoring, creation, security, disruption, recovery |
| NBA | Center | 400 minutes | Finishing, creation, security, rim disruption, recovery |
| NHL | Center | 400 minutes | Scoring, creation, security, disruption, territory |
| NHL | Left wing | 400 minutes | Scoring, creation, security, disruption, territory |
| NHL | Right wing | 400 minutes | Scoring, creation, security, disruption, territory |
| NHL | Defense | 400 minutes | Scoring, creation, security, disruption, territory |
| NHL | Goalie | 900 minutes | Shot prevention, danger control, rebound control |
| EPL | GK | 900 minutes | Shot stopping, clean sheets, penalties |
| EPL | DEF | 900 minutes | Team defensive outcome, attacking output, finishing, discipline |
| EPL | MID | 900 minutes | Creation, scoring, discipline |
| EPL | FWD | 700 minutes | Finishing, creation, discipline |

The full metric weights, directions, descriptions, and limitations are in the generated metric registry. A role being registered does not guarantee that a model head is fit or supported.

### 4.1 NFL seasonal role assignment

The NFL adapter uses every available regular-season weekly depth-chart observation. It maps each specific weekly listing to the broad taxonomy and selects the modal canonical role for that player-season. A count tie is resolved by the most recently observed week and then a deterministic lexical role order; a tie flag remains in the panel.

Generic `DB`, `DL`, and `OL` listings do not vote. A generic-only history remains unregistered rather than being guessed into CB/S, EDGE/IDL, or OT/IOL. `OLB` is grouped with EDGE as an explicit broad-taxonomy assumption, not proof of the player's assignment on each snap.

OT, IOL, and LS remain useful roster/build observations, but their performance fields, opportunity, and model targets are withheld. The hardened all-role adapter does not depend on conditional PFR-derived snap files for these roles.

### 4.2 Other sport boundaries

- NBA uses guard, forward, and center because profile abbreviations are not reliable multi-season deployment histories. Handler, stopper, rim-protector, and matchup roles require lineup or tracking data.
- NHL preserves center, left wing, right wing, defense, and goalie. It does not infer line, pairing, special-team unit, shutdown assignment, or forechecking role.
- EPL preserves only GK, DEF, MID, and FWD. Current public history cannot defend a recent five-season CB/FB/WB/DM/CM/AM/wing/striker taxonomy.

## 5. Observed role-season targets

Observed targets are constructed independently inside each `(sport, role, season)` cohort by [`all_roles_targets.py`](../src/possession_lab/all_roles_targets.py).

For one atomic rate metric, let `x` be the player's observed rate and `o` the role-specific opportunity. The cohort's shrinkage exposure is:

~~~text
k = max(0.5 × median eligible opportunity,
        0.5 × minimum opportunity,
        1)
~~~

The reliability and shrunk metric are:

~~~text
r = o / (o + k)
shrunk_metric = r × x + (1 - r) × opportunity-weighted cohort prior
~~~

The shrunk values are converted to empirical 0–100 percentiles among eligible peers. Lower-is-better metrics are reversed. Metric percentiles roll into declared domains, and domain percentiles roll into a role-quality composite using weights fixed in the registry. The composite is ranked again within the role-season reference cohort.

The output fields deliberately stay separate:

- `quality_percentile` and its alias `observed_role_percentile`: per-opportunity role quality;
- `availability_percentile`: opportunity relative to athletes with positive opportunity;
- `total_impact_percentile`: a reranked `75% quality + 25% availability` summary; and
- `sustained_3y_percentile`: an inclusive trailing three-season quality index with annual decay `0.70^age`.

Rows below the opportunity threshold receive `target_status = low_sample`. Their shrunk descriptive percentiles are useful context, but they are excluded from supervised labels. Rows with no positive opportunity are `not_observed`. Abstention and unregistered rows remain in the panel with null performance scores.

This season-relative design reduces unit and scoring-environment drift. It does not make percentile differences interval-scaled, erase team/tactical context, or prove that the semantic dimensions mean the same thing across sports.

## 6. Shared performance dimensions

Role domains are assigned to a small vocabulary used only for explicit cross-sport analogy:

- `scoring_finishing`
- `creation_distribution`
- `possession_security`
- `defensive_disruption`
- `recovery_rebounding`
- `progression_territory`
- `discipline_efficiency`

For example, NBA assists and an NHL primary-assist profile can both inform `creation_distribution`, while they remain different sport-specific observations. The mapping says the concepts are plausibly analogous; it does not assert a shared physiological or psychological latent variable.

No current dimension is labeled “awareness,” “reaction speed,” “decision-making,” or “game IQ.” Inferring those mental traits from public box scores would exceed the evidence. A later mental/game-awareness layer should begin with a predeclared construct, a repeatable measurement protocol or coach rubric, reliability testing, and sport-specific calibration before any cross-sport normalization.

## 7. Four-score output contract

### 7.1 Observed role percentile

- **Input:** current player-season performance and role-specific opportunity.
- **Reference:** eligible athletes in the same sport, role, and season.
- **Use:** retrospective description and target face-validity checks.
- **Not:** a prediction, career score, roster probability, or complete measure of player value.

### 7.2 Native forecast percentile

- **Target:** next season's observed role percentile.
- **Features:** height, weight, BMI, age, prior observed percentile, prior availability, trailing three-year percentile, and the role's prior-season performance dimensions.
- **Pairing rule:** same athlete, consecutive seasons, same broad role, and eligible in both the prior and realized target seasons.
- **Use:** a research next-season backtest within the athlete's current sport and role, using lagged performance plus listed physical profiles.
- **Evidence:** compared with the better of previous-season and trailing-three-year history baselines. Unsupported estimates remain explicitly experimental.

Role transitions are excluded from this model. Predicting a player's new native role is a different task and needs a transition model.

### 7.3 Cross-sport physical estimate

- **Target:** target-role observed percentile.
- **Features:** height, weight, BMI, and age.
- **Use:** a target-role physical association.
- **Evidence:** evaluated against a neutral 50th-percentile baseline.
- **Not:** evidence that the athlete has the required technique, perception, conditioning, or sport experience.

Height and weight are required at scoring time. Age may be imputed from the training cohort and is reported as such in the contribution output.

### 7.4 Cross-sport transfer guesstimate

For every ordered source-role → target-role pair, the registry takes the fixed intersection of their semantic dimensions. At least two shared dimensions are required. A target-side ridge model is then trained among eligible **target-role athletes** using build plus those target athletes' own dimension percentiles.

At scoring time, a source athlete's source-role percentiles are inserted into the identically named fields. This produces a useful “what does this profile resemble?” calculation, but it is a distribution-shift assumption.

The bridge gate tests whether the head reconstructs held-out target-role percentiles from target-role inputs. Even a passing gate provides **no observed cross-sport transfer validation**. It should be read as target-proxy reconstruction evidence only. The reported sensitivity range uses target-proxy residual error and is not a calibrated confidence interval.

Transfer is withheld when:

- the source season is not eligible;
- fewer than two dimensions intersect;
- required source dimensions, height, or weight are missing;
- the target-proxy reconstruction head fails its evidence gate; or
- the profile is materially out of the target head's physical or capability reference domain.

## 8. Model training and evaluation

All three supervised model families use a small deterministic ridge regression implementation in [`all_roles_models.py`](../src/possession_lab/all_roles_models.py):

1. numeric missing values allowed by the deployment contract are imputed with medians learned from the training rows;
2. features are standardized using training-row means and standard deviations;
3. `RidgeCV` selects `alpha` from `0.1, 1, 10, 100, 1000`; and
4. predictions are clipped to the 0–100 percentile range, with saturation warnings near the limits.

### 8.1 Eligible-only, deployment-matched cohorts

Supervised labels always require `target_status == eligible` and a finite observed target. The fit/evaluation cohort must also contain every non-imputable field required by the deployed scorer:

- physical heads: height and weight;
- native heads: height, weight, and all declared source-role dimensions; and
- bridge heads: height, weight, and every fixed shared dimension.

This avoids evaluating on rows the live scorer would have withheld. Reports keep candidate, eligible-label, and usable-deployment counts separate so missing physical coverage cannot masquerade as model evidence. Age remains an imputable feature; BMI is deterministically derived from height and weight.

### 8.2 Time split and baselines

- Seasons before 2025 train the frozen evaluation model.
- Season 2025 is the frozen test.
- Earlier seasons also produce rolling-origin diagnostics when samples permit.
- The final local artifact is refit on all available eligible, deployment-usable rows across seasons after evaluation, so portal scores use the full research snapshot.
- Metrics include MAE, RMSE, and Spearman rank correlation.
- A newcomer/unseen-history slice reports athletes absent from the pre-2025 training history.

Physical and bridge proxy heads are compared with a neutral prediction of 50. Native forecasts are compared with the better frozen-test history baseline: the player's prior-season percentile or trailing-three-year percentile.

Some NBA, NHL, and EPL physical profiles are current or undated and may be repeated across historical rows. The performance split is chronological, but the full feature set is therefore not completely timestamp-clean; these outputs should not be presented as deployment-grade prospective forecasts.

The 90% MAE-advantage interval resamples frozen-season test athletes by `player_id`. Because the frozen test contains one row per athlete-role, this is effectively a test-athlete row bootstrap; the train/test split is chronological, not athlete-disjoint. The unseen-history slice separately reports athletes absent from pre-2025 training. “Supported” requires the declared model to beat its baseline and the lower interval bound to be positive. Insufficient or failed evidence remains visible in the report and scorer.

### 8.3 Out-of-domain checks

Each fitted head stores reference summaries for its features. The scorer reports feature-level robust distances and 1st–99th percentile checks. Extreme build distance or extreme capability-dimension distance withholds a score. Age can produce a warning without automatically withholding the result. These are pragmatic diagnostics, not a full multivariate uncertainty model.

## 9. Face-validity checks

Two frozen NBA checks protect the target construction from obvious failures:

- Stephen Curry (`player_id = 3975`) must be at least the 90th percentile in the guard scoring domain in his latest observed season.
- LeBron James (`player_id = 1966`) must be at least the 90th percentile in the forward creation domain in his latest observed season.

An identity guard also verifies that Seth Curry (`player_id = 2326307`) is not confused with Stephen. These checks are declared in code and are not used to retune the metric weights around those names.

A pass shows that selected native domain targets meet basic face validity. It does not validate the broad overall role composite, native forecasting, or cross-sport translation. Current values and statuses are generated in [`observed_targets.json`](../reports/all_roles/observed_targets.json).

## 10. Scoring interfaces

### 10.1 Known player

Known-player lookup reads the processed observed-score panel. The player ID is source-specific, so source sport is mandatory.

~~~bash
uv run athlete-translation-lab all-roles-score \
  --sport nba --player-id 1966 --season 2025 --target-sport nfl
~~~

If `--season` is omitted, the latest available player-season is used. If `--target-sport` is omitted, all four target sports are returned.

### 10.2 Custom physical profile

~~~bash
uv run athlete-translation-lab all-roles-score \
  --height-cm 198 --weight-kg 102 --age 25 --target-sport nhl
~~~

This profile has no observed source-sport performance, so only physical estimates are applicable.

### 10.3 Custom normalized performance profile

[`examples/all_roles_athlete.json`](../examples/all_roles_athlete.json) shows the complete input shape for a hypothetical eligible source athlete. Dimension values must already be 0–100 percentiles computed against the declared source role-season. Raw points, tackles, or assists are not accepted as if they were comparable dimensions.

~~~bash
uv run athlete-translation-lab all-roles-score \
  --profile examples/all_roles_athlete.json --target-sport nfl
~~~

The scorer returns model status, evidence class, features used, largest signed linear contributions, OOD diagnostics, and withholding reasons alongside each numeric value.

## 11. Player explorer

The all-role portal is a static presentation layer over a frozen local export:

~~~bash
uv run athlete-translation-lab build-all-roles-portal
uv run athlete-translation-lab all-roles-portal
~~~

Open `http://127.0.0.1:8766`. This is intentionally separate from the legacy possession portal on port 8765.

The export chooses each athlete's latest player-season with positive observed opportunity, while retaining registered abstention roles with roster evidence. It includes a searchable player catalog and per-player structured score files. It does not call a third-party model API in the browser. Generated row-level JSON lives under `portal-all-roles/data/` and is ignored by Git.

The presentation hierarchy should remain:

1. observed native performance for the player's own sport;
2. native forecast, if supported/applicable;
3. transfer guesstimate for a different sport, if available; and
4. physical-only association beside it, never multiplied into the transfer number.

### 11.1 Compact comparison view

The original all-role explorer above is preserved as the full evidence view. A second frontend presents one selected target role at a time while reading the same frozen export:

~~~bash
uv run athlete-translation-lab build-all-roles-compact-portal
uv run athlete-translation-lab all-roles-compact-portal
~~~

Open `http://127.0.0.1:8767/compact/`. The compact frontend lives under `portal-all-roles/compact/`; player data remain in the single ignored `portal-all-roles/data/` directory. The existing 8766 server also exposes the compact page at `/compact/`.

The compact page keeps four distinct claims visible: observed native standing, native next-season forecast, target-role physical association, and the cross-sport transfer analogy. It never substitutes one when another is withheld. Its Body fit card is a fifth, non-predictive diagnostic: an empirical survival percentile of Mahalanobis distance in height/weight space. The reference uses one latest selectable profile per target-role athlete, a 10% diagonal covariance shrinkage, and at least 20 athletes. Higher means more central to that role's current build distribution—not more capable.

## 12. Outputs and how to read them

| Path | Purpose |
|---|---|
| [`reports/all_roles/data_build.json`](../reports/all_roles/data_build.json) | Current row, athlete, role, season, and physical coverage |
| [`reports/all_roles/observed_targets.json`](../reports/all_roles/observed_targets.json) | Role-season target priors, eligible reference counts, skipped cohorts, and NBA sanity checks |
| [`reports/all_roles/model_evaluation.json`](../reports/all_roles/model_evaluation.json) | Full per-head fit metadata, frozen metrics, baselines, evidence gates, and usable coverage |
| [`reports/all_roles/model_evidence_summary.csv`](../reports/all_roles/model_evidence_summary.csv) | Compact physical/native evidence table |
| [`reports/all_roles/role_summary.csv`](../reports/all_roles/role_summary.csv) | Aggregate role coverage and score distributions |
| [`reports/all_roles/eda_summary.json`](../reports/all_roles/eda_summary.json) | EDA file inventory and summary metadata |
| [`metadata/all_roles_metric_registry.json`](../metadata/all_roles_metric_registry.json) | Generated versioned role, metric, domain, and score contract |
| [`metadata/all_roles_source_matrix.json`](../metadata/all_roles_source_matrix.json) | Machine-readable source scope and governance posture |

Model-head counts and evidence statuses are build outputs, not stable design constants. After any adapter, registry, cohort, or model change, rerun the pipeline and use the regenerated reports as the source of truth.

## 13. Sources and governance

The detailed audit is [`all_roles_data_sources.md`](all_roles_data_sources.md). The short operational rules are:

| Sport | Core all-role sources | Current research posture |
|---|---|---|
| NFL | nflverse weekly rosters, weekly statistics, play-by-play, registry/schedules, and participation-derived defensive context | Core releases are attribution-friendly; participation has separate provider/share-alike obligations. Conditional PFR/community enrichments stay out of release training. |
| NBA | SportsDataverse-packaged ESPN profiles, game rosters, and player box scores | Local research prototype; the package does not settle every ESPN/NBA upstream redistribution or commercial right. |
| NHL | MoneyPuck designated skater/goalie summaries and lookup, plus NHL Stats bio enrichment | Noncommercial research with clear MoneyPuck attribution; do not assume permission for raw redistribution or broader commercial use. |
| EPL | Vaastav FPL archive plus sparse ESPN profile enrichment | Broad-role local research only. FPL/Understat/ESPN upstream rights remain unresolved; FPL-Core defensive/tracking fields are excluded from all-role training. |

- preserve each raw file's `.source.json` sidecar and SHA-256;
- regenerate [`download_manifest.json`](../metadata/download_manifest.json) after acquisition;
- do not commit or redistribute raw or row-level derived tables by default;
- keep MoneyPuck use noncommercial with clear attribution unless permission expands it;
- review ESPN/NBA and ESPN/FPL upstream rights before redistribution or commercialization;
- keep conditional PFR/community NFL enrichments out of release training until cleared; and
- do not allow a red-posture source to enter a public model indirectly through a denominator or derived feature.

The all-role NFL adapter's OT/IOL/LS abstention is an example of this last rule: roster identity is preserved, but conditional snap-derived performance labels are not used.

## 14. What is complete and what remains

Implemented now:

- independent all-role repository and command surface;
- five-season adapters and canonical player-season panel for all four sports;
- broad role registry, opportunity gates, shrinkage, domains, and season percentiles;
- explicit low-sample, missing, unregistered, and abstention states;
- physical association, same-role native forecast, and ordered bridge model families;
- frozen 2025 evaluation, rolling diagnostics, baselines, clustered-bootstrap evidence gates, and OOD checks;
- NBA identity and face-validity guards;
- aggregate EDA and a minimal static all-role player explorer; and
- source matrix and release-governance audit.

Highest-priority next work:

1. freeze and review one reproducible source snapshot after every code/data hardening change;
2. replace unresolved or conditional sources before public/commercial release;
3. acquire dated, rights-cleared physical measurements instead of treating profile listings as longitudinal measurements;
4. add licensed tracking/lineup data before attempting finer tactical roles;
5. validate mental or awareness constructs with explicit measurement protocols rather than box-score labels;
6. seek actual cross-sport labels—crossover athletes, controlled tests, coach assessments, or prospective trials—to validate transfer rather than target reconstruction; and
7. evaluate richer or hierarchical models only after the label and validation design improve. More complex algorithms cannot repair an invalid transfer target.

## 15. Reproduction checklist

~~~bash
# 1. Install
uv sync --extra dev --python 3.12

# 2. Rebuild all-role panels, targets, models, reports, and EDA.
#    This requires the raw cache and prerequisite sport-specific processed panels;
#    it does not acquire sources or rebuild the base sport pipelines.
uv run athlete-translation-lab run-all-roles

# 3. Build the static explorer export
uv run athlete-translation-lab build-all-roles-portal

# 4. Verify code and tests
uv run ruff check src tests
uv run pytest -q -p no:cacheprovider

# 5. Inspect generated evidence before making claims
git status --short
~~~

Do not present a score unless its `status`, `evidence_class`, reference cohort, source timing, and limitations travel with it.
