# Possession Lab project guide and review

Prepared for the project owner on 21 October 2026

Repository reviewed: Shaun7036/possession-lab at commit ea25d12. Data and model snapshots were created on 17 October 2026. This guide describes that saved implementation and its results; it does not represent a new data collection or retraining run.

The code is operational, but reliable cross-sport efficacy is not established. The main correction requiring action is incomplete EPL block coverage reaching season-level model labels. The guide explains the implementation in plain language and identifies the assumptions and results that need your review.

## 1 Where the project stands

The repository now contains working collection, cleaning, exploratory analysis, baseline modeling and scoring pipelines for the NFL, NBA, NHL and Premier League. It also contains a trained unified physical-profile efficacy prototype. It does not yet contain a validated model of whether an arbitrary athlete could switch sports successfully.

The strongest current result is that body dimensions help distinguish some broad playing roles among athletes who already reached elite leagues. Predicting an individual's possession-winning effectiveness from those dimensions is much less successful. The unified model learns from height and weight only. Five of its fourteen fitted role models pass exploratory point checks, but none has a 95 percent bootstrap improvement interval entirely above zero. Most individual prediction intervals are very wide.

There is also an actual data correction needed before trusting the EPL block-related findings. Some 2025–26 season block totals are sums over incomplete match coverage, without a partial-coverage flag reaching the models. The audit found eight affected defenders in the unified model's eligible cohort. The existing saved results are reported below as results of the current implementation, not as corrected estimates.

### What is completed

- A reproducible Python repository and command-line interface, with source manifests, data checks, reports, model files and automated tests.
- Five-season canonical player panels for all four leagues, with sport-specific identities, roles, opportunities and event definitions.
- Archived NFL combine and additional testing measurements, stored separately from the default modeling features.
- Descriptive body and play-style clusters, returning-player forecasts, body-to-role classifiers and physical event-rate association models.
- A separate 2025–26 Premier League association study using detailed defensive events.
- A unified scorer with role-specific composites, local and shared experts, athlete-disjoint evaluation, provisional intervals, physical-domain checks and abstention.

### What remains incomplete

- Genuine annual height and weight measurements for every sport. Multiple seasons of statistics do not establish multiple dated physical tests.
- Consistent speed, wingspan, arm length, leg length and agility measurements across the four leagues.
- Validated reaction-time, spatial-awareness, anticipation or decision-quality features.
- A coach-approved definition of possession-winning success that is comparable across sports.
- Independent evidence of an optimal body archetype, a validated hidden-value ranking, or real sport-switching outcomes.
- A deployed application, web dashboard or public prediction API. The working user interface is the command line and JSON output.

The right description today is a research platform with an operational prototype, several informative baseline results and important unresolved data and measurement questions.

### The saved data at a glance

| League | Season convention | Player seasons | Distinct athletes | Main opportunity |
|---|---|---:|---:|---|
| NFL | 2021 through 2025 NFL seasons | 7,279 defenders | 2,754 | Observed defensive scrimmage player-plays |
| NBA | 2021–22 through 2025–26 | 2,932 | 1,057 | Minutes |
| NHL | 2021–22 through 2025–26 | 4,738 skaters | 1,480 | Ice-time minutes |
| Premier League | 2021–22 through 2025–26 | 4,025 | 1,797 | Minutes |

The NFL also retains 15,518 all-position roster player-seasons before selecting defenders. NHL coverage is appearing skaters, not every contracted or zero-game roster player. EPL possession events exist only in the 2025–26 layer, despite the five-season roster/minutes panel.

There are 219 cached source files totaling 300.5 MiB and 38 processed Parquet tables. In this documentation audit, all 219 cached files matched their recorded hashes, and all 47 artifacts listed in the four shared model registries plus the unified registry matched their recorded hashes. Four additional recent EPL model files exist outside those shared registries. The local test suite passed 87 tests and the lint check passed on 21 October 2026. These checks establish integrity and software behavior, not scientific validity or complete source coverage.

Evidence: [R1], [R2], [R3], [R8], [R9], [R12].

## 2 How the implementation relates to your original idea

Your proposed workflow was to identify successful possession-winning builds within each sport, find athletes whose characteristics suggest hidden value, and eventually compare an athlete across sports using physical and engineered awareness features. The repository implements the infrastructure for investigating that idea, but several scientific steps are still assumptions rather than established results.

First, the data describe people who have already been selected into elite leagues. A relationship within that group does not tell us the probability that a non-elite or outside-sport athlete could enter the league. Technical skill, training, development, opportunity and selection have already shaped who appears in the data.

Second, the current archetype methods do not first identify independently successful athletes and then discover a uniquely successful build. Body clusters partition the observed physiques. Style clusters partition event-rate profiles. The unified archetype expert attaches average activity outcomes to body clusters. These are useful descriptions, but they are not proof of an ideal or causal build.

Third, possession-winning events are not interchangeable. A defensive rebound often terminates an opponent's possession; a block, hit or QB hit may disrupt play without changing possession. Faceoff wins measured per ice time include assignment and usage. The code therefore calls the unified target a possession/disruption activity composite rather than pretending it measures a universal quantity of possession value.

Finally, synchronization across sports currently means applying a common percentile-building procedure to different sport-role outcomes. A score of 70 is an estimated 70th-percentile activity target within that particular elite role. It is not a 70 percent success probability, equal sporting value in every sport, or evidence that one athlete will adapt better to one sport than another.

### Five questions the code keeps separate

| Question | Implemented analysis | What the output means |
|---|---|---|
| Which roles have similar builds | Physical role classifier | Broad role-label probability among observed elite athletes |
| What kinds of players exist | Body and play-style clustering | Descriptive groups of bodies or event profiles |
| What might a returning player do next season | Returning-player models | Availability, opportunity, event rates and count forecasts from prior history |
| How do body measurements relate to an event rate | Physical association models | Estimated sport-specific rate conditional on broad role and other included inputs |
| How does a profile map to standardized role activity | Unified efficacy ensemble | Provisional role-relative activity percentile plus uncertainty and evidence checks |

These analyses have different targets, features, splits and units. They must not be interpreted as different displays of the same validated ability score.

Evidence: [R4], [R5], [R6], [R8], [R10].

## 3 How the repository is organized

The data flow is source download, immutable local snapshot, sport-specific normalization, canonical player tables, analysis and fitted artifacts, then scoring. The sport adapters handle source differences; shared modules handle comparable software operations without forcing identical event meanings.

| Location | Purpose |
|---|---|
| `src/possession_lab/sports/nfl.py` | NFL acquisition, identity, participation, event credits and physical/testing tables |
| `src/possession_lab/sports/nba.py` | NBA source joins, standings-game filtering and player aggregation |
| `src/possession_lab/sports/nhl.py` | NHL skater summaries, games, situations and physical enrichment |
| `src/possession_lab/sports/epl.py` | FPL core, recent defensive events, profile matching and separate recent study |
| `src/possession_lab/io.py` | Cached downloads, provenance, hashes and table IO |
| `src/possession_lab/analysis.py` | Shared EDA, forecasts, role models, physical associations and clustering |
| `src/possession_lab/predict.py` | Original physical compatibility and rate-association scorer |
| `src/possession_lab/ensemble*.py` | Unified targets, experts, evaluation, training and scoring |
| `src/possession_lab/cli.py` | The user-facing commands |
| `src/possession_lab/catalog.py` | Inventory and schema metadata generation |

