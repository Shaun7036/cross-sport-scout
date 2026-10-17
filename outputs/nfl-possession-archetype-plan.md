# NFL possession-creation and defensive-disruption archetype plan

Prepared 2 October 2026

This is the active first-sport implementation plan for the wider cross-sport project. It covers the 2021–2025 NFL seasons and takes the project from raw public data through defensive role definitions, physical profiles, opportunity-adjusted metrics, archetype discovery, forecasting, hidden-value screening, and the eventual cross-sport handoff.

The companion [2025–26 source audit](2025-26-sports-data-source-audit.md) contains the full source assessment. The [multi-season project roadmap](multi-season-project-roadmap.md) defines the shared schema and temporal rules for all four sports.

---

# Executive decision

The NFL is the best first league for this project. It has:

- A reconstructable all-rostered-player universe through weekly rosters.
- Stable GSIS player IDs and a strong public ID crosswalk.
- Game/week defensive statistics.
- Defensive snap counts.
- Advanced pressure, coverage, and missed-tackle fields.
- Full play-by-play with game situation and expected-points context.
- Participation data that identify the defenders on a play and some team-level deployment context.
- Historical combine and pro-day measurements for a substantial, but selected, subset.

The project should not search for one generic “possession-winning defender.” In football, only a few events directly transfer possession. The correct umbrella construct is:

> **Possession creation and defensive disruption**

Keep these domains separate before producing any summary:

1. Direct takeaway creation.
2. Pass-rush disruption.
3. Coverage disruption.
4. Run disruption.
5. Tackle reliability.
6. Drive-ending value.
7. Decision cost and discipline.
8. Athletic range and physical profile.

This distinction matters. An interception directly changes possession. A forced fumble creates a chance to change possession. A pressure, sack, pass breakup, or tackle for loss may prevent a conversion or end a drive, but it is not automatically a turnover.

---

# Step 1 — freeze the questions before collecting data

Build four separate products. They may share tables, but they must not be presented as the same model.

## Product A: descriptive archetypes

Question:

> Which physical builds and defensive play styles were associated with successful NFL disruption from 2021 through 2025?

This is retrospective. It may use completed 2025 performance and can describe physical archetypes, play-style archetypes, role changes, and persistent high performers.

## Product B: returning-player forecast

Question:

> Using only information known before season t, can the model predict a returning defender’s availability, opportunity, and role-relative effectiveness in season t?

For the final evaluation:

- Features end before the 2025 season anchor.
- Targets come from the 2025 season.
- 2025 remains unopened until metric, model, threshold, and reporting choices have been selected using 2024.

## Product C: hidden-value screen

Question:

> Which defenders appear more effective than their prior deployment or market signal suggests?

The talent model must not use salary or draft capital. Those variables are added after the talent estimate to test whether deployment or the market appears to under-rate the player.

## Product D: physical-only role fit

Question:

> Based on body dimensions and historical testing, which NFL defensive roles and physical archetypes does a rookie, prospect, or outside-sport athlete resemble?

For an athlete from another sport, the result is a similarity or compatibility estimate. It is not a calibrated probability of becoming an NFL player because there are too few observed cross-sport transitions to learn that probability.

---

# Step 2 — freeze the population and season rules

## Seasons

Use NFL season labels:

- 2021
- 2022
- 2023
- 2024
- 2025

This is a coherent first window because every season is in the 17-game scheduling era. It also provides three development seasons, a 2024 validation season, and a 2025 final test.

Five seasons are sufficient for the first NFL performance panel. They are not sufficient for the best physical-only entry model. For that model, later extend combine and entry cohorts to at least 2010 while retaining 2021–2025 as the principal NFL performance window.

## Competition phase

Start with regular season only.

- Retain the nflverse season_type field.
- Store postseason separately.
- Do not mix regular-season and postseason rates: opponent quality, rotation, game leverage, and sample sizes differ.
- Do not assume every year has exactly 272 completed regular-season games. The 2022 Buffalo–Cincinnati game was cancelled; let the schedule table and game status determine the completed-game denominator.

## Player universe

For each season, define the descriptive universe as:

> The union of every player appearing on an NFL weekly roster at any point in the season.

Then left-join appearances, snaps, and performance. Preserve these states separately:

- Rostered and appeared on defense.
- Rostered and appeared only on offense or special teams.
- Rostered but did not appear.
- Appeared but recorded zero relevant events.
- Had no relevant opportunity.
- Source did not cover the observation.
- Measurement missing.

Do not start from a leaderboard or a minimum-snap filter. That would erase the low-opportunity players needed for availability modeling and hidden-value research.

## Initial modeling population

Keep all rostered players in the data warehouse. Limit NFL archetype and effectiveness model v1 to defenders:

- Defensive line.
- Edge/outside pass rushers.
- Off-ball linebackers.
- Cornerbacks.
- Safeties and defensive hybrids.

Special-team possession events and offensive players can be separate extensions later.

---

# Step 3 — create a source and definition registry

Before downloading, create a row for every source and metric definition.

Minimum source-registry fields:

| Field | Purpose |
|---|---|
| source_id | Stable internal source key |
| publisher | nflverse, NFL, PFR-derived, FTN, community repository, and so on |
| dataset | Weekly roster, player stats, snap counts, PBP, participation, combine |
| access_url | Documentation or file URL |
| coverage_start/end | Expected years and phases |
| player_key | GSIS, PFR, SMART/person, or other ID |
| game_key | Source game ID |
| license_or_terms | License, attribution, or restriction note |
| provider_version | Needed across definition/provider breaks |
| retrieved_at | Snapshot timestamp |
| file_hash | Reproducibility |
| schema_hash | Detect silent field changes |

Every metric also needs a definition ledger:

| Field | Example |
|---|---|
| metric_code | pressure |
| provider | PFR-derived advanced defense |
| definition_version | pfr_adv_v1 |
| numerator | Credited pressures |
| denominator | Pass-rush snaps if known; otherwise named fallback |
| unit | Count or rate |
| available_seasons | 2021–2025 |
| caveats | Provider attribution; overlapping subcomponents |

Do not merge two columns merely because both are called “pressure,” “target,” or “missed tackle.” Definition equivalence must be established first.

---

# Step 4 — acquire the raw NFL source stack

Use immutable landing and bronze layers. Never edit downloaded files in place.

Maintain two acquisition/model tiers:

1. **Core reproducible tier:** player identity, weekly rosters, schedules, player/team statistics, play-by-play, participation, and non-PFR fields whose reuse basis is documented.
2. **Conditional enrichment tier:** PFR-derived snap counts, advanced defense, nflverse combine fields, and community combine/pro-day enrichments, each subject to its upstream rights and attribution review.

