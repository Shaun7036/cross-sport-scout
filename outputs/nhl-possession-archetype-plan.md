# NHL puck-winning and defensive-disruption archetype plan

Prepared 1 October 2026

This plan was prepared after an ambiguous reference to “NHL” and is retained as a future-sport reference. The active first-sport workflow is the [NFL possession-creation and defensive-disruption archetype plan](nfl-possession-archetype-plan.md). This document still provides the eventual NHL-specific workflow covering data collection, player roles, measurements, feature engineering, archetypes, forecasting, hidden-value screening, and the later cross-sport handoff.

## The NHL objective

Build a five-season panel that can answer four different questions:

1. **Descriptive:** Which physical and play-style archetypes have produced strong puck-winning and defensive outcomes?
2. **Predictive:** Using information known before a season, which returning players are likely to provide possession-related value?
3. **Hidden value:** Which players appear effective after context adjustment but receive relatively little opportunity?
4. **Cold-start role fit:** Which NHL roles does a prospect or outside-sport athlete physically resemble?

Do not call every defensive action a possession win:

- A credited takeaway and a faceoff win are direct puck acquisitions.
- A hit or block is an intervention, not automatically a change of possession.
- Low expected goals against reflects the player, teammates, opponents, deployment, system, and goaltending.
- Board battles, loose-puck recoveries, forecheck pressure, controlled exits, and entry denials are not comprehensively recorded in free public NHL data.

The initial construct should therefore be called **puck acquisition and defensive disruption**.

---

# Step 1 — freeze the scope

## Seasons

Use:

- 2021–22
- 2022–23
- 2023–24
- 2024–25
- 2025–26

Source season IDs:

~~~text
20212022
20222023
20232024
20242025
20252026
~~~