Raw files and their `.source.json` sidecars are under `data/raw/`. Canonical and audit tables are under `data/processed/`. Fitted binary models are under `models/`. Those directories are deliberately ignored by Git. The repository versions code, aggregate reports, source hashes and schemas, but a fresh clone does not include the local datasets or model binaries.

`reports/<sport>/` contains EDA, QA, splits, metrics, archetype summaries and model registries. `reports/ensemble/` contains the newer unified evaluation and example. `metadata/` records file provenance and table schemas. `docs/` contains implementation notes. `outputs/` contains the original research plans and source audit; those plans are intentions, not proof that every proposed feature was implemented.

The two implementation commits are fa4c6cc, which built the four-sport pipelines and baseline models, and ea25d12, which added the unified efficacy ensemble. Both are dated 17 October 2026. No model or source-data correction is applied by this guide.

Evidence: [R1], [R2], [R4], [R7], [R11].

## 4 Data conventions that matter throughout the project

### Seasons and sample sizes

For the NBA, NHL and EPL, a stored season of 2025 means the season beginning in 2025 and ending in 2026. The NBA adapter converts that start year to the source's ending-year convention. NFL uses the NFL season year. The working panels cover regular seasons, not a common calendar-year window or postseason competition.

A player-season is one athlete's record in one season. Repeated seasons are correlated observations, not independent people. The canonical key is player ID plus season. Game tables use player ID plus game and season as appropriate. All four current season panels have unique player-season keys.

### Identity and joins

The NFL uses GSIS IDs, with PFR and SMART IDs for conditional enrichments. NBA uses its ESPN-based source player identity, retaining an incomplete NBA-ID crosswalk rather than requiring it. NHL uses the NHL player ID. EPL uses the stable FPL player code prefixed with `fpl:`; a season-local FPL element ID is only a join key within that season.

The unified model prefixes the canonical player ID with the sport. There is no verified cross-sport person crosswalk or dataset of actual athletes who changed sports. The common identity prefix keeps unrelated provider IDs from colliding; it does not identify the same human across different leagues.

### Missing values are not zero performance

A recorded zero can mean a player had opportunities but no event, or was rostered but did not play. A missing value can mean the provider did not collect the metric, the identity could not be resolved, or event/opportunity coverage is incomplete. Those meanings require different treatment.

For example, historical EPL interceptions are missing, not zero. A returning player who has no row in the next season has zero next-season opportunity for the forecast question. A present player with a missing target is not automatically assigned zero. The newly identified EPL partial-block issue shows why checking only whether a season total is numeric is insufficient.

### Units and denominators

Height is normalized to centimeters, weight to kilograms and birth dates to season-appropriate age where available. NFL core event rates use observed valid scrimmage participation. The other leagues use minutes. Shared baseline event-rate reports use events per 100 opportunity units. The separate recent EPL association uses events per 90 minutes. The unified model instead predicts a 0–100 percentile target.

Consequently, an NFL MAE of 0.3 events per 100 player-plays cannot be compared numerically with an NBA MAE of 1 event per 100 minutes or a percentile MAE of 25. An error metric needs its target, unit, cohort and baseline attached.

### Measurement timing

The multi-season design preserves physical-source timing where it can, but most leagues do not supply verified annual tests. NBA and NHL dimensions are complete in the current panels, yet no multi-season athlete has varying listed height or weight in those pulls. EPL current profile matches are repeated back to historical stable identities. NFL has archived roster listings, but only three multi-season athletes show a listed weight change; that is not a validated annual weighing program.

This means the repository cannot yet answer your proposed question about the relationship between genuine annual weight changes and performance across all four sports. It can model repeated performance seasons and descriptive body associations, while disclosing the different measurement timing.

Evidence: [R2], [R3], [R4], [R7], [R8].

## 5 What was done for the NFL

### Sources and retained universe

The adapter downloads nflverse weekly rosters, player identities, schedules, weekly player statistics, play-by-play and play participation. It also acquires snap counts, advanced defense, combine and community anthropometric/testing enrichments, but keeps the conditional-source layers separate from the default model inputs and targets.

It preserves 221,234 weekly roster records and 15,518 resolved all-position roster player-seasons. The defensive modeling panel contains 7,279 player-seasons and 2,754 distinct athletes. Missing-GSIS roster records are quarantined rather than joined by an assumed identity. The five unresolved roster tables contain 23, 26, 5, 7 and 18 records respectively; these are source rows, not necessarily distinct people.

The role system is EDGE, interior defensive line or IDL, linebacker or LB, ambiguous outside-linebacker hybrid, cornerback or CB, safety or S, and explicitly unknown categories where source position detail is inadequate. An OLB listing is not treated as proof of a pure edge-rush assignment. Slot/outside corner or box/deep safety alignments are not reconstructed.

### Matching event counts to opportunity

The primary denominator is participation on a valid regular-season pass/run scrimmage play. Event numerators are reconstructed from play-by-play on the same scope. This avoids dividing all-situations weekly tackles or forced fumbles, which may include special teams, by a defense-only denominator.

The code handles half-sacks, defensive forcing/recovery attribution, the order of multiple fumbles, credited safeties and overlapping sack/QB-hit events. A sack and QB hit can refer to the same play; they are not blindly summed into a count of distinct disrupted plays.

The core modeled event columns are sacks, QB hits, interceptions, forced fumbles, passes defended and `negative_play_tackle_credits`. The last is a consistently reconstructed PBP measure, not a renamed official TFL series. Official weekly tackles for loss are kept separately because historical credit conventions differ, particularly before 2024.

Participation changes provider from NGS through 2022 to FTN from 2023. Participation tells us a defender was on the play; it does not tell us that defender's exact pass-rush, coverage or pressure opportunity. Whole-play pressure exposure must not be interpreted as individual pressures generated.

The QA reconciles completed regular games: 272 in each selected season except 2022, which has 271 after the cancelled Buffalo–Cincinnati game. Raw postseason rows are excluded from the modeling scope.

### Coverage corrections already implemented

An event-credit/participation check found three 2025 player-seasons with credited events lacking matching participation: 29 credited metric rows across three player-games. Those records keep observed partial exposure for inspection, set the modeling opportunity to missing, and are excluded from rate fitting. This prevents artificially inflated rates from a partial denominator.

This is different from the unresolved EPL issue. The NFL already propagates the incomplete-exposure condition to eligibility; EPL partial event coverage currently does not receive the corresponding treatment.

### Physical and optional testing measurements

The 2025 defender panel has height and weight together for 1,405 of 1,484 players, or 94.7 percent. Listed weight exists for all 1,484; height is missing for 79. The broader optional roster inventory has arm/hand data for 1,991 players, wingspan for 293, 40-yard times for 1,611 and 10-yard splits for 1,199. Those optional counts refer to the broader roster measurement inventory, not necessarily eligible defenders or model training rows.

Testing events preserve test year and protocol, and the player-season measurement selection uses a measurement no later than that season with years-since-measurement metadata. The 2021 pro-day format is a protocol caveat. Arm length and leg length are distinct; no general leg-length dataset has been populated.

PFR advanced statistics and community testing enrichments are excluded from the default learned models pending source-use review. In particular, the core efficacy model has not learned from the richer limb/sprint inventory just because those tables were collected.

### Important NFL outputs

