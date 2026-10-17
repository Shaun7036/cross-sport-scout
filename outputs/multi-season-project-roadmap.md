# Multi-season cross-sport possession-winning project roadmap

Revised 1 October 2026

## Revised decision

The project will use a longitudinal player panel rather than a single 2025–26 snapshot.

The minimum common window is:

| Sport | Five-season window | Season used for final test |
|---|---|---|
| NFL | 2021–2025 | 2025 |
| NBA | 2021–22 through 2025–26 | 2025–26 |
| NHL | 2021–22 through 2025–26 | 2025–26 |
| Premier League | 2021–22 through 2025–26 | 2025–26 |

This window is a good common baseline because:

- The NFL moved to a 17-game regular season in 2021.
- NHL EDGE tracking begins in 2021–22, and the NHL has had 32 teams throughout this window.
- It avoids the most disruptive shortened/empty-stadium pandemic seasons.
- NBA Hustle statistics have existed since the 2016 postseason, so all five selected seasons are within the tracked era. See the [NBA Hustle history](https://www.nba.com/news/history-hustle-award-winners).
- Five seasons provide enough repeated observations for trends and age effects without forcing the four sports into very different eras.

Where definitions and licensing permit, collect 2019–20 and 2020–21 as an extended archive. Use them for sensitivity analysis and additional rolling-validation folds, not as a requirement for the first build.

The existing 2025–26 source audit remains the latest-season source map. Its sources should now be queried or downloaded for every season in the selected window where the same definition is available.

---

# 1. Split the project into distinct questions

One model should not be asked to perform description, forecasting, and cross-sport projection simultaneously. Build four related products.

## A. Descriptive archetype model

Question:

> Which physical and behavioral archetypes were successful possession winners across the completed five-season window?

This model may use completed 2025–26 performance. It can identify clusters, role archetypes, late developers, unusually effective body types, and players whose results exceeded their physical peer group.

It makes no claim that the results were knowable before the season.

## B. Returning-player forecast

Question:

> Using only information available before season t, how well can we predict a returning player's opportunity and possession-winning effectiveness in season t?

For the final test:

- Features end at 2024–25.
- The target is 2025–26.
- The player may have appeared in earlier target-league seasons.
- Players who subsequently record zero appearances remain part of the availability evaluation.

## C. Cold-start role-fit model

Question:

> Based on physical measurements and pre-entry testing, which target-league roles best match a rookie, prospect, or athlete with no history in that target league?

This model cannot use target-league performance history, player identity effects, draft outcome, or post-entry deployment.

Its output should be framed as role compatibility or archetype similarity—not proof that an athlete could successfully change sports.

## D. Cross-sport enriched model

Question:

> After adding source-sport behavioral dimensions, does the athlete still resemble successful target-sport possession-winning roles?

This is a separate, enhanced tier because it cannot score candidates who provide physical measurements only.

---

# 2. The 2025–26 season has two separate uses

Maintain two physically separate feature snapshots.

## Descriptive 2025–26 snapshot

- May include 2025–26 performance, role, team, and movement data.
- Used for completed-season rankings, archetypes, and retrospective hidden-value analysis.

## Predictive 2025–26 snapshot

- Contains only information available before the applicable 2025–26 season-opening date.
- Cannot include 2025–26 minutes, team role, roster outcome, injuries, weight listings published later, or season performance.
- Used once for final out-of-sample evaluation.

Mixing these snapshots would cause target leakage.

---

# 3. Observation units

Keep the finest feasible records and aggregate upward.

| Layer | Unit | Purpose |
|---|---|---|
| Measurement | Player × observation date × source | Preserves every physical/test value and its age |
| Roster | Player × team × effective date interval | Captures trades, waivers, injuries, loans, call-ups, and short contracts |
| Appearance | Player × game/week | Holds role, exposure, events, and game context |
| Player-team-season | Player × team stint × season | Preserves team and scheme context |
| Player-season-role | Player × season × role | Separates meaningful role changes and role shares |
| Player-season | Player × league season | Primary modeling row |
| Player-window | Player × anchor date × lookback window | Leakage-safe prior-season features |

A traded player normally has one league-level player-season outcome, built from team-stint rows. Do not count the player twice merely because they changed teams.

“All rostered players” means the union of roster spells, not only athletes who appeared. Preserve these distinct states:

- Rostered but never appeared.
- Appeared and recorded zero events.
- Had no relevant opportunity.
- Event feed did not cover the game/player.
- Measurement unavailable.
- Metric structurally unavailable in that sport or season.

None of these states should be encoded as the same zero.

---

# 4. Canonical data model

## Identity and competition tables

### player

- Internal global player UUID.
- Canonical display name.
- Date of birth, nationality, and sex.
- No height or weight: those belong in dated measurement events.

### player_identity

Grain: source plus source player ID.

- Internal player UUID.
- Source ID and source player ID.
- Valid dates.
- Match method and confidence.
- Manually verified flag.

Never use name alone as a durable key. Ambiguous matches go into a review queue.

### competition, season, team, game

Maintain internal IDs and every source-specific ID. The season table must record:

- Human label.
- Start/end dates.
- Source-specific season code.
- Regular/postseason phase.
- Definition/version notes.

## Roster and role tables

### roster_spell

- Player, team, competition, season.
- Effective start and end.
- League roster versus matchday roster.
- Active, inactive, reserve, injured, practice/development, loan, or registration status.
- Source-listed position.
- Standardized role family.

### player_game

- Player, team, game.
- Starter/substitute/dressed status.
- Listed position and observed role.
- Minutes, time on ice, snaps, shifts, possessions, or other exposure.

### player_game_metric

Long-form metric storage:

- Metric code and definition version.
- Raw value and unit.
- Confirmed-zero / missing / estimated status.
- Source and snapshot.

### player_game_opportunity

- Opportunity code and count.
- Observed versus estimated.
- Estimation method.

Examples include defensive snaps, pass-rush snaps, coverage targets, matchup possessions, opponent attempts, duel opportunities, or opponent-possession minutes.

## Physical measurement tables

### measurement_event

One row per player, measurement, date, and source:

- Measurement type.
- Raw value/unit and standardized SI value.
- Observed date and date precision.
- Publication/availability date.
- Protocol and context.
- Official, estimated, or derived status.
- Source and reliability tier.

Useful metric codes include height, body mass, wingspan, standing reach, arm length, leg length, hand size, body fat, sprint splits, jumps, agility drills, strength tests, game maximum speed, and game distance.

Controlled combine/pro-day tests belong in measurement events. Match-derived speed belongs in player-game metrics and is aggregated by season. They are not interchangeable.

### player_season_measurement

This gold-layer table selects the appropriate pre-season observation for a specific analysis anchor while retaining:

- Source measurement-event ID.
- Years since measurement.
- Selection rule.
- Staleness and reliability flags.

## Aggregate and feature tables

### player_team_season

Team-stint performance and context.

### player_season

- League-wide seasonal totals.
- Exposure and opportunity.
- Raw rates.
- Shrunken/context-adjusted estimates.
- Availability and data-coverage indicators.

### feature_registry

For every feature:

- Versioned formula.
- Inputs and denominator.
- Lookback window.
- Cohort and normalization group.
- Point-in-time/leakage rule.

### player_feature

Grain: player × anchor date × feature version.

- Raw feature.
- Sport-role standardized z-score and percentile.
- Lookback start/end.
- Quality and coverage flags.

### source_registry and source_snapshot

Record publisher, URL, access method, coverage, terms/license classification, attribution, retrieval timestamp, query/file name, checksum, source schema version, and restrictions.

---

# 5. Physical-measurement policy

## Height and limb dimensions

- Preserve every sourced observation.
- For an adult season-start model, select the highest-reliability measurement available before the anchor date; use recency to break ties.
- Seasonal differences in adult height are usually listing/source noise.
- Carrying a verified combine wingspan, reach, arm, hand, or limb measurement forward is acceptable, but retain age at measurement and years elapsed.
- Never infer arm or leg length from height and present it as measured.

## Weight and body composition

- Treat weight as time-varying.
- Select the closest reliable pre-anchor measurement, preferably within 365 days.
- Flag values older than two years as stale rather than silently calling them current.
- Calculate weight change only when consecutive measurements use comparable sources or protocols.
- Keep roster weight, combine weight, and measured body composition as separate source concepts.

Recommended fields:

- Selected preseason weight.
- Source and observation date.
- Days since measurement.
- Roster-versus-combine indicator.
- Same-source year-over-year change.
- Missing/stale flag.

## Sprint, agility, power, and speed

- Combine/pro-day drills remain historical tests.
- Retain age at test and years since test.
- Previous-season in-game top speed, bursts, and distance are time-varying performance features.
- Do not carry a match-derived speed value forward and label it current.
- Do not compare a football 40-yard dash, basketball three-quarter sprint, hockey maximum skating speed, and soccer tracking speed as raw equivalents. Convert them to within-sport/role percentiles first.

## Missingness

Combine participation is selected by invitation, health, role, prospect quality, and choice. Record separate states where possible:

- Not eligible.
- Not invited.
- Invited but did not test.
- Partial testing.
- Source unavailable.
- Structurally unavailable in that sport.

Never replace a missing measurement with zero. Fit imputation and missingness handling only inside each training fold.

Maintain two model tiers:

1. **Core full-roster model:** age, height, weight, broad role information, and highly available features.
2. **Enhanced measured-athlete model:** combine, reach, wingspan, agility, power, and movement data.

Report performance separately for athletes with and without enhanced measurements.

---

# 6. Sport-specific five-season source plan

## NFL: seasons 2021–2025

The active first-sport workflow is in the companion [NFL possession-creation and defensive-disruption archetype plan](nfl-possession-archetype-plan.md).

This is the cleanest panel:

- nflverse weekly rosters are available much further back than 2021.
- Snap counts are available from 2012.
- PFR advanced defensive statistics are available from 2018.
- Play-by-play and player statistics cover the complete selected period.
- Participation data are available from 2016, but the provider changes: NFL NGS through 2022 and FTN from 2023. Preserve a provider/definition flag and do not assume every participation field is identical across the boundary. See the [nflverse participation documentation](https://nflreadr.nflverse.com/reference/load_participation.html).
- Depth-chart sourcing/schema changes near the end of the window, so do not use depth rank as an unversioned five-season feature.
- There were no normal in-person combine workouts in 2021; testing took place through college pro days. Label those results as pro-day observations rather than standard combine measurements. See the [NFL's 2021 format notice](https://www.nfl.com/news/nfl-memo-details-different-format-for-combine-individual-workouts-will-be-held-o).
- Historical combine data remain measurement events rather than seasonal records.

The [nflverse weekly-roster documentation](https://nflreadr.nflverse.com/reference/load_rosters_weekly.html) and [advanced-defense documentation](https://nflreadr.nflverse.com/reference/load_pfr_advstats.html) support the full five-season window.

## NBA: 2021–22 through 2025–26

- Traditional, Hustle, defensive tracking, speed/distance, matchup, and combine sources should be collected separately by season.
- Hustle metrics predate the complete window, supporting definition continuity at a high level.
- Preserve endpoint/schema snapshots because NBA website endpoints are undocumented and individual fields can change.
- The NBA moved to Hawk-Eye 3D optical tracking beginning in 2023–24. Treat pre-Hawk-Eye and Hawk-Eye tracking as separate regimes, run distribution-break checks, and normalize within season. See the [NBA/Sony announcement](https://pr.nba.com/nba-sony-hawk-eye-innovations-partnership).
- New AWS-derived defensive box score, shot-difficulty, gravity, and related products debuted in 2025–26. They are holdout-season enrichment, not five-season core features. See the [NBA's new-stat overview](https://www.nba.com/news/the-athletic-nba-amazon-partner-to-offer-4-new-stats-for-fans-and-broadcasters).
- Build the temporal roster universe from per-game rosters plus official roster snapshots.
- Keep regular season and playoffs separate.

If a field is unavailable or changes definition in any of the five seasons, use either:

1. A common-core feature available in all seasons; or
2. A versioned enhanced feature trained only on its valid window.

Do not backfill later tracking statistics into earlier seasons.

## NHL: 2021–22 through 2025–26

- A detailed NHL workflow was also prepared and is retained as a future reference in the companion [NHL puck-winning and defensive-disruption archetype plan](nhl-possession-archetype-plan.md). The NFL plan is the active first-sport implementation.
- This window begins exactly when the NHL says EDGE puck/player tracking became fully operational across all arenas. See the [NHL EDGE launch description](https://www.nhl.com/news/nhl-edge-advanced-stats-section-brings-fans-closer-to-game).
- Collect official roster/bio, realtime, faceoff, penalty, on-ice, play-by-play, and shift records by season.
- Collect EDGE speed/distance/burst fields by player-season.
- Collect MoneyPuck player/game/shot files by season with definition and situation flags.
- Treat annual scouting-combine results as sparse dated measurements.
- The public NHL API changed transport/schema around 2023–24. Normalize old and new source shapes into a versioned canonical event schema and retain the raw API schema version.

Retain rink/scorer and team-season controls for takeaways, giveaways, and hits.

## Premier League: 2021–22 through 2025–26

This is the data-rights and definition bottleneck.

- A paid API-Football or rights-cleared provider can supply a five-season player/game panel, subject to explicit coverage audits.
- API-Football lacks recoveries, pressure events, top speed, and distance, so it produces a smaller common-core feature set.
- Official Premier League/Opta pages are useful for manual validation but should not be scraped into a training database without permission.
- FPL community archives help with identities, rosters, minutes, and some performance fields, but detailed defensive-field provenance and licensing vary by season.
- The frozen 2025–26 FPL-Core archive is stronger than its prior seasons and therefore cannot be assumed definition-equivalent across the whole window.
- Fantasy Premier League introduced [defensive-contribution scoring](https://www.premierleague.com/en/news/4373187) and changed tackle/BPS treatment in 2025–26. Do not use defensive-contribution points or BPS as a five-season outcome.
- The Champions League changed from the 32-team group format to a [36-team league phase in 2024–25](https://www.uefa.com/uefachampionsleague/news/0290-1bae124dbd1a-4a9fc08cd25c-1000--2024-25-champions-league-teams-format-dates-draws-final/), reinforcing the Premier League as the cleaner longitudinal soccer cohort.

Use two soccer layers:

1. **Five-season common core:** roster/identity, position, minutes, tackles, interceptions, blocks, duels, fouls, height, and weight where the chosen provider confirms coverage.
2. **Enhanced recent-season layer:** recoveries, richer duels, physical movement, or defensive-contribution fields only for seasons where definitions and rights are consistent.

If a rights-cleared five-season performance feed cannot be obtained, keep the five-season roster/physical panel but shorten the soccer performance model. Do not fabricate a consistent history by joining incompatible providers.

---

# 7. Build the targets in three components

A single rate can make low-minute players look artificially exceptional. Model:

## 1. Availability

- Probability of being rostered or appearing in the next season.

## 2. Opportunity

- Expected defensive snaps, minutes, possessions, shifts, TOI, targets, or role exposure conditional on appearing.

## 3. Effectiveness

- Role-adjusted possession-winning performance conditional on opportunity.

Then calculate expected contribution:

> Availability × expected opportunity × effectiveness

Use partial pooling or empirical-Bayes shrinkage so small samples move toward their sport-role-season average.

Keep possession performance multi-dimensional before making a composite:

- Pressure/disruption.
- Interception/anticipation.
- Recovery/loose-ball winning.
- Contest/reach.
- Duel or tackle execution.
- Decision cost and discipline.

Standardize within sport × season × role. Cross-sport models receive these standardized latent dimensions, not raw sacks, steals, takeaways, or tackles.

---

# 8. Leakage-safe feature construction

For a season t forecast, only use information available before season t opens.

Recommended features:

- Previous-season value.
- Two- and three-season exponentially weighted averages.
- Year-over-year trend or slope.
- Between-game consistency.
- Career-to-date opportunity.
- Prior role shares.
- Age at season start, modeled nonlinearly within sport and role.
- Measurement age and staleness.
- Team-independent/opponent-adjusted rates.
- Transfer/team-change indicator known by the prediction cutoff.

Do not use:

- Target-season minutes or performance.
- Target-season observed role when predicting role.
- Injuries or roster outcomes learned after the cutoff.
- Weight or profile values published after the anchor.
- Team aggregates containing target-period information.
- Player IDs as ordinary model predictors.

Scaling, imputation, feature selection, dimensionality reduction, and index weights must all be fitted within the training fold.

---

# 9. Validation design

## Main temporal split

| Use | Target season |
|---|---|
| Training | 2021–22 through 2023–24 |
| Validation/model selection | 2024–25 |
| Final untouched test | 2025–26 |

NFL uses the corresponding calendar seasons 2021–2025.

Inside the pre-test period, add rolling-origin checks:

- Train through 2022–23 and predict 2023–24.
- Train through 2023–24 and predict 2024–25.
- Lock definitions, transformations, and hyperparameters.
- Train through 2024–25 and evaluate once on 2025–26.

After reporting the final result, retrain through 2025–26 for a future 2026–27 forecast.

## Known-player test

The same athlete may appear in earlier training seasons and the later test season because that matches the returning-player use case. Account for repeated observations:

- Never use a random player-season row split.
- Use player-clustered bootstrap confidence intervals.
- Consider hierarchical/player random effects.
- Include team-season context.
- Run a sensitivity analysis weighting each training row by the inverse of that player's number of training seasons.

## Cold-start test

- Hold out entire entry cohorts or athletes.
- Every row belonging to a held-out athlete stays outside training.
- Use only pre-entry physical/testing and optional source-sport features.
- Evaluate genuine rookies/entrants with no prior target-league season.

## Reported metrics

- Rank correlation.
- MAE/RMSE or appropriate count-model deviance.
- Top-decile precision and recall.
- Calibration.
- Uncertainty-interval coverage.
- Stability across seasons.
- Results by role, age, opportunity, transfer status, and measurement-coverage tier.

Always compare with simple baselines:

- Role-season mean.
- Prior-season rate.
- Three-season weighted average.
- Age-and-role-only model.

---

# 10. Modeling architecture

## Stage 1: descriptive and shrinkage layer

- Produce transparent raw and opportunity-normalized player-season statistics.
- Estimate stabilized sport-role-season percentiles.
- Build archetype clusters from completed seasons.

## Stage 2: sport-specific predictive models

Each sport predicts the common dimensions and their uncertainty using sport-appropriate opportunities and context.

Start with interpretable baselines:

- Hierarchical count/rate models with exposure offsets.
- Regularized generalized linear models.
- Mixed-effects or partial-pooling models.

Add tree/boosting models only after temporal baselines are established.

## Stage 3: shared physical model

Use a shared physical representation with sport-role-specific prediction heads rather than one universal regression. Inputs are physical/testing fields available across sports; outputs are projected within-role percentiles.

## Stage 4: enriched cross-sport model

Add source-sport standardized behavioral dimensions. Return:

- Projected percentile for each target role.
- Nearest physical and behavioral archetypes.
- Feature contribution/explanation.
- Uncertainty.
- Measurement coverage.
- Out-of-distribution warning.

Without observed cross-sport transition outcomes, report similarity and compatibility—not a calibrated probability of succeeding in another sport.

---

# 11. Data-processing layers

1. **Landing:** untouched downloads and responses.
2. **Bronze:** immutable source-shaped tables, manifests, and hashes.
3. **Silver:** resolved identities, standardized units/dates, roster spells, games, metric observations, and measurement events.
4. **Gold:** player-season aggregates, as-of measurements, role shares, and leakage-safe feature tables.
5. **Model:** frozen wide matrices, targets, split manifests, imputers, and normalization parameters.
6. **Quarantine:** ambiguous identities, impossible values, definition conflicts, and unreconciled rows.

Suggested deliverables:

- player master.
- source identity crosswalk.
- roster spells.
- measurement events.
- player games and opportunities.
- player-game metrics.
- player-team-seasons.
- player-seasons.
- selected season measurements.
- long feature store.
- versioned train/validation/test matrices.

---

# 12. Quality controls

- Verify unique keys and referential integrity.
- Reconcile game and season totals against a designated authoritative source.
- Compare roster counts, appearance counts, and zero-appearance athletes.
- Track missingness by sport, season, role, team, source, and measurement type.
- Flag impossible values without deleting the raw observation.
- Detect height/weight conflicts, ID collisions, and birth-date mismatches.
- Version metric definitions and provider changes.
- Distinguish zero, no opportunity, not applicable, and missing.
- Verify that every feature input was available before its anchor date.
- Recompute a sample of aggregates directly from player-game data.
- Fit normalization parameters on training seasons only.

---

# 13. Revised implementation order

## Milestone 1 — shared foundation

- Freeze the five-season scope and season-opening anchor dates.
- Create source, identity, season, team, roster, and measurement schemas.
- Define the role ontology and common possession-winning dimensions.

## Milestone 2 — NFL reference panel

- Collect 2021–2025 weekly rosters, player stats, snap counts, advanced defense, play-by-play, participation, and combine testing.
- Build and validate the complete bronze-to-gold pipeline.
- Produce descriptive, known-player, and cold-start baseline models.

## Milestone 3 — NBA panel

- Mirror the schema for 2021–22 through 2025–26.
- Add Hustle, tracking/matchup, combine, and temporal roster data.

## Milestone 4 — NHL panel

- Add official events, MoneyPuck, EDGE, and sparse combine testing.
- Model rink/scorer and line/team context.

## Milestone 5 — Premier League panel

- Resolve the rights-cleared source and audit each season's field coverage.
- Build the five-season common core.
- Add enhanced recent-season fields separately.

## Milestone 6 — cross-sport layer

- Freeze sport-specific percentiles and latent dimensions.
- Train the physical-only shared model.
- Train and separately evaluate the enriched behavioral model.
- Add explanations, uncertainty, and extrapolation warnings.

## Immediate next deliverable

Build the source registry, canonical schema, and 2021–2025 NFL collection manifest. The NFL panel should be the reference implementation used to test all point-in-time joins, measurement-selection rules, and temporal split logic before duplicating the pipeline in the other sports.