This window begins when NHL EDGE player/puck tracking became fully operational league-wide. The NHL states that its public tracking history begins in 2021–22. [NHL EDGE coverage](https://www.nhl.com/news/nhl-edge-launches-website-for-puck-and-player-tracking-data)

## Competition phase

Start with regular seasons only:

- Official game type: 2.
- Keep playoffs separate rather than mixing them into regular-season rates.
- Add playoff models later if useful; role, opponent quality, and deployment change substantially in the postseason.

## Player universe

- Include every rostered skater where the source permits.
- Retain skaters with zero appearances.
- Exclude goalies from the first possession-archetype model, but keep them in the roster universe.
- Treat goalies as a separate later project because their physical profiles, opportunities, and puck-possession actions are fundamentally different.

## Outputs

Produce:

- A completed-season descriptive archetype table.
- A leakage-safe returning-player forecast.
- A hidden-value candidate table.
- A physical-only role-similarity table.
- Component scores and uncertainty—not only a single composite.

---

# Step 2 — define what the model is measuring

Keep seven domains separate initially.

| Domain | Public evidence | Main limitation |
|---|---|---|
| Direct acquisition | Takeaways and faceoff wins | Takeaways are scorer-dependent; faceoffs apply mainly to centers |
| Forecheck/pressure | Offensive-zone takeaways and event-sequence proxies | Public data does not identify every pressure or forced giveaway |
| Shot suppression | CA, FA, SA, xGA, high-danger chances against | Strongly affected by team, linemates, opponents, zone and score |
| Physical intervention | Blocks and hits | Neither guarantees possession was won |
| Puck security | Giveaways and defensive-zone giveaways | Crediting is subjective and opportunity differs by role |
| Discipline | Penalties taken/drawn and expected penalty cost | Penalty minutes combine very different events |
| Movement/range | EDGE speed bursts, maximum speed and distance | Does not directly measure reaction time or agility |

Only create an overall index after each component has demonstrated reasonable year-to-year stability and out-of-season predictive value.

---

# Step 3 — establish role families

Do not compare all skaters with one standard. First separate forwards and defensemen. Infer finer roles from deployment, not from the outcomes being evaluated.

Useful deployment inputs:

- Listed position.
- Faceoffs taken per 60.
- Even-strength, power-play, and penalty-kill TOI shares.
- Defensive-zone and offensive-zone start shares.
- Average shift length.
- TOI per game.
- Common line/pairing usage.
- Teammate and opponent quality where available.

## Centers

| Initial role | Typical deployment |
|---|---|
| Defensive/restart center | High faceoff volume, defensive-zone draws, PK time |
| Forechecking/two-way center | Balanced deployment and substantial 5v5 workload |
| Matchup/shutdown center | Defensive deployment against stronger opponents |

## Wingers

| Initial role | Typical deployment |
|---|---|
| Pressure/puck-hound winger | Forechecking workload, offensive-zone pressure |
| Speed/pursuit winger | High EDGE speed/burst workload |
| Defensive/matchup winger | PK time, defensive deployment, difficult opponents |

## Defensemen

| Initial role | Typical deployment |
|---|---|
| Gap/step-up defenseman | High 5v5 workload and difficult matchups |
| Shutdown/net-front defenseman | Defensive-zone and PK usage |
| Mobile retrieval/transition defenseman | Strong skating profile and puck-moving deployment |

The mobile retrieval role will remain partially proxy-based until valid entry/exit/retrieval microdata is licensed or manually tagged.

For a descriptive season, that season's deployment can define the role. For a preseason forecast, use only the previous role or predict the coming role separately.

---

# Step 4 — create a source registry before downloading

Create one row per source with:

- Publisher and dataset.
- URL or endpoint pattern.
- Seasons and game types.
- Update/revision behavior.
- Access date.
- License/terms URL.
- Attribution.
- Automation, redistribution, model-training, and commercial restrictions.
- Canonical ID.
- Expected fields and known gaps.

## Primary sources

| Source | Purpose | Status |
|---|---|---|
| Official NHL Stats reports | Bios, takeaways, giveaways, hits, blocks, faceoffs, penalties, on-ice reports | Official infrastructure but undocumented API; cache and use conservatively |
| Official NHL Web API | Rosters, schedules, play-by-play, player profiles and roster spots | Official infrastructure but unsupported as a public developer API |
| NHL EDGE | Maximum speed, burst bands, distance, shot speed and zone time | Curated player-season tracking summaries; no raw XY tracking |
| MoneyPuck | Bulk player/game/shot data, Corsi/Fenwick, xG and danger context | Free for noncommercial use with attribution |
| NHL Combine records | Sparse agility, power, strength, aerobic and wingspan enrichment | Leaderboards/top results only; highly selected |

[NHL terms](https://www.nhl.com/info/terms-of-service) limit unauthorized automated compilation and generally restrict NHL content to personal/informational/noncommercial use. [MoneyPuck](https://www.moneypuck.com/data.htm) permits its designated downloads for noncommercial use with credit and asks users not to scrape unlisted content.

For a public or commercial product, resolve permissions before treating these feeds as production assets.

---

# Step 5 — establish the canonical data model

## Core tables

### player

- Internal player UUID.
- Canonical name and DOB.
- Nationality.
- NHL player ID as the primary NHL source ID.

Do not put height or weight here; physical values belong in dated measurement records.

### player_identity

- Internal player UUID.
- Source.
- Source player ID.
- Valid dates.
- Match method/confidence.
- Manual-review flag.

### team and team_season

Use stable IDs rather than team names or abbreviations. This protects the panel from franchise/name changes.

### roster_spell

- Player, team and season.
- Effective start/end.
- Active, injured, reserve, scratched, called-up, or other status when known.
- Listed position.
- Source coverage status.

### game

- NHL game ID.
- Season, date, phase and teams.
- Home/away.

### player_game

- Player, game and team.
- Dressed/appeared status.
- Position.
- TOI and shifts by strength state when available.

### player_game_metric

Long-form metrics:

- Player/game/metric/definition version.
- Value/unit.
- Strength state.
- Source.
- Confirmed zero, missing, estimated, or not-applicable status.

### measurement_event

- Player and measurement type.
- Raw value/unit and standardized value.
- Observation date and precision.
- Publication/availability date.
- Protocol: roster listing, combine, fitness test, or tracking.
- Reliability tier and source.

### player_team_season and player_season

Retain team-stint rows for traded players, then create one league-wide player-season row using exposure-weighted context.

### source_snapshot

- Exact URL/query.
- Retrieval timestamp.
- File hash.
- Source/schema version.
- Raw row count.

---

# Step 6 — collect the roster and identity universe

## Season and team registry

Pull official season metadata:

~~~text
https://api.nhle.com/stats/rest/en/season
~~~

It supplies season dates and expected game counts. Enumerate each season's teams from standings on its final regular-season date:

~~~text
https://api-web.nhle.com/v1/standings/{YYYY-MM-DD}
~~~

Retain team IDs from schedules/games. Do not use abbreviations as durable keys because the Arizona/Utah identity changes inside this window.

## Official season reports

For every season ID, pull the skater bios report:

~~~text
https://api.nhle.com/stats/rest/en/skater/bios
  ?isAggregate=true
  &isGame=false
  &limit=-1
  &cayenneExp=seasonId={SEASON_ID} and gameTypeId=2
~~~

Fields include NHL player ID, height, weight, DOB, position, shooting side, nationality, draft information, and games played.

## Team roster snapshots

~~~text
https://api-web.nhle.com/v1/roster/{TEAM}/{SEASON_ID}
~~~

## Player profiles

~~~text
https://api-web.nhle.com/v1/player/{PLAYER_ID}/landing
~~~

## Game roster spots

Every game play-by-play response contains roster spots. Union these across all games to capture every skater who dressed.

## Opening-day lists

Add official opening-day roster releases for players who were rostered but did not immediately dress.

## Coverage caveat

The public sources do not provide a perfect historical ledger of every healthy scratch, injured-list spell, and zero-game call-up. Preserve:

- roster_source;
- roster_coverage_status;
- first/last confirmed date;
- dressed_game_count;
- whether the player came only from a snapshot or official release.

Do not convert “not observed in a game” into “not rostered.”

---

# Step 7 — collect physical and movement data

## Listed measurements

Convert height and weight to standard units, retaining:

- Original value and units.
- Source season.
- Observation/publication date precision.
- Whether the value changed from the previous listing.

Adult height differences are usually source/listing noise. Weight may change but may also be stale.

## NHL EDGE

For each player-season:

~~~text
https://api-web.nhle.com/v1/edge/skater-detail/{PLAYER_ID}/{SEASON_ID}/2
https://api-web.nhle.com/v1/edge/skater-skating-speed-detail/{PLAYER_ID}/{SEASON_ID}/2
https://api-web.nhle.com/v1/edge/skater-skating-distance-detail/{PLAYER_ID}/{SEASON_ID}/2
https://api-web.nhle.com/v1/edge/skater-comparison/{PLAYER_ID}/{SEASON_ID}/2
~~~

Store:

- Maximum skating speed.
- Bursts above 22 mph.
- Bursts from 20–22 mph.
- Bursts from 18–20 mph.
- Total distance.
- Distance per 60.
- Maximum single-game/period distance.
- Maximum and average shot speed.
- Zone-time and comparison percentiles.

Interpretation:

- Maximum speed is a peak/extreme, not general pace.
- Bursts per 60 measure repeat high-speed activity more reliably.
- Bursts per mile distinguish intensity from total workload.
- Distance per 60 reflects role and team system as well as fitness.
- Zone time means where the puck was while the player was on ice; it is not that player's possession time.
- EDGE does not publicly supply acceleration, change of direction, reaction latency, or raw trajectories.

EDGE has no supported bulk export. Build a cached player-season queue, record non-success responses, throttle requests, and resume rather than re-querying completed players.

## NHL Combine enrichment

Use:

- [Official combine leaderboards](https://records.nhl.com/draft/combine/bench-press)
- [2025 fitness-testing results](https://media.nhl.com/site/vasset/public/attachments/2025/06/19060/2025ScoutingCombine_FitnessTestingResults_060725_FINAL.pdf)

Possible fields include jump, pro agility, grip, Wingate cycling, VO2 max, pull-ups, bench power, and limited wingspan.

This is not a complete combine dataset. Store it as sparse optional enrichment with:

- Test year and test age.
- Test/protocol.
- Rank-only/top-performer publication flag.
- Missingness reason where known.

Do not infer arm or leg length from height.

---

# Step 8 — collect official aggregate performance

For each season, pull:

## Realtime events

~~~text
https://api.nhle.com/stats/rest/en/skater/realtime
  ?isAggregate=true
  &isGame=false
  &limit=-1
  &cayenneExp=seasonId={SEASON_ID} and gameTypeId=2
~~~

Fields include takeaways, giveaways, hits, blocked shots, shot attempts blocked, attempts and TOI.

## Faceoffs

~~~text
https://api.nhle.com/stats/rest/en/skater/faceoffpercentages
  ?isAggregate=true
  &isGame=false
  &limit=-1
  &cayenneExp=seasonId={SEASON_ID} and gameTypeId=2
~~~

Store attempts/wins and splits by zone and strength state.

## Penalties

~~~text
https://api.nhle.com/stats/rest/en/skater/penalties
  ?isAggregate=true
  &isGame=false
  &limit=-1
  &cayenneExp=seasonId={SEASON_ID} and gameTypeId=2
~~~

Store taken, drawn, minor/major/misconduct and supplied rates.

## On-ice possession proxies

~~~text
https://api.nhle.com/stats/rest/en/skater/puckPossessions
  ?isAggregate=true
  &isGame=false
  &limit=-1
  &cayenneExp=seasonId={SEASON_ID} and gameTypeId=2
~~~

This contains shot-attempt/Fenwick percentages and zone-start information. It does not contain player-held puck time, battle wins, entries, exits, or pressure events.

## Goals for/against

~~~text
https://api.nhle.com/stats/rest/en/skater/goalsForAgainst
  ?isAggregate=true
  &isGame=false
  &limit=-1
  &cayenneExp=seasonId={SEASON_ID} and gameTypeId=2
~~~

Use official aggregates for reconciliation and the initial MVP, not as the only modeling layer.

Also pull the official skater summary and time-on-ice reports for additional exposure/reconciliation controls:

~~~text
https://api.nhle.com/stats/rest/en/skater/summary
https://api.nhle.com/stats/rest/en/skater/timeonice
~~~

Use the same aggregate season/game-type parameters. If game-level official reports are needed, partition them by team; whole-season game-level queries can exceed service row limits.

---

# Step 9 — collect schedules, play-by-play and shifts

## Schedules

For each team-season:

~~~text
https://api-web.nhle.com/v1/club-schedule-season/{TEAM}/{SEASON_ID}
~~~

Union and deduplicate game IDs. Derive the active team list from official data rather than hardcoding current abbreviations.

## Play-by-play

~~~text
https://api-web.nhle.com/v1/gamecenter/{GAME_ID}/play-by-play
https://api-web.nhle.com/v1/gamecenter/{GAME_ID}/boxscore
~~~

Keep:

- Game state, period, clock, zone and coordinates.
- Event type and player IDs.
- Takeaways, giveaways, hits, blocks, faceoffs, shots and penalties.
- On-ice roster metadata when supplied.

Use game ID, event ID and sort order as the canonical event key. Preserve raw situation codes and transform them into manpower states in a versioned step.

## Shift charts

~~~text
https://api.nhle.com/stats/rest/en/shiftcharts
  ?cayenneExp=gameId={GAME_ID}
~~~

Use shifts to construct:

- On-ice player intervals.
- TOI by strength state.
- Teammate/line/pairing context.
- Event sequences while a player was on ice.

## Schema handling

The NHL API changed shape around 2023–24. Preserve raw responses and normalize them to a canonical event schema containing:

- api_schema_version;
- raw event type;
- canonical event type;
- event timestamp;
- players/roles;
- coordinates;
- strength and empty-net state.

Do not assume a transport/schema change is a metric-definition change, but test distributions before pooling.

---

# Step 10 — collect MoneyPuck

For start years 2021 through 2025:

## Season skaters

~~~text
https://www.moneypuck.com/moneypuck/playerData/seasonSummary/{START_YEAR}/regular/skaters.csv
~~~

## Game-level skaters

~~~text
https://peter-tanner.com/moneypuck/downloads/seasonPlayersSummary/skaters/{START_YEAR}.zip
~~~

## Shots

~~~text
https://peter-tanner.com/moneypuck/downloads/shots_{START_YEAR}.zip
~~~

## Biography cross-check

~~~text
https://www.moneypuck.com/moneypuck/playerData/playerBios/allPlayersLookup.csv
~~~

MoneyPuck supplies player/team/position/situation, TOI, shifts, takeaways, giveaways, defensive-zone giveaways, hits, blocks, faceoffs, zone starts and on-/off-ice Corsi, Fenwick, shots, dangerous chances, goals, and expected goals.

Important rules:

- Keep all-strength and 5v5 rows separately.
- Do not sum overlapping situation rows.
- Shot files include goals, saved shots and misses, but not blocked shots.
- Archive files and hashes because models and historical values can be revised.
- Retain MoneyPuck model/extract date.

[MoneyPuck's download page](https://www.moneypuck.com/data.htm) lists each target season, game-level data and its data dictionary.

## Download management

These NHL endpoints are undocumented and publish no supported bulk-service limit or SLA:

- Cache every successful response by normalized URL.
- Use no more than two concurrent requests and a conservative rate such as one or two requests per second.
- Honor Retry-After and use bounded exponential backoff with jitter for 429/5xx responses.
- Persist failed-request manifests so jobs resume without re-querying completed records.
- Freeze completed seasons after one documented final-correction refresh.
- Refresh only the active season during future development.

Five seasons contain 6,560 expected regular-season games. Play-by-play plus shifts therefore requires roughly 13,120 requests; boxscores add another 6,560. Build resumable batches rather than one monolithic job.

---

# Step 11 — build raw, canonical and model layers

## Landing

Untouched files/responses named by source, season, endpoint and retrieval date.

## Bronze

Source-shaped tables with:

- Source record ID.
- Query URL.
- Retrieval time.
- Hash.
- Raw schema version.

## Silver

- Resolved NHL player IDs.
- Canonical teams, games, positions and strength states.
- Standard units.
- Roster spells.
- Dated measurements.
- Canonical events and shifts.
- Explicit missing/zero/not-applicable states.

## Gold

- Player-game and player-team-season tables.
- Player-season aggregates.
- As-of physical selections.
- Role shares.
- Opportunity-normalized rates.
- Context-adjusted and shrunken component scores.

## Model

- Frozen train/validation/test matrices.
- Fitted preprocessing parameters.
- Split manifests.
- Target definitions and model versions.

## Quarantine

- Ambiguous identities.
- Impossible measurements.
- Birth-date conflicts.
- Duplicate/unmatched events.
- Unreconciled totals.

---

# Step 12 — perform data-quality checks before feature engineering

## Identity and roster checks

- One internal player per NHL player ID.
- No name-only joins without manual review.
- Team changes retained as separate stints.
- Goalies separated from skaters.
- Rostered/no-appearance players preserved.

## Schedule and game checks

- Deduplicate game IDs collected through both teams.
- Confirm 1,312 distinct regular-season games per target season, or document any official exception.
- Verify home/away, game date, season and phase.
- Compare game roster spots with boxscores; a normal game usually has 40 dressed players, while retaining documented exceptions.

## Performance reconciliation

- Compare GP and TOI across official reports and MoneyPuck.
- Reconcile season event totals with aggregated game records.
- Compare a sample of player game logs manually.
- Verify that every faceoff has one winner and loser and that league wins reconcile to league losses.
- Do not force agreement when provider definitions legitimately differ; preserve both versions.

## Shift checks

- No impossible negative or overlapping intervals for one player.
- Player shift TOI reasonably reconciles with box/season TOI.
- Strength-state intervals contain valid on-ice counts.
- Keep boxscore TOI authoritative when shift-chart rounding causes small differences.

## Measurement checks

- Plausible height, weight and speed ranges.
- Duplicates/conflicts preserved and ranked by reliability.
- No measurement published after the prediction anchor enters a preseason feature.
- Combine values never presented as current-season fitness.

## Missingness audit

Report missingness by:

- Season.
- Position/role.
- Team.
- Measurement.
- Source.
- Games and TOI.

Distinguish source failure from a real zero.

## Scorer/rink audit

Plot takeaways, giveaways, hits and blocks per game by rink, home/away and season. Run away-game-only sensitivity rankings. These subjective events require rink/scorer adjustment.

---

# Step 13 — engineer direct-acquisition features

## Takeaways

Calculate at 5v5 and other situations separately:

~~~text
takeaways_60 = 60 × takeaways / TOI_minutes
~~~

Also produce:

- Rink-adjusted takeaways per 60.
- Offensive-, neutral-, and defensive-zone takeaways per 60 where event locations are reliable.
- Takeaways per opponent shot-attempt exposure as an additional opportunity proxy.
- Empirical-Bayes/shrunken takeaway rate.

Do not treat raw takeaway totals as pure skill.

## Puck-security balance

~~~text
net_turnovers_60 =
    60 × (takeaways - giveaways) / TOI_minutes
~~~

Keep takeaways and giveaways visible rather than reporting only the difference.

## Faceoffs

For centers, first model each draw's expected win probability using:

- Opposing center.
- Zone.
- Rink side where available.
- Handedness.
- Strength state.
- Score.
- Home/away.
- Season.

Then:

~~~text
faceoff_wins_above_expected_per_100 =
    100 × sum(actual_win - expected_probability) / faceoffs_taken
~~~

Later, weight draw contexts by the probability or expected-goal value of obtaining the next shot/unblocked attempt within a validated time window.

---

# Step 14 — engineer forecheck and pressure proxies

Public data does not identify every pressure or board-battle winner. Label these as proxies.

Possible event-sequence features:

## Offensive-zone takeaway rate

Credited offensive-zone takeaways per 60 of 5v5 TOI.

## Hit-followed-by-regain proxy

1. The player receives credit for an offensive-zone hit.
2. No whistle/faceoff intervenes.
3. Their team records the next possession-indicative event within five seconds.
4. That event is a takeaway, shot attempt, or another clearly team-controlled event.

Report:

- Qualifying hits.
- Regain sequences.
- Estimated success rate and uncertainty.

This is not a true forecheck-win rate because public play-by-play omits many touches.

## Counterpressure regain proxy

When a team has a recorded possession-loss event, calculate whether it produces the next controlled/shot event within five or ten seconds while the player is on ice. Unless the player gets the credited takeaway, keep this as an on-ice or line-level feature rather than individual attribution.

Validate proxy definitions through a manually reviewed video sample before giving them significant model weight.

---

# Step 15 — engineer suppression, block and physical-intervention features

At 5v5 calculate:

~~~text
CA60   = opponent shot attempts × 60 / TOI
FA60   = opponent unblocked attempts × 60 / TOI
SA60   = opponent shots on goal × 60 / TOI
xGA60  = opponent expected goals × 60 / TOI
HDCA60 = opponent high-danger attempts × 60 / TOI
~~~

Lower is better. Also separate:

- Attempt suppression.
- Danger/shot-quality suppression.
- Rush and rebound xGA where supported.
- On-ice minus team-off-ice values.

## Blocks

~~~text
blocks_60 = 60 × individual_blocks / TOI

block_opportunity_share =
    individual_blocks / opponent_attempts_while_on_ice
~~~

Interpret blocks jointly with suppression:

- High blocks + good suppression can indicate useful intervention.
- High blocks + poor suppression may indicate the team is trapped without the puck.

## Hits

Use rink-adjusted hits per 60 and productive-hit proxies. High hit volume without subsequent regains is physical activity, not demonstrated puck-winning success.

---

# Step 16 — engineer puck-security and discipline features

Create:

- Giveaways per 60.
- Defensive-zone giveaways per 60.
- Expected-goal cost after giveaways.
- Minor penalties taken per 60.
- Penalties drawn per 60.
- Net penalty rate.
- Expected penalty cost based on type and resulting strength state.

For giveaway cost, test whether the opponent generates xG within 5, 10 and 15 seconds after the event. Select the window on validation data rather than choosing the most favorable retrospective result.

Keep fights/majors, obstruction penalties and other types separate before conversion into cost.

---

# Step 17 — engineer movement/range features

From EDGE:

~~~text
maximum_skating_speed
18_plus_mph_bursts_60
20_plus_mph_bursts_60
22_plus_mph_bursts_60
miles_skated_60
20_plus_bursts_per_mile
~~~

Convert each to season × position/role percentiles.

Recommended interpretation:

- Maximum speed: peak range.
- Bursts/60: repeat high-speed activity.
- Distance/60: workload/range.
- Bursts per mile: intensity profile.

Do not label these “reaction speed.” True reaction latency requires raw tracking or controlled testing.

---

# Step 18 — adjust for context

At minimum control for:

- Season.
- Position/role.
- Strength state.
- Team and team-season system.
- Linemates/pairings.
- Opponents.
- Offensive/defensive-zone deployment.
- Score and period.
- Home/away and rink.
- Empty-net situations.
- Rest/back-to-back when available.
- Team stint for traded players.

For subjective event counts, a starting model is:

~~~text
event_count ~ offset(log(TOI))
            + rink
            + rink × home
            + team
            + opponent
            + score_state
            + season
~~~

Use an overdispersed count model and shrink rink effects. Re-estimate by season or partially pool seasons because recording behavior changes.

For shot/xG suppression, use a regularized adjusted model with teammates, opponents and context. Use expected goals against rather than actual goals against as the primary target so goaltending does not dominate.

---

# Step 19 — create the player-season panel

One primary row per skater-season should contain:

- Identity, age and team stints.
- Prior/deployment role and role shares.
- Games, TOI and shifts.
- Dated selected height/weight and measurement staleness.
- Previous-season EDGE measurements for forecast features.
- Raw and adjusted domain metrics.
- Exposure counts.
- Shrunk estimates and intervals.
- Source/coverage flags.

For target season t, add:

- Previous-season value.
- Two- and three-season exponentially weighted means.
- Year-over-year trend.
- Game-to-game consistency.
- Career exposure.
- Age spline.
- Prior role shares.
- Team-change indicator known before the season.

Every feature needs an anchor date and must be available by that date.

---

# Step 20 — discover archetypes without making them circular

Build two separate systems.

## Physical archetypes

Inputs:

- Height and weight.
- Defensible size ratios.
- Lagged EDGE speed, bursts and distance for returning players.
- Sparse combine/testing where available.
- Measurement staleness/missingness.

Age can be used for trajectory analysis but should not define an “innate” body archetype.

## Play-style archetypes

Inputs:

- Acquisition.
- Forecheck/pressure proxies.
- Suppression.
- Blocks/hits.
- Security and discipline.
- EV/PK deployment.

Do not include the ultimate success target in the clustering inputs.

## Clustering procedure

1. Apply reliability thresholds for cluster discovery, while retaining low-TOI players for subsequent scoring.
2. Shrink rates and standardize within season × broad role.
3. Reduce correlated inputs using a transparent PCA/factor model.
4. Compare k-means, Gaussian mixtures and a density approach.
5. Use UMAP only for visualization.
6. Test bootstrap cluster stability and season-to-season reproducibility.
7. If stable discrete clusters do not exist, report continuous archetype axes instead of forcing labels.
8. Name clusters only after inspecting medoids and feature profiles.
9. Preserve membership probabilities rather than assigning every player with false certainty.
10. Cross-tab physical archetypes with play-style archetypes, then compare their adjusted outcomes.

This lets the analysis ask which physical builds tend to produce which styles—and which combinations are successful—without defining success into the cluster.

---

# Step 21 — build component outcome models

Do not start with one possession score. Build:

1. Acquisition model.
2. Suppression model.
3. Forecheck/pressure-proxy model.
4. Security/discipline model.
5. Availability model.
6. Opportunity/TOI model.

## Baselines

Every complex model must beat:

- Role-season mean.
- Prior-season rate.
- Three-season weighted average.
- Age + position + prior TOI model.

## Initial statistical models

- Negative-binomial or overdispersed Poisson counts with TOI offsets.
- Logistic/binomial faceoff models.
- Elastic net or GAM for adjusted/shrunken rates.
- Regularized adjusted plus-minus style models for on-ice shot/xG suppression.
- Gradient-boosted trees as the nonlinear challenger.

Model three stages:

1. Probability of being rostered/appearing.
2. Expected games/TOI conditional on appearing.
3. Effectiveness conditional on opportunity.

Then estimate expected contribution:

~~~text
availability × expected opportunity × effectiveness
~~~

This prevents a tiny-sample rate from automatically outranking a durable full-season contributor.

---

# Step 22 — use a leakage-safe temporal split

## Descriptive model

May use all completed 2021–22 through 2025–26 outcomes. Label it retrospective.

## Predictive model

- Predict 2022–23 using information through 2021–22.
- Predict 2023–24 using information through 2022–23.
- Use 2024–25 for validation and model selection.
- Lock features, preprocessing, archetypes and hyperparameters.
- Evaluate once on 2025–26 as the untouched final test.

The same returning player may appear in earlier training seasons and a later test season because that matches the known-player use case. However:

- Never randomly split player-season rows.
- Use player-clustered bootstrap intervals.
- Add a held-out-player evaluation to measure dependence on player history.
- Fit scalers, imputers, PCA, clusters and feature selection inside each training fold.

For a 2025–26 preseason prediction, do not use 2025–26 EDGE, role, team outcome, injury outcome, TOI or performance.

---

# Step 23 — define hidden value prospectively

Do not call every high-rate, low-minute player a hidden gem.

A candidate should satisfy:

- High predicted adjusted effectiveness.
- Low prior/current expected opportunity relative to role peers.
- A lower uncertainty bound that remains at least above average.
- Adequate historical exposure.
- No severe out-of-distribution flag.

Useful categories:

- **Under-deployed:** high talent forecast, low deployment.
- **Context-suppressed:** adjusted impact is materially better than raw results.
- **Archetype match:** resembles a successful type but has limited opportunity.
- **Contract value:** add only after acquiring valid salary/cap data.

Backtest each season:

- Did preseason-flagged players produce top-quartile effectiveness?
- Did their TOI increase?
- Did they outperform same-age, same-role, same-opportunity controls?

Injury-driven low minutes should not automatically create a hidden-value label.

---

# Step 24 — create the cold-start model carefully

## Core tier

- Age.
- Height and weight.
- Handedness/shooting side.
- Draft/entry information if it is available before evaluation.

## Enhanced tier

- Sparse combine/fitness tests.
- Prospect-league metrics or licensed tracking if later acquired.

For genuine NHL entrants:

- Train on earlier entry cohorts.
- Hold out entire players/cohorts.
- Keep every NHL season for a held-out player outside training.

For a cross-sport athlete, output:

- Closest NHL physical archetypes.
- Similarity percentile by role.
- Data coverage and uncertainty.
- Out-of-distribution warning.

Do not output “probability of becoming an NHL player” without actual labeled cross-sport transition data.

---

# Step 25 — evaluate the models

## Continuous predictions

- MAE/RMSE.
- Appropriate count deviance.
- Spearman rank correlation.

## Rankings/classification

- Precision and recall for top-quartile players.
- Precision at K / NDCG.
- Brier score and calibration.

## Uncertainty

- Empirical interval coverage.
- Interval width.
- Player/game-block bootstrap.

## Required slices

- Forward versus defense.
- Fine role.
- Age band.
- TOI/exposure band.
- Changed team versus stayed.
- Missing versus available EDGE/physical data.
- Home/away sensitivity for scorer-dependent events.

---

# Step 26 — prepare the cross-sport handoff

Export NHL results using a common contract:

- Sport, season, as-of date and role.
- Model/data-tier versions.
- Availability probability.
- Expected-opportunity percentile.
- Direct-acquisition percentile.
- Disruption/pressure percentile.
- Recovery/transition percentile, nullable when unmeasured.
- Suppression/contest percentile.
- Range/mobility percentile.
- Decision-efficiency percentile.
- Expected-contribution percentile.
- Physical and play-style archetypes with membership probabilities.
- Role-fit percentile.
- Uncertainty bounds.
- Coverage, staleness and out-of-distribution flags.

All percentiles must be calibrated within NHL season × role. Preserve raw NHL metrics underneath them. Later sports will map their own evidence to these dimensions; raw takeaways, steals, sacks and interceptions must not be pooled.

---

# Practical build order

## NHL MVP

Build this first:

1. Source registry and terms.
2. Five-season player/roster/identity panel.
3. Official bios, realtime, faceoff, penalty and on-ice reports.
4. MoneyPuck season/game files.
5. EDGE player-season movement data.
6. Dated measurement table.
7. Player-season 5v5 rates.
8. Rink adjustment and empirical-Bayes shrinkage.
9. Physical and play-style archetypes.
10. Descriptive component dashboard.

This is enough to learn useful archetypes without processing every event.

## NHL version 2

Add:

1. Full schedules and game roster spots.
2. Play-by-play.
3. Shift reconstruction.
4. Event locations and strength/score context.
5. Hit-followed-by-regain and turnover-cost proxies.
6. Teammate/opponent adjusted suppression.
7. Returning-player forecast.
8. Hidden-value backtests.

## NHL version 3

Add only if justified:

- Licensed entry/exit, retrieval, puck-battle or pressure data.
- Manually labeled video validation samples.
- Prospect-league or development-league data.
- Salary/cap layer.
- Raw tracking or richer commercial movement data.

---

# First ten concrete actions

1. Approve the seven-domain NHL construct.
2. Approve the initial center, winger and defense role families.
3. Create the source registry and terms snapshot.
4. Create season, team, player, identity, roster-spell and measurement schemas.
5. Download five seasons of official aggregate reports and MoneyPuck files.
6. Build the NHL player-ID crosswalk and roster-universe audit.
7. Queue and cache EDGE player-season requests.
8. Reconcile GP, TOI and core events between official data and MoneyPuck.
9. Publish missingness plus rink/scorer-bias reports.
10. Build the first 5v5 player-season feature table before attempting clustering.

The most important checkpoint is number ten. Do not begin clustering until the roster universe, opportunity denominators, source-definition differences, and scorer-bias audit are credible.