The owner-facing entry point is `player_seasons.parquet`. The supporting tables preserve weekly rosters, all rostered player-seasons, reported weekly totals, player-game scrimmage totals, individual event credits, missing-participation gaps, identity, measurement events and conditional advanced/testing/snap layers. The inventory has all table names and schemas. Keeping these layers separate makes it possible to review a suspicious season rate back to its player-play evidence.

Evidence: [R2], [R3], [R4], [R7].

## 6 What was done for the NBA

The NBA pipeline uses SportsDataverse's ESPN-derived player box scores, game rosters and player core tables for the five seasons. It retains the NBA player-ID crosswalk when present but does not require it to form the canonical ESPN-based player identity.

The season panel is built from roster and profile coverage, not only from positive-minute box-score rows. It therefore retains explicitly recorded nonappearances and some profile-only players. This is broader than a minutes leaderboard, but it is not an independently reconstructed transaction-by-transaction universe of every NBA contract.

The adapter removes All-Star/exhibition records and the NBA Cup championship game where it appears among source `season_type=2` rows. The cleaned schedule reconciles to 1,230 standings games, 30 teams and 82 games per team in every season. This matters because a source's regular-season flag alone is not enough to guarantee the intended denominator.

It joins game rosters to box scores, distinguishes reported DNP from ambiguous missing/zero-minute cases, combines team stints into one player-season, and retains a separate player-team-season table for traded athletes. Unresolved identity rows and excluded non-standings rows stay in audit tables instead of silently entering the panel.

The final data contain 160,121 player-game rows, 3,385 player-team-season rows and 2,932 player-seasons across 1,057 athletes. Core possession/disruption outcomes are steals, blocks and defensive rebounds. Turnovers and other box-score context may be retained, but the unified target does not turn those into a cross-sport net-value metric.

Height, weight and age are complete in this snapshot. Completeness does not solve timing: the dimensions behave as regenerated current profiles, not verified annual measurements. No learned cross-sport wingspan, speed, limb-length or cognitive feature has been supplied by this adapter.

Broad roles are guard, forward and center. Point/shooting guards map to guard; small/power forwards map to forward; centers remain centers. A good broad-position classifier should not be read as proof that the same dimensions explain differences in steals or defensive skill within a role.

Evidence: [R2], [R3], [R4], [R5].

## 7 What was done for the NHL

The NHL pipeline uses MoneyPuck's designated regular-season skater summary files and player-game ZIP downloads, plus its player lookup. Season-filtered NHL Stats bio reports enrich the athlete universe and listed dimensions. The adapter does not scrape a complete NHL EDGE tracking dataset.

The panel contains skaters with statistical appearances. Goalies and zero-game roster/contract players are outside its universe. It has 236,069 player-game rows, 4,738 player-seasons and 1,480 distinct skaters.

The core event mappings are MoneyPuck takeaways, shots blocked by the player, hits, giveaways and faceoff wins. Opportunity is source ice time converted from seconds to minutes. The unified targets use selected subsets; giveaways are not included in the unified possession/disruption composite.

MoneyPuck's all-situations totals already include five-on-five activity. The adapter keeps the all-situations fields and separate `_5v5` columns; it never sums those overlapping views. Explicit total rows are preferred over summing total and team-stint rows together. Regular-game filtering and player-game uniqueness prevent other duplication.

All 4,738 player-season records reconcile to player-game ice time and selected event counts, within floating-point tolerance for minutes. Dimensions and age are complete, but the bios are current/undated values for season-filtered players. All repeated height/weight values are constant for multi-season athletes in this pull. They cannot establish annual body changes.

The broad roles are defense, center and wing. Faceoff wins per ice time partly measure who is assigned to take draws. Hits and blocks reflect disruption and context, not necessarily recovered possession. The source shows a marked shift in takeaway-rate distributions beginning in 2024. The audit establishes distribution drift, not its cause or a confirmed formal scoring-definition change.

The unified model uses season-specific role reference distributions to reduce this scale problem. That does not remove arena scorer, team, assignment or other biases, and the older temporal takeaway forecast still has poor test explained variance.

MoneyPuck's recorded source-use notes call for attribution and noncommercial use restrictions. The source terms need review before commercial distribution or product use; the code's ability to download a file is not permission to relicense it.

Evidence: [R2], [R3], [R4], [R7], [R8].

## 8 What was done for the Premier League

### The five-season common core

Vaastav's Fantasy Premier League archive supplies roster identity, broad role, appearances and minutes for 2021–22 through 2025–26. Stable FPL codes connect seasons. Season-local element IDs only join files within a season.

The common panel contains 4,025 player-seasons and 1,797 distinct athletes. Its historical files do not provide a consistent five-season tackle/interception/recovery/block series. Those detailed event fields remain missing for 2021–24. Fantasy scores or the newer defensive-contribution rule are not substituted as equivalent historical possession measures.

### The enhanced recent-season layer

FPL-Core-Insights supplies 2025–26 player-match detail for all 38 gameweeks and 380 league matches. The enhanced appearance layer has 11,492 rows covering 537 appearing players. Recorded totals include 12,604 tackles, 6,267 interceptions, 35,556 recoveries and 2,709 recorded blocks. The last total is an observed partial total where coverage is missing, not an independently verified complete league total.

The five-season combined game table has 56,272 rows. Its 2025 common-core appearance count is 11,498, while the enhanced detail layer has 11,492; these are different source representations and should not be described as identical row sets. The adapter uses explicit joins and coverage metadata rather than treating the two feeds as interchangeable.

The enhanced appearances replace the common-core 2025 appearance layer in the final game table; they are not appended as a second set of the same matches. The QA keeps both source-layer counts for comparison.

Tackles and tackles won are distinct fields. The unified target uses tackles won, not raw tackles plus tackles won, which would double-count related activity. `defensive_contributions_raw` is a recent FPL scoring-rule field, not a harmonized historical defensive statistic.

### Physical enrichment and selection

ESPN team roster profiles are matched by normalized name within team. The saved enrichment includes 499 matched profiles: 464 exact normalized-name matches and 35 team-constrained fuzzy matches. It preserves ESPN ID, match method, match score and retrieval date so ambiguous matches can be audited.

In 2025, height exists for 473 of 841 rostered players, weight for 441, and both measurements for 441, or 52.4 percent. Age exists for 822. Physical coverage is therefore substantially more selective than in the NBA/NHL panels. Current ESPN profiles repeated onto historical rows do not supply historical measurements. Fuzzy matches deserve manual review, even though a potential matching error is not the same as a demonstrated error.

### The block-coverage correction needed

There are 293 missing block values among the 11,492 enhanced player-match rows. Fifty-one players have some matches with blocks observed and others missing; 22 players have all observed appearance block values missing.

The current season aggregation uses a sum with `min_count=1`. That keeps an all-missing season missing, but produces a numeric season total when even one match is observed. The denominator still includes the full season's minutes. Consequently, a partially observed block numerator can be treated as a complete rate label.

Of the unified EPL defender model's 117 eligible athletes, eight have such partial block totals. They represent 14 missing player-match block rows and are distributed across five training athletes, one calibration athlete and two test athletes. This can affect the EPL DEF composite and the separate recent-season blocks association. The unified MID and FWD targets do not use blocks, so this specific defect does not directly alter those targets.