The core model must remain runnable without the conditional tier. That gives the project a defensible fallback if a public research prototype later becomes a redistributed or commercial product.

## Exact five-season file manifest

Prefer Parquet for the raw mirror while retaining the documented CSV alternatives for manual inspection.

For each year from 2021 through 2025:

~~~text
https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_YEAR.parquet
https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_YEAR.parquet
https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_YEAR.parquet
https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_YEAR.parquet
https://github.com/nflverse/nflverse-data/releases/download/pbp_participation/pbp_participation_YEAR.parquet
https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_YEAR.parquet
https://github.com/nflverse/nflverse-data/releases/download/pfr_advstats/advstats_week_def_YEAR.parquet
https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_YEAR.parquet
~~~

Download once for the complete window:

~~~text
https://github.com/nflverse/nflverse-data/releases/download/players/players.parquet
https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet
https://github.com/nflverse/nflverse-data/releases/download/combine/combine.parquet
~~~

Published regular-season summary files can be used as reconciliation controls, but the canonical seasonal aggregates should be built from the frozen weekly files:

~~~text
https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_YEAR.parquet
https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_reg_YEAR.parquet
~~~

## A. Weekly rosters: the population spine

Documentation: [nflverse weekly rosters](https://nflreadr.nflverse.com/reference/load_rosters_weekly.html)

Verified filename pattern:

~~~text
https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_YEAR.csv
~~~

Collect 2021 through 2025.

Useful fields include:

- gsis_id.
- Team and week.
- Roster status.
- Position and depth-chart position.
- Date of birth.
- Listed height and weight.
- College, experience, entry status, and draft fields.

Create a roster spell whenever a player’s team, status, or position state changes. A final-week roster alone is not sufficient.

## B. Master player and ID crosswalk

Documentation: [nflverse players](https://nflreadr.nflverse.com/reference/load_players.html)

File:

~~~text
https://github.com/nflverse/nflverse-data/releases/download/players/players.csv
~~~

Use GSIS ID as the principal NFL player key. Retain:

- PFR ID for snap counts, advanced defense, and combine joining.
- NFL/SMART person ID for official or community combine enrichment.
- ESPN, PFF, OTC, and other identifiers for optional future sources.

Names are for display and manual review, not durable joins.

## C. Weekly player statistics

Documentation: [nflverse player statistics](https://nflreadr.nflverse.com/reference/load_player_stats.html)

Verified filename pattern:

~~~text
https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_YEAR.csv
~~~

Core defensive fields include:

- Solo and assisted tackles.
- Tackles for loss.
- Sacks.
- Quarterback hits.
- Forced fumbles.
- Opponent-fumble recoveries.
- Interceptions and interception return value.
- Passes defended.
- Safeties.
- Defensive touchdowns and blocked kicks.

These are the stable first-pass outcomes.

## D. Snap counts

Documentation: [nflverse snap counts](https://nflreadr.nflverse.com/reference/load_snap_counts.html)

Verified filename pattern:

~~~text
https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_YEAR.csv
~~~

Use defensive snaps and defensive snap percentage as the broad exposure denominator. The player key is normally PFR ID, so resolve it through the master crosswalk.

Snap counts are PFR-derived. Keep them in the conditional enrichment layer until the project’s intended use has passed an upstream-rights review. In the core tier, use exploded participation player-plays as the principal broad exposure and reconcile them against snap counts where allowed.

## E. PFR-derived advanced defense

Documentation: [nflverse PFR advanced statistics](https://nflreadr.nflverse.com/reference/load_pfr_advstats.html)

Verified filename pattern:

~~~text
https://github.com/nflverse/nflverse-data/releases/download/pfr_advstats/advstats_week_def_YEAR.csv
~~~

Important fields include:

- Coverage targets.
- Completions, yards, touchdowns, target depth, YAC, and passer rating allowed.
- Blitzes.
- Hurries, quarterback knockdowns/hits, sacks, and pressures.
- Combined tackles.
- Missed tackles and missed-tackle percentage.

This is the most useful free bulk layer for individual pressure, coverage, and tackling opportunity. Treat assignments and definitions as provider observations, not ground truth from tracking.

It is PFR-derived. Sports Reference’s [data-use policy](https://www.sports-reference.com/data_use.html) places separate restrictions on AI/ML use. Do not assume that a downstream repository license overrides upstream terms. Keep a core result that does not depend on these fields, and report core-versus-enhanced performance separately.

## F. Play-by-play

Documentation: [nflverse play-by-play](https://nflreadr.nflverse.com/reference/load_pbp.html)

Verified filename pattern:

~~~text
https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_YEAR.parquet
~~~

Play-by-play supplies:

- Down, distance, time, score, field position, and drive.
- Play type and game situation.
- EPA and WPA.
- Interceptor, sack, half-sack, quarterback-hit, tackle-for-loss, tackle, forced-fumble, and recovery identifiers where recorded.
- Penalties and accepted/declined context.

Use it to construct contextual and drive-ending features after the aggregate MVP works.

## G. Participation

Documentation: [nflverse participation loader](https://nflreadr.nflverse.com/reference/load_participation.html) and [participation dictionary](https://nflreadr.nflverse.com/articles/dictionary_participation.html)

Verified filename pattern:

~~~text
https://github.com/nflverse/nflverse-data/releases/download/pbp_participation/pbp_participation_YEAR.csv
~~~

Useful fields include:

- Defenders present on the play.
- Offensive and defensive personnel.
- Defenders in the box.
- Number of pass rushers.
- Formation.
- Play-level pressure.
- Time to throw.
- Route, man/zone, and coverage fields where populated.

Critical limitation:

> These fields do not consistently identify which individual defender rushed or held a particular coverage assignment on every play.

Critical source break:

- Participation through 2022 came from NFL Next Gen Stats.
- From 2023 onward it comes from FTN Data via nflverse.

Store participation_provider and definition_version on every record. Audit distributions across the 2022–2023 boundary. Fields that are not demonstrably compatible must remain provider-era features or be calibrated separately.

The FTN layer has separate attribution and share-alike terms. Preserve its required attribution and do not assume that the main nflverse license alone describes every underlying field.

## H. Schedules and game metadata

Use nflverse schedules for:

- Game IDs.
- Season, week, and phase.
- Date/time.
- Home/away teams.
- Stadium, surface, roof, weather, rest, and result where available.

The schedule table is the authority for which games were scheduled, completed, cancelled, or postseason.

## I. Team statistics and injuries

Collect weekly team statistics as a reconciliation and context layer. Use them to verify team takeaways, sacks, plays, and offensive/defensive opportunity without treating team totals as an individual player’s contribution.

Collect weekly injury reports for availability research, but preserve report status and publication timing. A missing report is not proof that the player was healthy, and a target-season injury outcome cannot be used in a preseason forecast.

## J. Historical combine data

Documentation: [nflverse combine dictionary](https://nflreadr.nflverse.com/articles/dictionary_combine.html)

File:

~~~text
https://github.com/nflverse/nflverse-data/releases/download/combine/combine.csv
~~~

Core measurements:

- Height and weight.
- 40-yard dash.
- Bench press.
- Vertical jump.
- Broad jump.
- Three-cone.
- Short shuttle.

Join PFR ID to the master player crosswalk.

The nflverse combine release is PFR-derived and belongs in the conditional enrichment tier unless upstream use is cleared.

## K. Optional arm, hand, split, and wingspan enrichment

The official [NFL Combine Tracker](https://www.nfl.com/combine/tracker/) and player profiles may contain:

- Arm length.
- Hand size.
- 10-yard split.
- Wingspan for recent cohorts.
- Additional drill results.

The community [NFL Draft Combine & Pro Day dataset](https://github.com/array-carpenter/nfl-draft-data) is useful for research and prototype enrichment and can join through NFL person/SMART ID, but its data-reuse position must be checked before redistribution or production use.

Treat official NFL pages as optional enrichment, not the core dependency:

- The backing endpoint is undocumented.
- Authentication and schemas can change.
- Terms must be reviewed before automated collection.
- A cached snapshot and field-level provenance are mandatory.

## L. Source rights and attribution

Record source-level and field-level terms rather than assigning one license to the entire joined table.

- The main [nflverse-data repository](https://github.com/nflverse/nflverse-data) publishes releases under [CC BY 4.0](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md); credit nflverse, link the license, and describe transformations.
- Participation uses separate CC BY-SA 4.0 attribution. Credit “NFL NextGenStats via nflverse” for 2022 and earlier and “FTN Data via nflverse” for 2023 onward.
- PFR-derived snap, advanced-defense, and combine fields need a separate upstream-rights review.
- The community combine/pro-day repository does not currently provide a sufficiently clear reuse license for a production dependency.
- Official NFL pages and undocumented backing endpoints should be used only within the permission and terms appropriate to the project.

“Free to view” and “openly licensed for model training and redistribution” are different states. Preserve that distinction in the source registry.

## M. Tracking research, not the core feed

NFL player tracking records location, speed, distance, and acceleration at high frequency, but the full 2021–2025 raw league-wide feed is not publicly downloadable. See [NFL Football Operations’ tracking overview](https://operations.nfl.com/gameday/technology/nfl-next-gen-stats).

Big Data Bowl releases are valuable for developing:

- Closing-speed ideas.
- Pursuit-angle features.
- Coverage separation.
- Reaction and movement concepts.
- Blocker–rusher interaction models.

They are selected samples or competition tasks, not a substitute for a full five-season feed.

---

# Step 5 — snapshot the raw data reproducibly

Recommended directories:

~~~text
data/
  landing/
    nflverse/
      weekly_rosters/2021/...2025/
      players/
      player_stats/2021/...2025/
      snap_counts/2021/...2025/
      advanced_defense/2021/...2025/
      play_by_play/2021/...2025/
      participation/2021/...2025/
      schedules/
      combine/
    nfl_optional/
      official_combine/
      community_combine/
  bronze/
  silver/
  gold/
  model/
  quarantine/
metadata/
  source_registry/
  schemas/
  manifests/
  data_dictionary/
~~~

For every file, save:

- Source and resolved download URL.
- Retrieval timestamp.
- Content hash.
- Byte size and row count.
- Column names and types.
- Minimum/maximum season, week, and game date.
- License/terms classification.
- Provider/version.

Raw URLs can be refreshed or corrected. A model is reproducible only if its exact snapshots and hashes are retained.

---

# Step 6 — resolve identity before modeling

Build a player_identity table with one row per source ID.

Minimum fields:

- Internal player UUID.
- GSIS ID.
- PFR ID.
- NFL/SMART person ID.
- ESPN/PFF/OTC IDs where present.
- Canonical name.
- Date of birth.
- Match method.
- Confidence.
- Manually verified flag.
- Valid-from and valid-to dates where IDs can change.

Match order:

1. Direct crosswalk ID.
2. Direct source ID already linked to a known player.
3. Normalized name plus date of birth.
4. Normalized name plus team/season/position as a review candidate.
5. Manual review.

Never accept name-only fuzzy matching automatically. Suffixes, punctuation, initials, duplicate names, and name changes cause silent errors.

Identity QA:

- One GSIS ID should map to one internal player.
- One PFR ID should not map to multiple active players without an explicit reason.
- Flag birth-date conflicts.
- Flag source rows with no crosswalk match.
- Produce an ambiguous-match quarantine file.

---

# Step 7 — reconstruct roster spells and eligibility

Convert weekly roster observations into dated intervals.

Suggested roster_spell fields:

- player_id.
- season.
- team.
- start_week and end_week.
- effective dates.
- roster_status.
- listed_position.
- depth_position and its source version.
- practice-squad/reserve/injured status where provided.
- source snapshot.

Rules:

- A trade or waiver creates a new team spell.
- A roster-status change creates a new state within the same team spell.
- A player with multiple teams still has one league-wide player-season row later.
- Retain player-team-season rows for context.
- Do not treat a missing week as a release until source semantics have been verified.

Create a separate preseason forecast-eligibility table. It must be defined from information available at the chosen anchor, not from knowledge that the player later appeared.

---

# Step 8 — store every physical value as a dated measurement event

Do not place one supposedly timeless height or weight directly on the player table.

Suggested measurement_event fields:

- player_id.
- metric_code.
- raw value and unit.
- standardized value and unit.
- observed_at.
- date precision.
- available_at.
- source.
- protocol.
- test location.
- official/estimated/derived flag.
- reliability tier.
- source row ID and snapshot.

## Measurement families

### Broad-coverage measurements

- Height.
- Weight.
- Age at season anchor.
- Experience.

### Morphology enrichment

- Arm length.
- Hand size.
- Wingspan.
- Standing reach if ever verified.

### Speed, acceleration, and movement testing

- 40-yard dash.
- 10-yard split.
- Short shuttle.
- Three-cone.

### Power and strength

- Vertical jump.
- Broad jump.
- Bench press.

## As-of selection

For each player-season:

- Height/arm/hand/wingspan: select the highest-reliability adult value available before the anchor; retain measurement age.
- Weight: select the nearest reliable pre-anchor listing, preferably within 365 days.
- Combine/pro-day drill: retain the original test date, test age, protocol, and years since test.
- Never relabel an old combine result as a current-season physical ability.

## 2021 testing warning

The NFL did not conduct the normal centralized in-person workout combine in 2021; workouts occurred at college pro days. See the [NFL’s 2021 format notice](https://www.nfl.com/news/nfl-memo-details-different-format-for-combine-individual-workouts-will-be-held-o).

Record a protocol/source effect. Do not assume a 2021 pro-day time is directly interchangeable with a standardized Indianapolis result.

## Limb-length warning

Arm and hand measurements are available for a useful subset. Wingspan is much sparser. Leg length/inseam is not systematically published for NFL players.

- Leave unobserved limb fields null.
- Do not present height-derived leg length as a measurement.
- If a later model estimates a body proportion, label it explicitly as an estimate and keep it out of the raw measurement table.

---

# Step 9 — build a two-layer defensive role taxonomy

NFL listed positions are too crude for the final analysis, but public data cannot reliably identify every alignment. Use two layers.

## Layer 1: reliable broad role

Recommended v1 role families:

| Role | Typical source positions | Main opportunity types |
|---|---|---|
| EDGE | DE, pass-rushing OLB | Rush, run defense |
| Interior defensive line | DT, NT, interior DE | Interior rush, run defense |
| Off-ball linebacker | ILB, MLB, WLB, coverage OLB | Run, coverage, blitz |
| Cornerback | CB, DB | Coverage, run support, occasional blitz |
| Safety/hybrid | FS, SS, S, DB | Deep/box coverage, run support, blitz |

Use standardized listed position plus prior usage evidence. Store role_confidence and role_source.

## Layer 2: deployment/play-style archetype

Infer style from opportunity and deployment variables, not successful outcomes:

- Pass-rush involvement.
- Blitz frequency.
- Coverage-target exposure.
- Run/pass on-field exposure.
- Box count and personnel context.
- Tackle-location/context mix.
- Man/zone team context.

Possible enhanced archetypes:

- Pure edge rusher.
- Balanced edge.
- Interior penetrator.
- Interior run anchor.
- Coverage linebacker.
- Run-fit linebacker.
- Blitzing linebacker/hybrid.
- Coverage-heavy corner.
- Nickel/run-support defensive back.
- Deep-leaning safety.
- Box/blitz safety.

Important boundaries:

- Do not claim a clean outside-versus-slot CB label without valid alignment data.
- Do not claim box-versus-deep safety on every snap without alignment/tracking.
- An OLB may be EDGE or off-ball; listed position alone is not enough.
- Do not use sacks, interceptions, or tackles for loss to assign the role that will later be judged on those outcomes. That is circular.

For predictive modeling, use only lagged role shares or predict the role separately. Target-season observed role is leakage.

---

# Step 10 — build the player-play opportunity layer

The ideal row is one defender on one defensive play.

Suggested fields:

~~~text
game_id
play_id
season
week
defense_team
player_id
broad_role
role_confidence
defensive_snap
dropback
designed_run
scramble
down
distance
yardline
score_state
quarter
clock
offensive_personnel
defensive_personnel
formation
defenders_in_box
number_of_pass_rushers
man_zone
coverage_type
was_pressure
time_to_throw
offensive_epa
player_event_flags
participation_provider
definition_version
~~~

Construct this by exploding the participation defense-player list and joining to play-by-play.

Free-data limitations:

- Presence on a pass play is not proof of a coverage snap.
- Presence on a dropback is not proof of a pass-rush snap.
- The play-level pressure flag does not identify the individual responsible.
- Team coverage type does not reveal each defender’s assignment.

Therefore retain both:

1. Exact denominators where a source explicitly provides them.
2. Clearly named exposure proxies such as opponent dropbacks while on field.

Never label a proxy as an exact rush or coverage opportunity.

---

# Step 11 — create direct possession-change labels

## Interception

Credit the intercepting player. Also retain:

- Pressure status.
- Intended receiver and route if present.
- Man/zone and coverage family if present.
- Target depth.
- Return yards and touchdown separately.

An interception can result from pressure, a tipped ball, another defender’s coverage, or quarterback error. It is an observed outcome, not pure proof of individual anticipation.

## Forced fumble

Credit the player who forced the fumble.

Keep three variables separate:

- Forced fumble.
- Opponent fumble ultimately recovered by the defense.
- Player who recovered the ball.

Suggested labels:

~~~text
interception_created
forced_fumble_created
lost_fumble_created
defensive_recovery
direct_takeaway_created = interception_created + lost_fumble_created
~~~

A recovery is highly affected by ball location and teammate/opponent proximity. Do not weight recovery the same as causing the fumble.

## Defensive touchdown

Treat a return touchdown as downstream realization, not the underlying takeaway skill. Split:

- Turnover creation.
- Return value.

## Safety

A safety ends the drive and changes the subsequent possession structure, but it is best retained in the drive-ending domain rather than mixed blindly with interceptions and forced fumbles.

---

# Step 12 — construct the six main performance domains

Do not begin by hand-weighting one overall score. Build transparent components first.

## A. Direct takeaway creation

Candidate outputs:

~~~text
takeaways_created_per_1000_defensive_snaps
interceptions_per_100_targets
forced_fumbles_per_1000_defensive_snaps
lost_fumbles_created_per_1000_defensive_snaps
probability_of_at_least_one_direct_takeaway
~~~

Rare events need strong shrinkage and uncertainty intervals.

## B. Pass-rush disruption

Preferred metrics when valid denominators exist:

~~~text
pressure_rate = pressures / pass_rush_snaps
sack_rate = sacks / pass_rush_snaps
qb_hit_rate = non_sack_hits / pass_rush_snaps
forced_fumble_rush_rate = rush_forced_fumbles / pass_rush_snaps
pressure_to_sack_conversion = sacks / pressures
~~~

Public fallback:

~~~text
pressures_per_100_on_field_dropbacks
sacks_per_100_on_field_dropbacks
hits_per_100_on_field_dropbacks
~~~

Call these exposure rates, not true rush-win rates.

Pressure-to-sack conversion is secondary. It depends on quarterback style, time to throw, coverage, teammates, and random finishing variation.

Do not sum pressures, hurries, hits, and sacks unless the provider’s definitions prove those components are mutually exclusive.

## C. Coverage disruption

Candidate metrics:

~~~text
target_rate = targets / estimated_coverage_or_pass_exposure
completion_rate_allowed = completions / targets
ball_disruption_rate = passes_defended_or_broken_up / targets
interception_rate = interceptions / targets
yards_per_target_allowed
touchdown_rate_allowed
yac_per_completion_allowed
explosive_completion_rate_allowed
~~~

First audit whether passes_defended includes interceptions. Do not double-count.

Low target volume is ambiguous. It may reflect good coverage, a low-volume assignment, scheme protection, or a weak opposing receiver. Target avoidance must be interpreted with context.

Later build expected-completion and expected-yards models using:

- Target depth.
- Route.
- Quarterback and receiver.
- Down/distance.
- Score and field position.
- Pressure.
- Man/zone and coverage family.
- Defender role.
- Team-season scheme.

Label public coverage responsibility as a noisy provider assignment. The free historical data do not identify exact responsibility on every target.

## D. Run disruption

Create run-defense exposure from designed non-scramble runs while the defender is on field.

Candidate definitions:

~~~text
stuff = credited tackle on a run gaining zero or negative yards

down_distance_stop =
  first down gain <= 45 percent of yards to go
  second down gain <= 60 percent of yards to go
  third/fourth down gain < 100 percent of yards to go

run_stop_rate = credited_run_stops / run_defense_exposure
run_tfl_rate = run_tackles_for_loss / run_defense_exposure
~~~

For assisted tackles:

- Use fractional credit that sums to one; or
- Keep solo and assisted stops as separate features.

Do not award a full stop to every credited assister.

On-field run EPA is a team/context signal, not proof that one player created the whole value. Use multilevel adjustment and describe it as association.

## E. Tackle reliability

Candidate metrics:

~~~text
tackle_attempts = credited_tackles + missed_tackles
missed_tackle_rate = missed_tackles / tackle_attempts
tackle_completion_rate = credited_tackles / tackle_attempts
solo_tackle_share = solo / (solo + assists)
zero_or_negative_gain_tackle_share
~~~

Split by run/pass and gain context where possible.

Raw tackle volume is not inherently positive. A safety can accumulate tackles because runners and receivers repeatedly reach the second level.

## F. Decision cost and discipline

Use accepted, player-attributed defensive penalties:

~~~text
penalties_per_1000_snaps
penalty_yards_per_1000_snaps
automatic_first_down_penalties_per_1000_snaps
penalty_epa_cost_per_1000_snaps
~~~

Separate:

- Defensive pass interference.
- Holding.
- Illegal contact.
- Offside/neutral-zone infractions.
- Roughing the passer.
- Face-mask, horse-collar, and unnecessary roughness.

Exclude declined and offsetting penalties from realized cost.

Keep penalty cost, missed-tackle cost, and coverage-explosive cost visible rather than burying them in one opaque negative score.

---

# Step 13 — build drive-ending and situational value

This domain connects disruption to possession without pretending every event is a turnover.

Candidate directly attributable events:

- Interceptions.
- Forced fumbles that become defensive recoveries.
- Third- or fourth-down sacks.
- Third- or fourth-down passes defended that cause incompletion.
- Credited fourth-down run stops short of the line to gain.
- Safeties.

Create:

~~~text
drive_ending_disruptions_per_100_defensive_drives
third_down_disruption_rate
fourth_down_stop_rate
high_leverage_disruption_rate
~~~

Do not credit a third-down tackle if the offense already converted.

## EPA handling

Use:

~~~text
defensive_epa = -offensive_epa
~~~

But do not give one defender the entire EPA of a play merely because the defender was on the field.

For turnovers, separate creation value at the turnover spot from return value when the data allow it. The interceptor or forcing defender created the possession event; return yards may come from a different player and team blocking.

## Leverage

Do not weight events by realized WPA, because the realized outcome helps define that weight. Estimate pre-play leverage from game state, then compare weighted and unweighted rates.

---

# Step 14 — define role-specific scorecards

The evidence that matters differs by role.

## EDGE

- Adjusted pressure/exposure rate.
- Sack and quarterback-hit rates.
- Forced fumbles.
- Run stops and TFLs.
- Batted passes if consistently available.
- Offside and roughing-the-passer cost.

## Interior defensive line

- Interior pressure proxy.
- Quarterback hits and sacks.
- Batted passes.
- Stuff and run-stop rate.
- Run TFL rate.
- Forced fumbles.
- Missed-tackle rate.

Important blind spot: free public data do not capture double-team absorption, gap occupation, or block control well. Nose tackles will be undervalued if the model relies only on credited events.

## Off-ball linebacker

- Run-stop/TFL rate.
- Forced fumbles.
- Blitz pressure.
- Target and coverage outcomes.
- Ball disruption.
- Missed-tackle rate.
- Penalty cost.

## Cornerback

- Target exposure.
- Completion and yards per target allowed.
- Ball disruption and interceptions per target.
- Explosive plays and touchdowns allowed.
- Defensive pass-interference/holding cost.
- Missed tackles after completions.

## Safety/hybrid

- Target and ball-disruption outcomes.
- Interceptions.
- Explosives/TDs allowed.
- Run stops.
- Blitz pressure.
- Tackle reliability.
- Penalty cost.

Do not compare a nose tackle’s interception rate with a cornerback’s, or a cornerback’s pressure volume with an edge rusher’s. Normalize within season and defensible role family.

---

# Step 15 — engineer physical and movement features

Retain all raw measures and publish formulas for derived features.

## Core physical features

- Height.
- Weight.
- Age at season start.
- Years of NFL experience.
- Size residual relative to role rather than BMI alone.

## Reach/morphology features

- Arm length.
- Hand size.
- Wingspan.
- Wingspan-to-height ratio where both are observed.
- Role/cohort residuals for arm or wingspan after accounting for height.

## Speed, burst, and agility

- 40-yard time.
- 10-yard split.
- Short shuttle.
- Three-cone.
- Vertical.
- Broad jump.
- Bench press.

Recommended construction:

- Convert direction so higher always means more favorable only in the feature layer.
- Standardize within entry cohort and broad role.
- Use a speed factor from correlated sprint fields.
- Use a burst factor from vertical and broad jump.
- Use an agility factor from shuttle and cone.
- Retain test age, protocol, and years since measurement beside every factor.

Avoid pretending that combine speed equals current in-game speed. The NFL records real movement data, but a complete free five-season feed is not available.

## Missing testing

Missing combine data are not random. Preserve:

- Not eligible.
- Not invited.
- Invited but did not test.
- Injury/partial testing.
- Pro-day only.
- Source unavailable.
- Structurally unavailable.

Never replace a missing drill with zero.

Maintain two model tiers:

1. Core full-roster tier: age, height, weight, broad role, and high-coverage fields.
2. Enhanced measured-athlete tier: limb measures and testing.

Report performance separately by measurement-coverage tier.

---

# Step 16 — engineer behavioral proxies carefully

The project may eventually include “awareness,” “reaction,” or “decision speed,” but box-score data do not measure mental traits directly.

Use names such as:

- Anticipation behavior proxy.
- Closing/disruption proxy.
- Decision-discipline proxy.
- Spatial-versatility proxy.
- Recovery/tackle-reliability proxy.

Possible public-data proxies:

| Intended idea | Observable proxy | Main caveat |
|---|---|---|
| Anticipation | Role-adjusted INT/PBU per target, route/depth/context adjusted | Interceptions reflect pressure, QB error, and teammates |
| Reaction/closing | Quick pressure where timing exists; early run stop; YAC suppression | Full timing and movement are not public for all games |
| Spatial awareness | Explosive-play suppression, target avoidance with context, role versatility | Assignment and safety help are incompletely observed |
| Decision quality | Penalty EPA, missed tackles, TD/explosive cost | Aggressive roles have different risk profiles |
| Adaptability | Entropy of reliable prior role shares | Requires valid deployment labels |

Do not name a score “reaction time” unless it comes from a timed test or tracking measurement. Do not name a score “awareness” as if it were a psychological measurement.

Coach/scout ratings can be added later as a separate source:

- Use a defined rubric.
- Obtain repeated raters where possible.
- Measure inter-rater reliability.
- Keep subjective ratings separate from game-derived evidence.
- Record whether the coach knew the player outcome, to manage hindsight bias.

---

# Step 17 — aggregate to player-game and player-season tables

Keep fine-grained data, but use a stable player-season row for most modeling.

Recommended tables:

| Table | Grain |
|---|---|
| player | One internal athlete |
| player_identity | Source ID × athlete |
| roster_spell | Player × team × interval |
| game | One game |
| player_game | Player × game × team |
| player_game_metric | Player × game × metric definition |
| player_game_opportunity | Player × game × opportunity |
| measurement_event | Player × measurement × date × source |
| player_team_season | Player × team stint × season |
| player_season_role | Player × season × role |
| player_season | Player × season |
| player_feature | Player × anchor date × feature version |

For traded players:

- Retain every team stint.
- Build one league-wide player-season outcome.
- Weight contextual team variables by actual exposure.
- Do not count the athlete twice in league-wide clustering.

Store:

- Raw totals.
- Exact and proxy denominators.
- Raw rates.
- Shrunken rates.
- Role-season z-scores and percentiles.
- Missingness/coverage flags.
- Source and definition versions.

---

# Step 18 — run quality assurance before feature engineering

## File/schema QA

- Expected files exist for 2021–2025.
- Hashes and row counts recorded.
- Required columns present.
- Type changes detected.
- Duplicate raw rows reported.

## Schedule/game QA

- Every performance game maps to the schedule.
- Regular/postseason correctly separated.
- Cancelled/no-contest games handled from schedule status.
- Team abbreviations normalized.

## Identity QA

- GSIS, PFR, and SMART ID mappings are unique where expected.
- Unmatched source players reported by season and role.
- Name and birth-date conflicts quarantined.

## Roster QA

- Unique player-team-week records.
- Roster counts by team/week inspected.
- Zero-appearance rostered players retained.
- Trades and status changes produce valid spells.

## Snap/opportunity QA

- Player defensive snaps do not exceed team defensive plays without an explained source issue.
- Team/game defensive snap totals broadly reconcile.
- Participation defender counts are plausible.
- On-field dropbacks and runs are nonnegative and do not exceed team play counts.

## Event QA

- Season totals for sacks, interceptions, forced fumbles, TFLs, and passes defended reconcile to a designated validation source within explained differences.
- Half-sacks and assisted tackles use explicit fractional/full-credit rules.
- Fumble forcer and recoverer are not conflated.
- Penalties exclude declined/offsetting events from realized cost.

## Advanced-stat QA

- Pressure components checked for overlap.
- Passes-defended definition checked for whether interceptions are included.
- Targets and completions have valid denominators.
- Missed-tackle values and percentages reconcile where possible.

## Physical QA

- Units normalized.
- Height/weight and drill values fall within defensible bounds.
- Conflicting measurements retained and flagged, not overwritten.
- Measurement dates precede prediction anchors.
- 2021 pro-day protocol flagged.

## Provider-break QA

- Compare field availability and distributions for 2021–22 NGS participation versus 2023–25 FTN participation.
- Version fields whose definitions or population change.
- Run models with and without participation-era features.

Publish a QA report before any final archetype or rank is produced.

---

# Step 19 — shrink noisy rates before ranking players

Interceptions, forced fumbles, sacks, and passes defended are noisy at low opportunity.

Use one of:

- Empirical-Bayes beta-binomial shrinkage for success/opportunity rates.
- Gamma-Poisson or negative-binomial hierarchical models for counts with exposure offsets.
- Multilevel generalized models with season, role, team, and player effects.

The displayed estimate should include:

- Raw numerator.
- Opportunity denominator.
- Raw rate.
- Shrunken estimate.
- Uncertainty interval.
- Role-season percentile.

Do not rank a defender with 40 snaps above a durable 900-snap player solely because of a volatile raw rate.

---

# Step 20 — discover physical archetypes

Physical archetypes answer:

> What kinds of bodies and tested athletic profiles exist within NFL defensive roles?

Procedure:

1. Use one row per athlete, or weight each athlete inversely by career-season count.
2. Select the best pre-entry/adult measurements with protocol and staleness fields.
3. Fit imputation only inside the development sample.
4. Include missingness indicators.
5. Standardize by role and entry cohort where appropriate.
6. Reduce highly correlated drill variables using PCA or factor analysis.
7. Compare k-means, Gaussian mixtures, and a medoid/density alternative.
8. Evaluate bootstrap stability, assignment entropy, separation, and football interpretability.
9. If clusters are unstable, publish continuous axes instead.
10. Name archetypes after examining medoids and feature profiles.

Potential axes:

- Size/reach.
- Straight-line speed.
- Acceleration.
- Burst/power.
- Change of direction.
- Strength.

Do not bake performance into the physical clusters. Performance is overlaid later to learn which builds succeed in which roles.

---

# Step 21 — discover play-style archetypes

Play-style archetypes answer:

> How does a defender tend to create disruption when deployed?

Use opportunity and action mix, preferably after shrinkage:

- Rush versus coverage versus run-defense exposure.
- Pressure/hit/sack mix.
- Target and ball-disruption activity.
- TFL/run-stop/tackle activity.
- Blitz activity.
- Direct-takeaway mix.
- Penalty and missed-tackle behavior.
- Team man/zone, box, personnel, and rush-count context.

Procedure:

1. Require a reliability threshold for fitting clusters, but retain low-snap players for probabilistic assignment.
2. Convert raw counts into valid opportunity-normalized features.
3. Standardize within season × broad role.
4. Keep the successful outcome used to judge clusters outside the cluster construction where possible.
5. Fit PCA/factor axes for correlated behavior.
6. Compare stable clustering approaches.
7. Use UMAP only as a visualization, not proof of real discrete groups.
8. Track probabilistic archetype membership by season.
9. Allow players to change style over time.

Cross-tab:

> physical archetype × play-style archetype × role-relative effectiveness

This is the cleanest answer to “which builds tend to become which kinds of possession/disruption players?”

---

# Step 22 — build the descriptive NFL scorecard

For every player-season-role row, publish:

- Availability/defensive snap volume.
- Direct-takeaway estimate.
- Pass-rush disruption.
- Coverage disruption.
- Run disruption.
- Tackle reliability.
- Drive-ending value.
- Decision efficiency.
- Physical archetype probabilities.
- Play-style archetype probabilities.
- Raw evidence and opportunity beneath each score.
- Data coverage and uncertainty.

Normalize component scores within:

~~~text
season × broad role
~~~

Do not immediately average them. If a summary is useful, provide:

1. An equal-weight transparent composite.
2. A learned outcome-predictive composite.
3. The component radar/table beside either composite.

Weights learned from data must be fitted only on training seasons and frozen before the final test.

---

# Step 23 — model availability, opportunity, and effectiveness separately

A useful future contribution model is:

~~~text
expected_contribution
  = probability_of_availability
  × expected_defensive_opportunity
  × role_adjusted_effectiveness
~~~

## Availability model

Targets may include:

- On an NFL roster at the chosen future checkpoint.
- Appears in at least one game.
- Records at least a defined defensive-snap threshold.

Candidate models:

- Logistic regression/elastic net baseline.
- Survival or discrete-time hazard model for roster exit.
- Gradient-boosted classifier as challenger.

## Opportunity model

Targets:

- Games active.
- Defensive snaps.
- Role share.

Candidate models:

- Hurdle model: any snaps, then conditional snap volume.
- Negative binomial/Tweedie count model.
- Gradient boosting as challenger.

## Effectiveness models

Fit role-specific or hierarchical component models:

- Negative binomial for counts with log opportunity offset.
- Binomial/beta-binomial for success/opportunity outcomes.
- Elastic net or GAM for interpretable nonlinear age/size effects.
- Gradient-boosted trees as a nonlinear challenger.
- Ridge adjusted plus-minus for on-field EPA/drive suppression, heavily regularized and presented as association.

One flat model should not assume the same feature effects for a corner and a nose tackle.

---

# Step 24 — create leakage-safe temporal features

For target season t, permit only information available before the chosen t anchor:

- Previous-season component estimates.
- Two- or three-season exponentially weighted averages.
- Trend/slope.
- Between-week consistency.
- Prior snap volume and role shares.
- Past availability/injury information known by the anchor.
- Age and experience.
- As-of physical/test measurements and measurement staleness.
- Past-only, leave-player-out team/context aggregates.

Prohibited:

- Target-season depth chart after the anchor.
- Target-season role learned from the completed season.
- Target-season injury outcome.
- Target-season games, snaps, stats, team results, or late roster status.
- Physical listings first published after the anchor.

Build two forecast variants:

1. Portable player model: no destination-team/scheme inputs.
2. Deployment-aware model: adds pre-anchor team/coordinator/context.

The portable version is more useful for identifying league-wide role fit. The deployment-aware version may forecast actual next-season production better.

---

# Step 25 — use temporal validation, not random rows

Recommended split:

- Create target-2022 rows using only information through 2021.
- Create target-2023 rows using only information through 2022.
- Use these development rows for initial fitting and internal time-aware resampling.
- Use 2024 for model/feature/threshold selection.
- Freeze the complete design.
- Retrain through 2024 where allowed.
- Evaluate once on untouched 2025.

The same returning athlete may appear in earlier training seasons and the later test because that matches the returning-player use case. However:

- Never random-split player-season rows.
- Use player-clustered bootstrap confidence intervals.
- Add a held-out-player evaluation to show how much performance depends on prior NFL history.
- Keep entire players and entry cohorts outside training for cold-start evaluation.

Baselines every complex model must beat:

- Role-season mean.
- Prior-season value.
- Two-/three-year exponentially weighted average.
- Age + role + prior snaps.

Metrics:

- Availability: Brier, log loss, PR-AUC, AUROC, calibration.
- Opportunity: MAE, RMSE, interval coverage.
- Counts/rates: deviance, MAE, Spearman rank correlation.
- Ranking: precision@K, recall@K, NDCG.
- Top-quartile classification: precision, recall, Brier, calibration.
- Uncertainty: empirical interval coverage and width.

Report by:

- Role.
- Age and experience.
- Prior-snap band.
- Team change.
- Measurement coverage tier.
- Participation-provider era.
- Missing-data status.

---

# Step 26 — build the hidden-value screen prospectively

Do not define hidden value after seeing who broke out.

Possible flags:

- Under-deployed: high forecast relative to prior snaps/depth opportunity.
- Low-total/high-rate: strong shrunken efficiency hidden by limited exposure.
- Context-suppressed: adjusted estimate materially better than raw team result.
- Adjacent-role match: physical/play-style profile resembles a successful nearby role.
- Contract value: expected contribution relative to cap cost, only after contract data are added.

A candidate should normally require:

- Validation-selected probability of top-quartile role effectiveness.
- Lower uncertainty bound near or above role average.
- Meaningful positive deployment/market residual.
- Sufficient data coverage.
- No severe out-of-distribution warning.
- Availability risk explicitly considered.

Backtest:

1. Use only information available before 2024 to flag 2024 candidates.
2. Test whether they gained opportunity or produced strong 2024 role-adjusted outcomes.
3. Freeze the rule.
4. Apply it to the 2025 holdout.
5. Compare with matched controls of similar age, role, prior opportunity, and availability risk.

Do not call every injured, low-snap, high-rate player a bargain.

---

# Step 27 — build the physical-only cold-start model

## Core tier

- Age at entry.
- Height.
- Weight.
- High-coverage body fields.

## Enhanced tier

- Arm, hand, and wingspan where observed.
- 40 and 10 split.
- Vertical and broad.
- Shuttle and three-cone.
- Bench.
- Protocol, source, test age, and staleness.

Exclude from a truly physical-only contract:

- NFL performance history.
- College production.
- Draft round.
- Salary.
- Destination team.
- Target-season depth chart.

If the purpose is to infer role from build, college/listed position should be a comparison benchmark, not an input that makes the answer circular.

Use historical entry cohorts, ideally 2010 onward:

- Hold out complete draft/entry cohorts.
- Keep every season belonging to a held-out athlete outside training.
- Predict predefined early-career opportunity/effectiveness thresholds only for actual football entrants.

For outside-sport athletes, output:

- NFL role similarity percentile.
- Nearest physical archetypes.
- Nearest successful comparables with clear caveats.
- Measurement coverage.
- Uncertainty.
- Out-of-distribution warning.

Suppress “probability of NFL success” for cross-sport athletes unless a defensible transition dataset is later assembled.

---

# Step 28 — quantify uncertainty and extrapolation

Every model-facing player output should include:

- Point estimate.
- Confidence or predictive interval.
- Sample opportunity.
- Data-coverage tier.
- Measurement staleness.
- Provider/definition era.
- Out-of-distribution flag.

Recommended methods:

- Hierarchical/empirical-Bayes shrinkage.
- Player-clustered bootstrap.
- Team/game blocks as sensitivity analysis for play-level models.
- Time-ordered probability calibration.
- Temporal conformal intervals using 2024 residuals for 2025 where sample size permits.
- Cluster membership probabilities rather than forced labels.
- Robust within-role distance or isolation methods for physical OOD detection.

An honest wide interval is more useful than a precise-looking rank based on four targets or 80 snaps.

---

# Step 29 — encode leakage and definition tests

Automated tests should fail the build if:

- Any feature has observed_at or available_at after its forecast anchor.
- A 2025 feature uses 2025 games, snaps, performance, injury outcome, or completed-season role.
- A target-season minimum-snap filter removes zero-opportunity forecast cases.
- Target-season depth chart appears in a predictive matrix.
- Player IDs are ordinary numeric/categorical predictors rather than join/group keys or explicit random effects.
- Scaling, imputation, PCA, feature selection, clustering, or calibration was fitted outside the training fold.
- Team/context features include the focal player or future information.
- An adjusted-impact predictor was estimated using the target season.
- A pressure total and its overlapping components are double-counted.
- A raw zero is substituted for missing/not-applicable data.
- Participation providers or metric definitions are pooled without a version field.
- The 2025 test is opened before the 2024 design is frozen.

---

# Step 30 — freeze the cross-sport output contract

Later sports should share meanings, not raw NFL units.

Suggested output fields:

- sport, season, as_of_date, role_id, model_version, and data_tier.
- Availability probability.
- Expected opportunity percentile.
- Direct possession-win percentile.
- Disruption/pressure percentile.
- Anticipation/interception-behavior percentile.
- Recovery/tackle percentile.
- Suppression/contest percentile.
- Range/mobility percentile.
- Decision-efficiency percentile.
- Expected-contribution percentile.
- Physical archetype probabilities.
- Play-style archetype probabilities.
- Role-fit percentile.
- Raw sport-specific evidence.
- Uncertainty, coverage, staleness, and OOD flags.

All percentiles should be calibrated within sport × season × role. Do not pool raw NFL interceptions, NBA steals, NHL takeaways, and soccer tackles.

The cross-sport model can later share a physical representation, with separate sport-role prediction heads. Each sport-specific model should first translate its native evidence into the common dimensions.

---

# Recommended implementation sequence

## Gate 1 — definitions

- Approve the broad NFL role ontology.
- Approve the six performance domains and drive-ending layer.
- Freeze direct takeaway versus disruption terminology.
- Choose regular-season-only v1.

## Gate 2 — raw collection

- Download and hash 2021–2025 rosters, player stats, snaps, advanced defense, schedules, PBP, and participation.
- Download the player crosswalk and combine file.
- Register licenses, attribution, providers, and field definitions.

## Gate 3 — identity and roster foundation

- Resolve GSIS/PFR/SMART IDs.
- Build weekly roster spells.
- Create the all-rostered-player universe.
- Produce unmatched/ambiguous reports.

## Gate 4 — aggregate MVP

Use:

- Weekly rosters.
- Weekly player stats.
- Snap counts.
- Advanced defense.
- Combine/physical measurements.

Produce:

- Player-team-season and player-season tables.
- Broad roles.
- Per-snap/per-target component rates.
- Missingness report.
- Role-season shrunken scores.
- First physical and play-style archetypes.

This MVP can answer a large portion of the project before the more complex player-play layer exists.

## Gate 5 — contextual v2

Add:

- Play-by-play.
- Participation.
- On-field run/dropback exposures.
- EPA, down/distance, game state, personnel, coverage, box, and rush-count context.
- Drive-ending and leverage features.
- Provider-break sensitivity models.

## Gate 6 — models

- Fit availability, opportunity, and effectiveness baselines.
- Fit interpretable elastic-net/GAM/hierarchical models.
- Add nonlinear challengers only if they beat the baselines on 2024.
- Freeze 2024 selections.
- Evaluate 2025 once.

## Gate 7 — hidden value and cold start

- Backtest hidden-value flags prospectively.
- Extend historical combine/entry cohorts.
- Fit core and enhanced physical-only models.
- Add salary/market data only after talent estimates are frozen.

## Gate 8 — application

For any player, show:

- Broad role and role confidence.
- Physical and play-style archetype probabilities.
- Component percentiles with raw evidence.
- Expected availability/opportunity/contribution.
- Nearest relevant comparables.
- Data coverage and measurement dates.
- Uncertainty and OOD warnings.
- Why the model reached the result.

---

# Recommended first practical model

Keep v1 intentionally modest:

1. Broad-role assignment with confidence.
2. Role-season empirical-Bayes component rates.
3. Separate physical and play-style archetypes.
4. Three-year exponentially weighted features.
5. Elastic-net or hierarchical forecasts for availability, opportunity, and each effectiveness component.
6. 2024 model selection.
7. One untouched 2025 evaluation.

Only add boosted trees, complex adjusted plus-minus, or tracking-inspired features after this system beats persistence and role-average baselines.

---

# What the final NFL result should sound like

A useful result:

> This defender resembles a high-burst, long-lever EDGE archetype. His shrunken pressure exposure and run-disruption estimates are above the role average, his direct takeaway estimate remains uncertain, and his penalty cost is elevated. Based on pre-2025 information, the model projected above-average per-opportunity disruption but only moderate expected contribution because of availability and snap uncertainty.

An overclaim:

> This is the ideal possession-winning athlete and his reaction speed is elite.

The first statement exposes role, evidence, uncertainty, and the difference between efficiency and opportunity. The second claims mental and movement traits that the public data did not directly measure.

---

# Immediate next build

The next concrete deliverable should be an NFL collection manifest and data dictionary containing:

- Every 2021–2025 source file.
- Expected key, grain, columns, phase, provider, and definition version.
- Exact destination path and snapshot hash.
- Join route to GSIS ID.
- Coverage and missingness checks.
- License/attribution note.
- Bronze-to-silver transformation.
- QA acceptance rule.

After that manifest is approved, implement the aggregate MVP before attempting the full player-play context model.