The needed correction is to retain metric-specific observed/missing match counts and exposure coverage, then either exclude incomplete season labels, define a consistently observed-window rate, or explicitly model missingness under a defensible assumption. Missing blocks must not simply become zeros. After choosing the policy, rebuild the EPL panel and rerun the affected models, target transforms, calibration and reports. The issue is not proven to be the cause of the defender model's 52.4 percent interval coverage.

### Source rights

The saved source audit did not establish an explicit redistribution license for the enhanced community dataset. Keep it as a research/prototyping dependency until rights are reviewed. Source accessibility and attribution do not by themselves establish suitability for a public or commercial application.

Evidence: [R2], [R3], [R4], [R7], [R8], [R9].

## 9 What the exploratory analysis and archetypes do

The shared EDA produces seasonal row/player coverage, missingness, physical and opportunity distributions, within-role body/rate relationships, role event-rate comparisons and QA summaries. It is intended to expose coverage and definitions before interpreting a model fit. A large raw correlation across roles can be driven by positions rather than individual efficacy.

### Body archetypes

Within a broad role, the original descriptive body clustering uses unique athletes and sufficiently measured development observations through 2023. When at least 40 measured development athletes are available, it standardizes body dimensions and fits exactly three KMeans clusters. Three is an imposed descriptive choice, not a discovered number of natural biological types.

Those clusters summarize sizes within roles. They do not independently identify winning builds. The NFL body-cluster output can include an unknown defensive-back category even though that category is excluded from the supervised role classifier. EPL physical clusters are fitted for DEF and MID where supported.

### Play-style archetypes

The original style analysis requires at least 100 opportunity units. It shrinks event rates using a prior exposure equal to one quarter of the development median opportunity, standardizes them relative to role, and compares KMeans solutions with two through five clusters. It selects the highest development silhouette score, a measure of cluster separation.

All four saved style analyses selected two clusters. Their silhouette and mean bootstrap adjusted Rand index are NFL 0.331 and 0.964, NBA 0.312 and 0.893, NHL 0.260 and 0.960, and EPL 0.270 and 0.868. The adjusted Rand index assesses assignment stability under five resamples. These style resamples are player-season rows, not an independent-athlete inferential bootstrap. EPL uses its single recent event cohort and is explicitly descriptive-only.

Because the clusters use the activity metrics themselves, showing that a cluster has high values of those same metrics is not independent evidence that its members are successful. Independent outcomes, context adjustment and an external evaluation would be needed for a hidden-value or optimal-build claim.

The unified model's soft-archetype expert is a separate estimator described in Section 12; it is not simply the old cluster labels reused as a universal success scale.

Evidence: [R5], [R8], [R10].

## 10 How the original prediction models work

### Returning-player forecasts

The forecast cohort starts with a player's previous-season record and left-joins the following season. A nonreturner stays in the evaluation with zero future opportunity/counts. This avoids evaluating only surviving players. A present player whose metric is genuinely unobserved remains missing for that target.

Features include previous log opportunity, exponentially weighted opportunity, prior age, prior event rates, exponentially weighted event rates and broad role. The exponential smoother has span three and is recursive; it is not a strict last-three-season cutoff. Current height/weight, IDs and same-season target statistics do not enter these regressors.

Development targets are 2022 and 2023. Candidate selection uses 2024. The selected methods are refitted through 2024 and evaluated on 2025. Numeric imputation/scaling and role encoding are learned from training data. Because the source snapshots are final corrected records and profile publication timing is not fully audited, this is retrospective temporal evaluation, not a proven point-in-time deployment simulation.

Availability predicts any positive future opportunity using logistic regression, with C chosen from 0.1, 1 and 10 by validation Brier error. It beats the training-prevalence baseline in validation for all four sports. In the NFL, this is future defensive scrimmage participation, not merely remaining under contract.

Opportunity uses Ridge on log-transformed positive opportunity, with alpha chosen from 1, 10 and 100. The hurdle prediction multiplies positive-opportunity output by availability once. It is compared with previous-season opportunity persistence. Persistence wins 2024 selection for NFL, NBA and NHL; the hurdle model wins for EPL.

Event-rate prediction uses Ridge on log-transformed per-100 rates, weighted by the square root of exposure capped at the training 95th percentile. It is compared with role means and previous-season rate persistence. Validation MAE selects the method. The selected rate is multiplied by the selected unconditional opportunity and divided by 100 to form a count estimate. A hurdle component does not receive an extra, duplicate availability multiplier.

Inverse-transforming a log regression is not automatically an unbiased conditional mean. The count product is also an approximation rather than a complete joint model of rate and playing time. These are useful baseline assumptions to review before stronger contribution claims.

### Broad physical role classification

The role classifier uses height and weight only, one first sufficiently measured record per athlete, and excludes unspecified role labels. The saved models train on athletes first observed through 2023, select using those first observed in 2024, and test on first-observed 2025 athletes. First observed with measurements does not mean rookie or true professional entry year.

| League | Classes | Test athletes | Accuracy | Majority baseline | Balanced accuracy |
|---|---:|---:|---:|---:|---:|
| NFL | 6 | 244 | 69.7% | 19.7% | 61.4% |
| NBA | 3 | 106 | 80.2% | 55.7% | 79.1% |
| NHL | 3 | 116 | 40.5% | 37.1% | 39.3% |
| EPL | 4 | 104 | 50.0% | 41.3% | 37.4% |

Balanced accuracy averages recall across classes, reducing the dominance of a common role. The four accuracies cannot rank sports by transferability because the class definitions and cohorts differ. These are role-label classifications among elite players.

### Physical event-rate associations

These are separate from both forecasts and role classification. They use height, weight, age where available and broad role to estimate a sport-specific event rate. They require at least 100 opportunity units and measured height/weight, with entire identities isolated in deterministic training/validation/test buckets. Training uses seasons through 2023, validation uses different athletes in 2024 and test uses different athletes in 2025.

Ridge alpha is selected on validation MAE. A role-mean baseline is reported, but improvement is not required for the original model to be fitted or exposed by its scorer. Examples illustrate mixed value: NFL sack MAE is 0.2831 versus 0.2826 for role means; NBA steals 1.019 versus 0.985 is worse; NBA blocks 0.851 versus 0.935 and defensive rebounds 2.895 versus 3.150 are better. All are per 100 sport-specific opportunity units.

### The separate recent EPL study

This study uses 2025–26 only, at least 450 minutes and a reproducible whole-player 75/25 split: 300 training athletes and 100 test athletes from 400 eligible players. Inputs are role, height, weight and age, with training-only median imputation and indicators. Height/weight coverage is 77.75 percent in this more active cohort, and age is complete.

It fits RidgeCV event rates per 90 minutes. Tackles have model MAE 0.569 versus role mean 0.563; interceptions 0.287 versus 0.291; recoveries 0.772 versus 0.768; blocks 0.154 versus 0.171. The blocks fit actually uses 299 observed training and 97 observed test labels, and the newly found partial-coverage problem also needs correction. The current block result must not be presented as clean evidence until that correction is evaluated.

Evidence: [R5], [R6], [R7], [R9].

## 11 What the original models actually achieved

The returning-player results below use the method selected on 2024, not whichever candidate later happened to have the lowest 2025 error. Rates are events per 100 observed scrimmage player-plays for NFL and per 100 minutes for NBA/NHL.

| Outcome | Selected method | Test rate MAE | Test R squared |
|---|---|---:|---:|
| NFL sacks | Ridge | 0.263 | 0.310 |
| NFL QB hits | Ridge | 0.511 | 0.357 |
| NFL interceptions | Ridge | 0.100 | 0.030 |
| NFL forced fumbles | Ridge | 0.126 | 0.013 |
| NFL passes defended | Ridge | 0.463 | 0.097 |
| NFL negative-play tackle credits | Ridge | 0.498 | 0.107 |
| NBA steals | Ridge | 1.046 | 0.188 |
| NBA blocks | Previous-season rate | 0.838 | 0.440 |
| NBA defensive rebounds | Ridge | 2.380 | 0.495 |
| NHL takeaways | Ridge | 0.648 | -0.106 |
| NHL blocks | Ridge | 1.357 | 0.440 |
| NHL hits | Previous-season rate | 2.687 | 0.703 |
| NHL faceoff wins | Previous-season rate | 2.793 | 0.854 |

MAE is average absolute error in the target's unit. R squared compares squared error with predicting the test-set mean; a negative value means that mean prediction would have lower squared error. A method can improve MAE over persistence while still having negative R squared. NFL interceptions and forced fumbles have little explained variance; the NHL takeaway result does not support confident individual rankings.

The selected opportunity MAEs are 126.93 player-plays for NFL, 488.16 minutes for NBA, 278.69 minutes for NHL and 576.25 minutes for EPL. The availability Brier errors for logistic versus prevalence are NFL 0.1335 versus 0.2477, NBA 0.1227 versus 0.1605, NHL 0.1036 versus 0.1218 and EPL 0.2207 versus 0.2488. Lower Brier error is better.

Selection discipline matters. NBA opportunity persistence remains selected even though the hurdle candidate has lower 2025 MAE. EPL's hurdle remains selected even though persistence has lower 2025 MAE. Changing those selections after observing the test would overstate the evidence. NHL takeaway total-count MAE is 6.647 versus 6.252 for the previous count, so that count forecast does not beat persistence.

The sensible finding is that prior performance helps some tasks, simple persistence remains competitive, and dimensions distinguish some broad roles better than they explain individual effectiveness. There is no universal model win across all sports and targets.

Evidence: [R5], [R9].

## 12 How the unified efficacy model is built

### Eligibility and learned features

The unified system specifies fifteen heads: six NFL roles, three NBA roles, three NHL roles and EPL DEF/MID/FWD. It fits a head only when at least fifty distinct measured training athletes are available. Fourteen heads are fitted. EPL FWD has nineteen training athletes and is skipped. Unknown roles and goalkeepers are outside the target definition.

This is not a blend of the original four role classifiers or returning-player forecasts. It refits new sport-role experts on the constructed percentile target, then combines those experts under one scoring contract. The older models remain separate studies with different outputs.

Training eligibility requires finite height, weight, positive opportunity and every required event component, with nonnegative event counts. Known under-18 ages are excluded; missing age is allowed because age is unused. The minimum season opportunity is 150 NFL player-plays, 300 NBA minutes, 300 NHL minutes and 450 EPL minutes. These are design choices, not learned thresholds. Broad data tables retain players who do not meet those modeling cutoffs.

Only height and weight are learned inputs. Age is accepted and checked when supplied but unused. BMI is derived and displayed but excluded to avoid duplicating the same two dimensions geometrically. The richer NFL testing inventory is not a back door into this common model.

### Constructing the target

The model predicts a constructed possession/disruption activity percentile, not a directly observed universal skill score. The complete target procedure is fitted separately within sport, role and season using the training athletes of the current fold.

For each component event, the reference rate is total training event count divided by total training opportunity, using the reference weights. The prior exposure is half the median training opportunity. Each player's raw event rate is shrunk toward that reference rate before ranking.

```
prior exposure = 0.5 times median reference opportunity
shrunk rate = (event count + reference rate times prior exposure)
              divided by (player opportunity + prior exposure)
```

For illustration, suppose the reference rate is 0.02, prior exposure is 200, and a player has eight events in 200 opportunities. The raw rate is 0.04. The shrunk rate is (8 + 0.02 times 200) divided by 400, or 0.03. A smaller sample is pulled toward the reference instead of being declared exceptional from a few events. This example explains the calculation; it is not a saved athlete rating.

Each shrunk component is mapped through a training-reference empirical cumulative distribution to a 0–100 mid-rank. Ties share their midpoint rank. Component ranks are averaged within domains, then domains are combined using fixed role weights. A final training-reference CDF converts the composite to the final percentile target. An empirical CDF is the reference distribution used to determine where a value stands among peers.

All priors and reference distributions are refitted inside every training fold. The seasonal separation prevents different seasonal scales, including the observed NHL takeaway shift, from becoming a spurious body association. It does not correct every scorer, team, pace or assignment effect. A missing season reference cannot silently borrow another year's distribution.

### Fixed definitions that you should review

NFL rush disruption averages sack and QB-hit percentiles equally. Ball disruption averages passes-defended and interception percentiles equally. Negative stops use negative-play tackle credits; fumble creation uses forced fumbles.

| NFL role | Rush | Negative stops | Ball disruption | Fumbles |
|---|---:|---:|---:|---:|
| EDGE | 55% | 25% | 0% | 20% |
| IDL | 55% | 35% | 0% | 10% |
| LB | 15% | 40% | 30% | 15% |
| OLB hybrid | 40% | 35% | 15% | 10% |
| CB | 0% | 10% | 75% | 15% |
| S | 5% | 25% | 55% | 15% |

| Other role | Event or domain weights |
|---|---|
| NBA guard | Steals 55%, blocks 15%, defensive rebounds 30% |
| NBA forward | Steals 40%, blocks 30%, defensive rebounds 30% |
| NBA center | Steals 15%, blocks 45%, defensive rebounds 40% |
| NHL defense | Takeaways 60%, blocks 30%, hits 10% |
| NHL center | Takeaways 45%, faceoff wins 45%, blocks 10% |
| NHL wing | Takeaways 65%, blocks 20%, hits 15% |
| EPL DEF | Recoveries 35%, tackles won 35%, interceptions 20%, blocks 10% |
| EPL MID | Recoveries 40%, tackles won 35%, interceptions 25% |
| EPL FWD | Recoveries 50%, tackles won 30%, interceptions 20% |

These weights are hand-set research assumptions. They have not been learned as an objective definition of sporting value or approved through a coach study. NHL center faceoff activity is wins per ice time, not faceoff win percentage. Negative possessions such as turnovers/giveaways are not part of a common net-value score.

The report compares this target with equal-domain/equal-component weights without retuning the model against test outcomes. Target sensitivity is material: mean absolute changes are about 17.1 percentile points for NHL defense, 16.7 for NHL wing and 15.0 for NFL CB. Your judgment about what counts as successful possession work can therefore change a substantial part of the label the model is asked to learn.

### The experts inside each head

Each role has four local experts: Ridge regression with alpha 10; histogram gradient boosting with depth three, minimum leaf twenty, 200 iterations and L2 regularization ten; Extra Trees with 200 trees and minimum leaf fifteen; and a soft-archetype regressor.

The soft-archetype regressor fits up to three height/weight KMeans clusters. It predicts from distance-based soft membership and cluster outcome means shrunk toward the head's overall mean with strength twenty. It does not assume hard membership in a single perfect body type. Its minimum cluster support is fifteen rows, not necessarily fifteen distinct athletes; repeated seasons and weighted support need that qualification.

A shared fifth learned expert standardizes height and weight within the training sport-role and fits degree-two polynomial Ridge with alpha 100 to the normalized coordinates and percentile outcomes. Its weighting gives equal mass to sports, then roles, then athletes. It never treats a raw sack and a raw steal as the same response. A sixth expert always predicts the neutral target fifty.

Each expert output is clipped to 0–100 before blending. The blend has nonnegative weights summing to one, chosen to minimize athlete-balanced squared error. A numerical optimizer uses scaled scores and verified deterministic starts. Repeated career seasons are inverse-weighted so a longer observed career does not automatically receive more total influence.

Evidence: [R8], [R10], [R12].

## 13 How the unified model is evaluated

### The identity split

An identity hash assigns approximately sixty percent of athletes to training, twenty percent to calibration and twenty percent to test. The fixed split salt is stored separately from model version so a future version label does not itself reshuffle cohorts. All seasons and role changes of an athlete remain in one partition.

Training identities contribute eligible 2021–2025 rows, including contemporaneous 2025 observations. Calibration and test identities contribute only 2025 rows. Therefore, this study asks how a contemporary body association generalizes to unseen elite athletes, not how a model trained before the season predicts the future.

EPL is a same-season unseen-athlete study because its detailed possession labels exist only in 2025. Cross-sport identifiers are not actual sport-switching labels. The source snapshot was already inspected during project development, so the test is held out from fitting but is not a new blind or prospective benchmark.

### Nested fitting

Three outer athlete-grouped folds assess the stack. Inside each outer training fold, a separate three-fold crossfit produces predictions for athletes excluded from the base experts. The blend weights are fitted to those inner out-of-fold predictions rather than predictions on the experts' own training rows.

The complete target scale, imputation/scaling, body standardization and expert fits remain inside those folds. A final three-fold out-of-fold pass on the training identities learns final weights; the experts are then fitted on all training identities. Calibration residuals do not choose those weights.

The stack is selected instead of neutral fifty only if nested validation improves MSE by more than one percent and has positive Spearman rank correlation. Otherwise `selected_method` is `baseline` and the selected prediction is exactly fifty.

### The primary score checks

The internal status `evidence_supported` additionally requires positive frozen-test MSE improvement, positive test rank correlation, at least nine calibration athletes and at least fifteen test athletes. It means the exploratory point checks passed. The clearer accompanying evidence grade is `provisional_point_gate_passed`.

Statistical significance and adequate interval coverage are not primary-score gates in this implementation. A 95 percent bootstrap interval crossing zero does not itself withhold the primary number. Poor interval coverage triggers a warning, not automatic suppression. This is an important review decision, not a detail to hide behind the word supported.

### Intervals and bootstrap evidence

The provisional 90 percent prediction interval uses absolute residuals from separate calibration athletes. With n residuals, its radius is the ordered residual at rank ceiling of (n + 1) times 0.90. If that rank exceeds the available sample, the radius is infinite and the displayed interval is 0–100. Bounds are clipped to the target range.

These intervals describe an individual's activity target, not a confidence interval on the average prediction or a probability of professional success. Their usual coverage rationale depends on exchangeability, which drift, selection and outside-sport application can violate.

The report also performs 300 athlete-cluster bootstrap resamples of test MSE improvement with seed 42. It reports uncertainty in the measured improvement over neutral fifty. No current head has a 95 percent improvement interval wholly above zero.

The older baseline rate models use a different validation-residual interval calculation. Those intervals must not be described as the unified model's separate-calibration procedure.

Evidence: [R5], [R8], [R10], [R12].

## 14 The saved unified results

P means the exploratory point checks passed, not statistical confirmation. N means no primary predictive evidence under the implemented checks. S means insufficient measured training support. MSE change is improvement over neutral fifty, so positive is better. Coverage is observed test coverage of a nominal 90 percent interval. These are the current saved results before the EPL partial-block correction.

| Role | Train athletes | Test athletes | MSE improvement | Interval coverage | Status |
|---|---:|---:|---:|---:|---|
| NFL EDGE | 131 | 12 | -5.5% | 75.0% | N |
| NFL IDL | 132 | 28 | -1.7% | 89.3% | N |
| NFL LB | 125 | 16 | 0.0% | 93.8% | N |
| NFL OLB hybrid | 120 | 22 | 7.8% | 100.0% | P |
| NFL CB | 175 | 19 | 2.3% | 89.5% | N |
| NFL S | 141 | 18 | 0.0% | 77.8% | N |
| NBA guard | 185 | 48 | 0.0% | 93.8% | N |
| NBA forward | 168 | 36 | 1.3% | 100.0% | P |
| NBA center | 71 | 10 | 3.4% | 90.0% | N |
| NHL defense | 227 | 43 | -4.3% | 93.0% | N |
| NHL center | 207 | 45 | 4.6% | 93.3% | P |
| NHL wing | 211 | 58 | 0.0% | 87.9% | N |
| EPL DEF | 76 | 21 | 16.7% | 52.4% | P |
| EPL MID | 80 | 33 | 8.8% | 87.9% | P |
| EPL FWD | 19 | Not evaluated | Not fitted | Not fitted | S |

The role-level target MAEs are generally about 22–35 percentile points, so a point score must not be interpreted as precise. Average interval widths for provisionally passing NFL OLB hybrid, NBA forward and NHL center are 97.3, 92.1 and 94.8 points respectively. Very wide intervals can achieve high coverage while conveying little individual discrimination.

EPL DEF's nominal 90 percent interval covers only 52.4 percent of its twenty-one test athletes. That is a serious calibration warning. Its partial-block labels also need correction, and a lower test error does not rescue an incomplete target. The current pipeline still allows an in-domain provisional defender point score because neither issue is presently a separate automatic suppression rule.

Some apparently conflicting statuses are intentional. NFL CB has slightly better MSE but negative test rank correlation, so it has no primary score. NBA center has positive point improvement but only ten test athletes. NFL LB, NFL S, NBA guard and NHL wing select neutral fifty after nested validation.

The shared cross-sport expert is present in the architecture, but its weight is effectively zero in all five provisionally passing heads. The current results therefore do not demonstrate that cross-sport sharing improves the models that pass the point checks. The software is unified; useful transfer learning remains unestablished.

The weight CSV and chart describe candidate stacks. For a head whose selected method is baseline, its candidate weights are not the active prediction rule; the active selected output is fifty. That distinction matters when inspecting a large shared-expert weight in a head that did not select the stack.

Evidence: [R8], [R10].

## 15 How to read an athlete score

### Original score command

`score` returns broad role-label probabilities and registered physical rate associations. It does not run the returning-player forecasts. Its event-rate outputs are in per-100 sport-specific units, require age when the saved model needs it, and may be returned even if their test model did not beat a role mean. Out-of-domain conditions are flagged rather than withheld.

It does not expose the separate recent EPL per-90 models. The original compatibility example and the newer ensemble example therefore have different meanings.

### Unified efficacy command

`efficacy` accepts a JSON profile or metric flags. Height and weight must have explicit units; JSON supports centimeters or total inches or feet-plus-inches, and kilograms or pounds. Conflicting aliases, non-finite values and nonpositive core dimensions fail validation. An optional supplied age must be adult; extreme positive dimensions generate warnings and domain checks rather than being clipped into the reference population.

Recognized testing and limb measurements are retained as unused metadata. Unknown fields, including proposed mental measures, are explicitly ignored with warnings. Changing age, wingspan or an arm-length field does not change this version's learned efficacy prediction.

For each fitted role, physical-domain checks compare the profile with one latest training record per athlete. The scorer checks raw training minimum/maximum dimensions and a regularized two-dimensional Mahalanobis squared distance against 9.21034. This combines both dimensions rather than treating each alone as sufficient. The cutoff is a reference-domain heuristic, not a biological statement that an unusual athlete cannot play.

Physical fit is 100 times one minus the empirical CDF of that distance among reference athletes. It is a centrality/similarity diagnostic. It is neither the old role classifier's probability nor an efficacy multiplier. The primary efficacy number is withheld for an out-of-domain profile, failed evidence checks or insufficient support, while labeled experimental values may remain visible.

The sport summary selects the largest publishable in-domain role estimate. That maximum is a browsing convenience without separate sport-level calibration. Its interval is not a simultaneous guarantee across all candidate roles. No validated ranking of sports follows from choosing the largest number.

### The included example

The example profile is 188 cm, 95 kg, age twenty-five, wingspan 197 cm, arm length 82 cm and leg length 98 cm. Only height and weight affect its learned score.

| Sport | Primary result | Interval | Physical fit | Explanation |
|---|---|---|---:|---|
| NFL | OLB hybrid 31.88 | 0 to 84.91 | 4.17 | In domain but near an atypical edge of the reference body distribution |
| NHL | Center 52.05 | 0.25 to 100 | 73.91 | In domain with a very wide prediction interval |
| NBA | No primary sport rating | Not applicable | Role-specific | Guard lacks predictive evidence; forward is out of domain |
| EPL | No primary sport rating | Not applicable | Role-specific | DEF and MID are out of domain; FWD lacks training support |

A null is not zero ability. The overlapping intervals do not establish that this person would be better at hockey than football. The example is useful for understanding the interface and abstention, not for making a real athlete-placement decision.

Evidence: [R6], [R8], [R10], [R12].

## 16 Corrections and decisions to review

The following items separate verified defects and documentation mismatches from scientific choices. They are recorded for your review; the underlying code, data and fitted outputs have not been silently corrected.

### High priority data correction

EPL partial block coverage needs a metric-specific completeness policy, propagated from player-match rows to season totals and model eligibility. Eight eligible unified defenders are affected. Add regression tests for a player with one observed and one missing block row, then rebuild and rerun affected studies. Do not fill the missing values with zero or claim the current EPL DEF gain is established evidence.

### Evidence policy and user-facing language

The internal `evidence_supported` label is stronger than its actual condition. A clearer name would refer to provisional point checks. Decide whether to withhold all primary ratings until bootstrap improvement evidence excludes zero, whether to suppress poorly calibrated intervals or point ratings, and what external sample size and prospective evaluation would be acceptable. These are future policy decisions, not safeguards already present.

EPL DEF currently publishes an in-domain provisional point score despite poor interval coverage and the newly found incomplete-label issue. The guide recommends treating that result as requiring correction, not as an endorsed player rating.

### Target construct and archetype interpretation

Review the fixed role weights with people who understand assignments and what possession winning means in each league. Decide whether activity per opportunity, possession recovery, prevented threat or net defensive value is the desired target. Those are different constructs. The current targets intentionally combine some activity and disruption proxies.

Review whether faceoff wins per ice time, blocks and hits reward usage or reactive defending in ways that conflict with your goal. Consider a direct possession-change target where the event data permit it. Any change requires a versioned target and fresh evaluation rather than relabeling the current score.

Body clusters should be called descriptive archetypes, not proven successful builds. Cluster support measured in weighted rows should not be described as a count of independent athletes. The shared expert's near-zero contribution in passing heads should be visible rather than presenting the architecture as demonstrated cross-sport transfer learning.

### Rebuild and registry gaps

`analyze --sport all` rebuilds the shared analyses but does not rerun EPL's separate recent per-90 study. That study is called by `epl.run()` after shared analysis. The README's broad rebuilding description needs this qualification. If using existing cached data, a programmatic call to the separate recent study can rerun it without treating the generic analyze command as sufficient.

The four `recent_2025_*_per90.joblib` files are outside EPL's shared model registry and are not consumed by the legacy scorer. A future implementation should give them their own registered integrity/version contract and explicit inference path if they are intended for application use.

Hash verification protects against mismatched or changed artifacts. It is not authenticity if someone replaces both a pickle and its registry. Only trusted local joblib files should be loaded. Preserving raw snapshots also matters: a manifest can detect upstream changes but cannot force a website to serve an old file.

### Documentation and provenance mismatches

The last paragraph of `reports/findings.md` predates the unified prototype and still says a trained cross-sport ensemble is a later stage. The correct distinction is that an efficacy prototype exists, while validated sport-switching prediction remains unachieved.

The optional community NFL anthropometric files have a generic `nflverse/data` source label in the download manifest because the adapter derives the label from a URL path component. Their actual URLs and license notes identify the community source. Correct the source label without pretending the raw content was downloaded from nflverse. This is provenance labeling, not an error in the current core model's feature values.

Use the actual inventory and current code as the source of truth when an older note disagrees. EPL QA is written in both `reports/epl/qa.json` and `data/processed/epl/qa.json`; the existence of two copies is not itself a missing-output defect.

### Coverage and rights decisions

The all-rostered-player objective is only partly realized. NHL is appearance-based; NBA uses available roster/profile source coverage; EPL is an FPL roster universe; NFL retains its broader resolved roster layer but excludes unresolved IDs and nondefensive roles for the defensive model. Decide whether contract/transaction reconstructions are necessary for the next study.

Review the thirty-five fuzzy EPL profile matches. Obtain dated tests or true annual measurements before studying physical changes. Keep conditional NFL sources separate until source-use review is complete, and review enhanced EPL and MoneyPuck rights before redistribution or commercial use. Public access should not be described as an unrestricted license.

Evidence: [R2], [R3], [R4], [R5], [R6], [R7], [R8], [R9].

## 17 How to reproduce and inspect the work

Use Python 3.12 with the locked environment. The commands below are intended to be run from the repository root. They are instructions for future use; this guide did not refresh the sources or refit the models.

### Prepare the environment

```
uv sync --locked --extra dev --python 3.12
```

### Inspect saved results without retraining

```
uv run possession-lab status
uv run possession-lab score --sport all --height-cm 188 --weight-kg 95 --age 25
uv run possession-lab efficacy --profile examples/athlete.json
```

The default sport is NFL for the older run/analyze/score commands, but all four sports for efficacy and train-ensemble. `--root` selects the workspace location. A JSON profile allows imperial units and retained optional measurements; simple command-line measurement flags are metric. The example profile and an imperial example are under `examples/`.

### Rebuild source panels and individual analyses

```
uv run possession-lab run --sport all
uv run possession-lab manifest
```

Existing caches are verified before reuse. Upstream content that differs from a tracked source hash fails rather than silently becoming the same experiment. `--accept-source-updates` explicitly accepts a new dataset version and should be paired with a new evaluation. It is not a routine workaround for an unexpected hash error.

### Rebuild shared analyses from existing panels

```
uv run possession-lab analyze --sport all
```

This does not refresh the processed tables or rerun the separate recent EPL per-90 models. To rerun the latter from a current processed EPL panel, the existing public Python entry point is:

```
uv run python - <<'PY'
from pathlib import Path
import pandas as pd
from possession_lab.sports.epl import recent_season_model
root = Path.cwd()
panel = pd.read_parquet(root / 'data/processed/epl/player_seasons.parquet')
recent_season_model(panel, root)
PY
```

After an EPL aggregation-code correction, rebuild its processed panel first rather than rerunning only this model against stale labels.

### Train and score the unified model

```
uv run possession-lab train-ensemble
uv run possession-lab efficacy --height-cm 188 --weight-kg 95 --age 25 --output work/athlete_rating.json
```

Training writes a local unified joblib model and aggregate reports. Detailed player predictions remain local and ignored by Git. The `--fast-development-fit` option reduces expert fits for pipeline checks and is explicitly flagged; it is not the configuration used by the saved substantive evaluation.

The current unified loader explicitly restricts inputs to 2021–2025 and evaluates held-out athletes in 2025. Passing a newer `--seasons` value to another command does not automatically create a correctly updated ensemble study. Changing the study window and prospective test requires an intentional code/configuration change and a new version.

### Run checks

```
uv run ruff check src tests
uv run pytest -q
```

The GitHub workflow runs the locked environment, lint and tests on push and pull requests. Unit tests use synthetic fixtures and do not redownload the full leagues. Sport QA reports cover real-data invariants. The EPL block defect demonstrates why passing tests and reconciled counts do not prove that every scientific label is complete or correct.

Evidence: [R1], [R4], [R5], [R7], [R11], [R12].

## 18 A practical order for your review

Start by deciding whether the target should remain possession/disruption activity or become a stricter possession-change or value measure. Review the role definitions and hand weights before investing in more complex models; a more accurate predictor of the wrong target will not answer your question.

Next, correct and regression-test the EPL block completeness issue, review the fuzzy physical matches, and rerun the affected evidence. Keep the original reports as an explicitly identified historical version so the effect of the correction is visible.

Then decide which physical measurements can be obtained under suitable terms and comparable protocols. Height and weight alone are not enough to claim individual efficacy. NFL testing can support an NFL-specific extension without pretending that a football forty-yard time and an on-ice skating maximum are the same measure. Preserve test dates, surface, equipment, effort protocol and missingness rather than forcing nominally similar columns together.

For awareness features, first define the decision task and exposure. Anticipation might be evaluated from the timing of an athlete's response to an observable cue; accuracy needs attempts and opportunities, not just successful interceptions. Those examples are proposed study directions, not features already engineered in the repository. Coaching input, tracking/event detail and reliability tests would be needed before synchronizing them.

Finally, freeze a future or external evaluation before selecting another model based on the existing test snapshot. Recheck individual uncertainty and compare with simple role and persistence baselines. A representative dataset of prospects or actual sport switchers would be required to move from elite-peer association toward the original viability claim.

The immediate review question is therefore not whether the code runs; it does. It is whether the definitions, coverage and evidence policy match the question you want the eventual application to answer.

## Appendix A Where to find the evidence

These references point to the reviewed repository snapshot. Function names and JSON keys are included so you can locate the exact implementation without reading every file.

| Reference | Repository evidence |
|---|---|
| R1 | `README.md`; repository commands, scope and current overview |
| R2 | `metadata/data_inventory.md`, `dataset_catalog.json`, `download_manifest.json`; table grains, schemas, source URLs, hashes, retrieval dates and recorded terms |
| R3 | `reports/nfl/qa.json`, `reports/nba/qa.json`, `reports/nhl/qa.json`, `reports/epl/qa.json`; real-data checks and coverage |
| R4 | `src/possession_lab/sports/`; acquisition and canonicalization for each sport |
| R5 | `src/possession_lab/analysis.py`; `build_forecast_pairs`, `forecast_models`, `physical_role_model`, `physical_effectiveness_models`, `descriptive_archetypes` |
| R6 | `src/possession_lab/predict.py`; `score_physical_profile` and registered legacy inference |
| R7 | `docs/nfl_pipeline.md`, `docs/nhl_pipeline.md`, `docs/epl.md`, `docs/model_card.md`; sport notes and task boundaries, read with the corrections in this guide |
| R8 | `src/possession_lab/ensemble.py`, `ensemble_targets.py`, `ensemble_experts.py`, `ensemble_evaluation.py`, `ensemble_features.py`, `ensemble_score.py`; unified model and scoring implementation |
| R9 | `reports/<sport>/summary.json`, split manifests, `reports/findings.md`; baseline results. EPL recent study: `reports/epl/recent_2025_association.json` |
| R10 | `reports/ensemble/evaluation.json`, `evaluation.csv`, `expert_weights.csv`, `model_registry.json`, `example_athlete.json`; frozen unified outputs and example |
| R11 | `pyproject.toml`, `uv.lock`, `.github/workflows/tests.yml`, `.gitignore`, `src/possession_lab/cli.py`, `io.py`, `catalog.py`; environment, checks, reproducibility and orchestration |
| R12 | `tests/`; synthetic data, identity, denominator, missingness, temporal, grouping, target, optimizer, scoring and integrity tests |

In the unified JSON, each head's `nested_cv`, `metrics`, `candidate_metrics`, `mse_improvement_cluster_bootstrap`, `interval_diagnostic`, `target` and `target_weight_sensitivity` carry the detailed evidence. `selected_method` distinguishes an active stack from the neutral baseline. `improvement_statistically_established` is false for every current head, even where the exploratory status says `evidence_supported`.

The data and model directories are local artifacts. Their absence from GitHub is intentional. The registries define which model files belong to the current run; an old joblib still present in a directory is not automatically an active model.

## Appendix B Terms used in the reports

| Term | Meaning in this project |
|---|---|
| Opportunity | The exposure denominator, such as observed NFL participation or minutes |
| Persistence | Predicting the next outcome from the previous season's value |
| Hurdle model | Predicting whether any opportunity occurs and how much occurs conditional on positive opportunity |
| Shrinkage | Pulling noisy small-sample rates toward a reference rate |
| CDF or percentile | Where a value lies in a stored reference distribution |
| Out of fold | A prediction for an athlete excluded from the model fit that produced it |
| Nested validation | Separate inner fitting/selection and outer assessment folds |
| Calibration set | Separate athletes used to estimate residual interval widths |
| MAE | Mean absolute prediction error, in the target's unit |
| MSE and RMSE | Mean squared error and its square root; they emphasize large errors more than MAE |
| R squared | Squared-error improvement relative to a mean prediction; it can be negative |
| Spearman correlation | Association between predicted and observed ranks, not exact-value accuracy |
| Brier error | Squared probability error for a binary outcome; lower is better |
| Bootstrap interval | Resampling-based uncertainty for a statistic, conditional on the sample and method |
| Prediction interval | A range intended to describe an individual's future or held-out target, subject to its assumptions |
| Out of domain | A profile outside the implemented reference-body checks, not proof of inability |
| Archetype | A descriptive cluster or soft grouping, not automatically a successful or optimal build |
| Efficacy rating | The current prototype's role-relative activity estimate, not overall skill or transition success |

## Appendix C What this documentation pass changed

This pass adds the owner guide in Markdown and Word. It audits the saved data, code, model registries and tests, and identifies corrections for review. It does not alter source downloads, canonical player tables, model code, fitted predictors or previously saved performance results. The EPL partial-block issue and the other review items remain to be corrected through a separate implementation and evaluation step.
