# All-role data sources, coverage, and release gates

Status date: 22 October 2026

This document is the source-governance guide for the NFL, NBA, NHL, and Premier League all-role project. It records what is cached, what each source can support, which physical values are genuinely time-specific, and when a model must abstain. The machine-readable companion is [`metadata/all_roles_source_matrix.json`](../metadata/all_roles_source_matrix.json).

This is a research and engineering assessment, not legal advice. Public accessibility is not the same as permission to redistribute data or commercialize a model trained from it.

## 1. Decision vocabulary

The source matrix uses three deliberately conservative labels:

| Posture | Project meaning |
|---|---|
| **Green** | An explicit license supports the stated use if attribution and the other license conditions are followed. |
| **Amber** | Local research is defensible only within stated conditions, or the upstream rights chain is not clear enough for raw redistribution or commercial use. |
| **Red** | Keep the source out of release training, raw redistribution, and commercial use until written permission, a licensed replacement, or a documented rights review exists. |

The label applies to the named source and use case, not automatically to every downstream artifact. A model that combines a green source with a red source inherits the red release gate.

For exact acquisition evidence, use each raw file's adjacent `.source.json` sidecar. It records the designated URL, retrieval time, SHA-256, byte count, source label, and source-use note. [`metadata/download_manifest.json`](../metadata/download_manifest.json) is the convenient aggregate, but it must be regenerated after every acquisition. The current raw cache has 253 sidecars: the earlier 224-file snapshot plus 29 rate-limited Wikidata query batches. It also includes all five designated MoneyPuck goalie summaries for 2021 through 2025.

## 2. Current all-role snapshot

The canonical `season` is the NFL season year for football and the season-start year for the NBA, NHL, and EPL. Thus `2025` means 2025-26 outside the NFL. All modeled outcomes are regular-season outcomes.

| Sport | Current all-role rows | Athletes | Roles in v1 | Height + weight |
|---|---:|---:|---|---:|
| NFL | 15,518 | 5,850 | QB, RB/FB, WR, TE, EDGE, IDL, LB, CB, S, K, P; OT, IOL, and LS are identity-only abstentions | 15,337 (98.8%) |
| NBA | 2,866 | 1,030 | guard, forward, center | 2,866 (100.0%) |
| NHL | 5,263 | 1,654 | center, left wing, right wing, defense, goalie | 5,257 (99.9%) |
| EPL | 4,005 | 1,777 | **GK, DEF, MID, FWD only** | 1,784 (44.5%) |

These are counts from the current derived Parquet files, not contractual source counts. They can change when a cache is refreshed or a cleaning rule changes. The NBA all-role count is smaller than the broader canonical roster/profile panel because this adapter requires a confirmed regular-season appearance. The NHL universe is appearance-based and does not represent every zero-game contract player.

## 3. How to use seasonal physical data correctly

Multi-season performance data are valuable because they let the project compare a player's performance with same-role peers in each season, estimate year-to-year stability, and hold out a later season. They do **not** turn an undated profile weight into five annual weigh-ins.

The safe distinction is:

- A **season-role performance percentile** compares genuinely observed performance in that season with the appropriate peers.
- A **season-cohort physical percentile** can compare the best valid profile value with that season's athletes, but the label must say “profile percentile” when the measurement date is unknown.
- A **physical-change feature** requires two dated measurements with known or defensible protocols. Repeating a current profile value across earlier seasons cannot create this feature.

If the same undated height or weight appears in five player-season rows, those rows are five performance observations but one physical observation for longitudinal purposes. Player-level grouping is therefore required in validation so repeated seasons do not leak the same athlete into both train and test folds.

The current source timing is:

| Sport | Physical source | Timing interpretation |
|---|---|---|
| NFL | Earliest archived weekly roster listing in each season | Season-attached listing; actual measurement date and protocol are unknown. Combine/pro-day tests are genuinely dated historical events but often predate the modeled season by years. |
| NBA | SportsDataverse/ESPN `player_core` profile | Regenerated current/undated profile. Do not interpret repeated values as annual measurements. |
| NHL | Season-filtered NHL Stats bio universe for skaters; current MoneyPuck lookup for goalies | Both are current/undated profiles. Every all-role NHL row is marked as not a confirmed season measurement. |
| EPL | ESPN 2025 roster profiles, filled only where missing by strict Wikidata CC0 matches | Both are current/undated profiles. Propagation to earlier seasons does not make either source historical. |

No sport currently has a general, rights-cleared, season-dated source for wingspan, arm length, leg length, top speed, agility, and reaction time together. NFL prospect testing supplies some of these fields for a subset, but its reuse posture is not cleared for model training. There is no general leg-length source in the repository.

## 4. Source posture at a glance

| Source family | Overall posture | What is safe now | Main restriction |
|---|---|---|---|
| nflverse core releases | Green | Research and attributed derived publication | Preserve attribution; still review third-party marks and commercial product terms. |
| nflverse Next Gen Stats release | Green | Automated research and attributed derived publication for passing, rushing, and receiving | Skill-position coverage only; preserve nflverse and NFL Next Gen Stats attribution and respect provider minimum-attempt thresholds. |
| nflverse play participation | Amber | Local research with provider attribution | CC BY-SA 4.0 and NGS/FTN provider chain require release compatibility review. |
| PFR-derived nflverse snaps, advanced defense, combine | Red | Cached source inspection only | Sports Reference data/AI/ML terms require review; the hardened all-role runtime and models do not load or depend on these files. |
| array-carpenter prospect tests | Red | Source inspection only | No clear dataset reuse license found. |
| SportsDataverse ESPN NBA releases | Amber | Local reproducible research/prototyping | The packaging license does not settle underlying ESPN/NBA rights. |
| MoneyPuck designated files | Amber | Noncommercial research with clear MoneyPuck attribution | Other uses require permission; raw redistribution is not assumed. |
| NHL Stats bios | Amber | Dated local research enrichment | No general open-data redistribution grant is asserted. |
| Vaastav FPL archive | Amber | Local research prototype | MIT covers repository software; underlying FPL/Understat data rights remain upstream. |
| FPL-Core-Insights | Red | Source inspection only | No repository data license found and provider rights are unclear. |
| ESPN EPL profile JSON | Amber | Dated local research enrichment | No asserted open-data license; partial and current/undated. |
| FBref / Sports Reference | Red for this model | Source evaluation only; no data ingested | Current terms prohibit using site content to support ML methods that predict, classify, label, or score inputs; the former advanced soccer feed was deleted in January 2026. |
| Pappalardo/Wyscout Figshare benchmark | Green | Historical research and attributed publication | Historical benchmark only; not current EPL truth. |
| StatsBomb Open Data | Amber | Listed competitions after accepting custom terms | Custom agreement and attribution/logo conditions; recent EPL is not in the open index. |
| Wikidata profile enrichment | Green | Automated CC0 identity and undated profile enrichment | Community-maintained values need strict entity matching, plausibility checks, and timing labels. |
| SkillCorner Open Data | Green | Tracking and cross-sport feature-engineering benchmark | The current open cohort is 2024-25 A-League, not Premier League player truth. |
| NBA.com Stats, Hustle, and Tracking | Red for automated ingestion | Manual source inspection only without written permission | NBA terms limit statistics to specified noncommercial uses; the NBA Stats FAQ says the statistics are not available for download. |
| NHL EDGE and other NHL.com data pages | Red for automated ingestion | Manual source inspection only without written permission | NHL terms prohibit unauthorized scraping or automated compilation and restrict database/derivative use. |

### Automation boundary

“Public in a browser” does not mean “safe to automate.” The acquisition layer must follow these source-specific rules:

- [nflverse](https://github.com/nflverse) states that most release data, including the Next Gen Stats release unless a release page says otherwise, are CC BY 4.0; FTN data are CC BY-SA 4.0. Automated release downloads are allowed with the required attribution and share-alike handling.
- [MoneyPuck](https://moneypuck.com/data.htm) permits the files listed on its data page for noncommercial use and ad-hoc journalism with clear attribution. Automate only those designated downloads; do not scrape unlisted pages.
- [Wikidata](https://www.wikidata.org/wiki/Help:Data_access) is CC0 and suitable for automated enrichment. Send an identifiable User-Agent, request compressed responses, avoid high parallelism, and obey `429`/`Retry-After` responses.
- [Sports Reference terms](https://www.sports-reference.com/termsofuse.html) section 5, item 11(ii), prohibits using site content to support machine-learning methods that predict, classify, label, or score inputs. The [Sports Reference data-use page](https://www.sports-reference.com/data_use.html) repeats that restriction. FBref is therefore not an input to this repository, whether acquired manually or automatically.
- [Fantasy Premier League terms](https://fantasy.premierleague.com/help/terms) state that the Premier League owns Game data and prohibit automated systems used to access and extract information. The cached Vaastav archive may support the existing amber local-research prototype, but the project must not add a direct FPL scraper or assume redistribution rights.
- [NBA.com terms](https://www.nba.com/termsofuse) restrict NBA Statistics to attributed legitimate news reporting or private noncommercial use and prohibit a comprehensive regularly updated statistics database without consent. The [NBA Stats FAQ](https://www.nba.com/stats/help/faq) says those statistics are not available for download for academic or personal use. Do not automate NBA.com Stats endpoints without written permission or a licensed feed.
- [NHL.com terms](https://www.nhl.com/info/terms-of-service) prohibit unauthorized spidering, scraping, or automated compilation and restrict copying data into a database or creating derivatives. Do not automate NHL EDGE or undocumented NHL endpoints without written permission.

These are engineering release gates, not legal conclusions. Re-check the current terms before every new adapter or public deployment.

## 5. NFL

### Cached sources and designated URLs

The NFL cache covers 2021 through 2025.

| Layer | Cache | Designated URL | Key use |
|---|---|---|---|
| Weekly rosters | `data/raw/nfl/{season}/roster_weekly_{season}.parquet` | `https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_{season}.parquet` | GSIS identity, position/depth chart, team, week, height, weight, birth date |
| Weekly player statistics | `data/raw/nfl/{season}/stats_player_week_{season}.parquet` | `.../stats_player/stats_player_week_{season}.parquet` | Passing, rushing, receiving, defensive credits, kicking, and punting totals |
| Play-by-play | `data/raw/nfl/{season}/play_by_play_{season}.parquet` | `.../pbp/play_by_play_{season}.parquet` | Play scope, defensive credit fields, offensive penalties |
| Play participation | `data/raw/nfl/{season}/pbp_participation_{season}.parquet` | `.../pbp_participation/pbp_participation_{season}.parquet` | Defenders on each play and pressure-play context |
| Player registry | `data/raw/nfl/players.parquet` | `.../players/players.parquet` | GSIS/PFR/SMART crosswalk and profile identity |
| Schedules | `data/raw/nfl/games.parquet` | `.../schedules/games.parquet` | Completed regular-game universe |
| PFR-derived snaps | `data/raw/nfl/{season}/snap_counts_{season}.parquet` | `.../snap_counts/snap_counts_{season}.parquet` | Cached inventory only; excluded from hardened all-role runtime, denominators, and models |
| PFR-derived advanced defense | `data/raw/nfl/{season}/advstats_week_def_{season}.parquet` | `.../pfr_advstats/advstats_week_def_{season}.parquet` | Cached inventory only; excluded from hardened all-role runtime and models |
| PFR-derived combine | `data/raw/nfl/combine.parquet` | `.../combine/combine.parquet` | Cached historical testing inventory only; excluded from all-role model features |
| Community prospect testing | `data/raw/nfl/optional/combine_{official,pro_day}.parquet` | `https://raw.githubusercontent.com/array-carpenter/nfl-draft-data/master/data/...` | Optional arm, hand, wingspan, speed, jump, agility, and bench data |

The omitted prefix in the nflverse table is `https://github.com/nflverse/nflverse-data/releases/download`. The [nflverse-data license](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md) is CC BY 4.0 for the core release repository. Participation is separately documented as CC BY-SA 4.0, with NFL NextGenStats via nflverse through 2022 and FTN Data via nflverse from 2023 onward.

### Role and outcome coverage

The current broad taxonomy is supportable from roster/depth-chart labels, with important qualifications:

- `QB`: passing EPA/value, efficiency, first downs, air yards, scoring, interceptions/fumbles, and sack avoidance.
- `RB_FB`: rushing and receiving value, first downs, scoring, and ball security.
- `WR` and `TE`: receiving value, catch/conversion efficiency, yards after catch, scoring, and ball security.
- `EDGE` and `IDL`: sacks, QB hits, negative-play tackles, and forced fumbles on a participation-aligned denominator.
- `LB`, `CB`, and `S`: interceptions, passes defended, tackles/stops, and forced fumbles.
- `K`: field-goal, long-field-goal, and extra-point rates.
- `P`: net yards, inside-20 rate, touchback rate, and blocked-punt avoidance.
- `OT`, `IOL`, and `LS`: roster identity and build are retained, but no release-safe individual public performance label is used. Opportunity, games, and snap-derived fields remain null; observed targets and performance models abstain.

The season role is the modal specific canonical role across all available regular-season weekly depth-chart observations. Generic `DB`, `DL`, and `OL` records do not vote and are not guessed into granular roles. Ties are resolved by the most recent observed week and then a deterministic role string, with the tie flag preserved. `OLB` is grouped with `EDGE` as an explicit broad-taxonomy assumption; it is not proof of pass-rush assignment. Slot/outside corner, box/deep safety, rush/coverage linebacker, route, and blocking-assignment roles require licensed charting or tracking.

The current hardened snapshot has these role counts:

| Role | Rows | Role | Rows |
|---|---:|---|---:|
| QB | 631 | RB/FB | 1,163 |
| WR | 2,017 | TE | 1,048 |
| OT | 1,208 | IOL | 1,473 |
| EDGE | 1,959 | IDL | 1,234 |
| LB | 1,112 | CB | 1,613 |
| S | 1,111 | K | 263 |
| P | 223 | LS | 214 |
| Unmapped generic-only history | 249 | **Total** | **15,518** |

All 2,895 OT/IOL/LS rows carry an explicit abstention state: OT and IOL use `abstain_source_rights_and_label_limit`, while LS uses `abstain_no_public_label`. Their `snap_fields_status` records `not_loaded_conditional_pfr_source`; the current all-role panel has no observed OT/IOL/LS opportunity, games, or offensive-snap values.

### Physical coverage

The default panel has plausible height and weight together for 15,337 of 15,518 rows after physical-value quarantine. That high completeness should not be mistaken for measurement quality. The values are roster listings and the code marks the actual measurement date as unknown.

The optional measurement inventory contains arm length, hand size, wingspan, 40-yard time, 10-yard split, vertical jump, broad jump, three-cone, shuttle, and bench press, with test year and protocol. Coverage is uneven: the earlier audit found arm/hand data for 1,991 players, wingspan for 293, 40-yard times for 1,611, and 10-yard splits for 1,199 in the broader inventory. These fields remain excluded from release training pending rights review.

### Newly consumed cached fields and next enrichment

The 22 October 2026 source pass uses three more fields already present in the weekly nflverse statistics: `passing_20`, `rushing_10`, and `receiving_20`. They produce role-specific explosive-play rates per attempt or target. This adds no new source or rights dependency, but the same opportunity thresholds used for the corresponding attempts/targets still apply.

The highest-priority new NFL acquisition is the [nflverse Next Gen Stats release](https://github.com/nflverse/nflverse-data/releases/tag/nextgen_stats), documented in the [`load_nextgen_stats` reference](https://nflreadr.nflverse.com/reference/load_nextgen_stats.html) and [data dictionary](https://nflreadr.nflverse.com/articles/dictionary_nextgen_stats.html). It covers 2016 onward, supplies regular-season summary rows as `week == 0`, and joins directly on `player_gsis_id`. The useful transferable fields are:

- passing: average time to throw, completed/intended air yards, air-yards differential and air yards to the sticks, aggressiveness/tight-window rate, maximum completed air distance, expected completion percentage, and completion percentage over expected;
- rushing: route efficiency measured as distance travelled per rush yard, time to the line of scrimmage, rate versus eight-plus defenders in the box, expected rushing yards, rushing yards over expected, and rate above expectation;
- receiving: cushion, separation, intended air yards and share, catch percentage, yards after catch, expected yards after catch, and yards after catch over expected.

These fields support speed-of-decision, separation, movement-efficiency, and expectation-adjusted production features for QB, RB, WR, and TE. They do not solve defensive, offensive-line, kicker, punter, or long-snapper evaluation. Provider minimum-attempt rules must be retained rather than treating omitted players as zero-valued.

### NFL go/no-go

- **Go:** local core-role research with attributed nflverse core and correctly attributed participation data.
- **Conditional:** public participation-derived work only after implementing CC BY-SA compatibility and NGS/FTN attribution.
- **Abstain:** OT, IOL, and LS identities/builds remain visible, but do not emit observed performance, native forecasts, or target-role performance scores without a release-safe individual label and complete denominator.
- **No-go:** present any current OT/IOL field as blocking quality or any LS field as snapping quality.
- **No-go:** train on PFR-derived snaps, advanced defense, combine, or the optional community testing files until source-use rights are cleared. The current all-role runtime excludes them.

## 6. NBA

### Cached sources and designated URLs

The NBA uses season-ending source years 2022 through 2026 for project seasons 2021 through 2025.

| Layer | Cache | Designated URL template |
|---|---|---|
| Player profile | `data/raw/nba/{ending_year}/player_core_{ending_year}.parquet` | `https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_player_core/player_core_{ending_year}.parquet` |
| Game roster | `data/raw/nba/{ending_year}/game_rosters_{ending_year}.parquet` | `.../espn_nba_game_rosters/game_rosters_{ending_year}.parquet` |
| Player box score | `data/raw/nba/{ending_year}/player_box_{ending_year}.parquet` | `.../espn_nba_player_boxscores/player_box_{ending_year}.parquet` |
| Optional ID crosswalk | `data/raw/nba/nba_player_crosswalk_2026.parquet` | `.../nba_crosswalk/nba_player_crosswalk_2026.parquet` |

The full prefix is `https://github.com/sportsdataverse/sportsdataverse-data/releases/download`. The [SportsDataverse release repository](https://github.com/sportsdataverse/sportsdataverse-data) publicly packages the files, but the project conservatively treats the ESPN/NBA upstream rights chain as unresolved for raw redistribution and commercial use.

The panel uses ESPN athlete ID as canonical identity. The crosswalk is optional because its historical coverage is incomplete. Game-roster and box-score joins retain confirmed appearances while removing exhibitions and the NBA Cup final from standings-game scope.

### Fields and role outcomes

Consumed box fields include minutes, starts, field goals, three-pointers, free throws, points, assists, turnovers, offensive and defensive rebounds, steals, blocks, fouls, and plus/minus. Derived v1 metrics include per-36 scoring, assists, turnovers, rebounds, steals, blocks, fouls, and plus/minus; true shooting; effective field-goal percentage; three-point percentage; three-point-attempt rate; free-throw percentage; free-throw-attempt rate; and assist-turnover ratio. The four latter workload/style fields added on 22 October 2026 are calculated from the existing cache and introduce no new acquisition dependency.

The only stable v1 roles are `guard`, `forward`, and `center`:

- Guards emphasize scoring efficiency, creation, ball security, disruption, and defensive rebounding.
- Forwards add offensive rebounding to those domains.
- Centers emphasize finishing, rim disruption, creation/ball security, and offensive/defensive rebounding.

Raw profile abbreviations may include PG, SG, SF, and PF, but the multi-season source is not a reliable deployment history. Primary-handler, wing-stopper, rim-protector, switch defender, and matchup roles need licensed lineup/tracking data. The current cache has no league-wide deflections, charges drawn, loose balls recovered, contested shots, matchup possessions, or speed/tracking feed.

The best playing-profile supplement would add official-style hustle and tracking measures: deflections, offensive and defensive loose balls recovered, charges drawn, contested two- and three-point shots, screen assists and screen-assist points, box outs, speed and distance, touches, passes, potential assists, drives, time of possession, rebound chances, defended field goals, and catch-and-shoot, pull-up, paint, post, and elbow touches. These are target fields for a licensed provider, not an instruction to scrape NBA.com. The [NBA terms](https://www.nba.com/termsofuse) and [NBA Stats FAQ](https://www.nba.com/stats/help/faq) make automated ingestion inappropriate without written permission.

Likewise, official combine measurements could add height with and without shoes, weight, wingspan, standing reach, body-fat percentage, hand length and width, lane agility, shuttle, three-quarter-court sprint, and standing/max vertical. They cover combine participants rather than the full league and remain a manual or licensed option under the same rights gate.

### Physical coverage and gates

Height, weight, and age are complete across the current 2,866 all-role rows. The profile files were regenerated from current ESPN profiles, so completeness does not make them annual observations. Wingspan, arm length, leg length, top speed, agility tests, and reaction measures are absent.

- **Go:** local guard/forward/center research with transparent box-score composites.
- **No-go:** infer annual weight change from repeated current-profile values.
- **No-go:** claim granular defensive-role ability without a licensed tracking or matchup source.
- **No-go:** redistribute cached row-level ESPN-derived data or commercialize the result before upstream rights review.

## 7. NHL

### Cached sources and designated URLs

The NHL cache covers 2021-22 through 2025-26.

| Layer | Cache | Designated URL template | All-role use |
|---|---|---|---|
| MoneyPuck skater summary | `data/raw/nhl/moneypuck_skaters_{season}_regular.csv` | `https://www.moneypuck.com/moneypuck/playerData/seasonSummary/{season}/regular/skaters.csv` | Skater outcomes |
| MoneyPuck goalie summary | `data/raw/nhl/moneypuck_goalies_{season}_regular.csv` | `https://www.moneypuck.com/moneypuck/playerData/seasonSummary/{season}/regular/goalies.csv` | Goalie outcomes |
| MoneyPuck player-game skaters | `data/raw/nhl/moneypuck_skater_games_{season}.zip` | `https://peter-tanner.com/moneypuck/downloads/seasonPlayersSummary/skaters/{season}.zip` | Base-pipeline QA and possession analysis, not the all-role season-summary builder |
| MoneyPuck player lookup | `data/raw/nhl/moneypuck_all_players_lookup.csv` | `https://www.moneypuck.com/moneypuck/playerData/playerBios/allPlayersLookup.csv` | Goalie and fallback physical/profile values |
| NHL Stats bios | `data/raw/nhl/nhl_official_skater_bios_{season}{season+1}.json` | `https://api.nhle.com/stats/rest/en/skater/bios?...seasonId={season}{season+1}...` | Skater physical values and birth date |

[MoneyPuck's data page](https://moneypuck.com/data.htm) permits noncommercial use and ad-hoc journalism, requires clear MoneyPuck attribution whenever its data are an input, asks users to contact MoneyPuck for other purposes, and prohibits unapproved scraping of data not listed there. This is why its overall project posture is amber rather than green.

The builder selects `situation=all`. That row already includes even-strength and special-teams activity; it must never be added to `5on5` or other situation rows. For traded players, an explicit provider total row is preferred. Otherwise team stints are summed once. Ice time is stored in seconds and converted to minutes before every per-60 calculation.

### Skater fields and roles

The exact MoneyPuck fields used for skaters are:

- identity/exposure: `playerId`, `season`, `name`, `team`, `position`, `situation`, `games_played`, `icetime`;
- scoring/creation and shot quality: `I_F_goals`, `I_F_xGoals`, `I_F_primaryAssists`, `I_F_secondaryAssists`, `I_F_shotsOnGoal`, `I_F_shotAttempts`, and `I_F_highDangerShots`;
- security/disruption: `I_F_giveaways`, `I_F_takeaways`, `shotsBlockedByPlayer`, `I_F_hits`, `penalties`, and `penaltiesDrawn`;
- faceoffs: `faceoffsWon` and `faceoffsLost`;
- territory: `onIce_xGoalsPercentage`, `offIce_xGoalsPercentage`, `onIce_corsiPercentage`, and `offIce_corsiPercentage`.

The v1 mapping is direct: C to center, L/LW to left wing, R/RW to right wing, and D to defense. The 22 October 2026 feature pass adds shots on goal, shot attempts, and high-danger shots per 60; faceoff win percentage; penalty differential per 60; on-ice Corsi share; and relative Corsi. The existing domains remain goals/xG, primary/secondary assists, giveaways and takeaway-giveaway ratio, takeaways/blocks/hits, and on-ice/relative expected-goal share. All rate calculations use the same all-situations ice-time scope, and positions that do not take meaningful faceoff volume must receive missing/low-evidence status rather than a synthetic zero.

The 154-column skater summary has further audited but not yet consumed candidates: shifts and game score; low-, medium-, and high-danger shots, expected goals, and goals; defensive-zone giveaways; zone and on-the-fly shift starts/ends; on-ice for/against shots, attempts, expected goals, and danger; and after-shift expected-goal, Corsi, and Fenwick measures. These should enter only after a metric-grain, collinearity, and stability review. In particular, overlapping shot-volume and territory summaries should not be counted as independent evidence simply because all are available.

These labels do not identify line number, shutdown or transition deployment, special-team unit, defense pairing, handed side, or specific forechecking role. Those need additional shift, lineup, or tracking evidence.

### New goalie layer

All five designated goalie summaries are now cached with source sidecars and are included in the current 224-file central download manifest:

| Season | SHA-256 prefix | Bytes |
|---:|---|---:|
| 2021 | `7fb1b4b7dcda` | 111,789 |
| 2022 | `a7f712fd7f50` | 101,858 |
| 2023 | `9b9ca9dad5f2` | 93,777 |
| 2024 | `a718782ffbeb` | 97,451 |
| 2025 | `2fe2a2dbf258` | 93,386 |

The exact fields used are `xGoals`, `goals`, `ongoal`, `highDangerShots`, `highDangerGoals`, and `rebounds`, plus identity and ice time. The derived goalie outputs are save percentage, high-danger save percentage, goals saved above expected per 60, and rebounds allowed per save.

MoneyPuck's goalie file does **not** contain a rebound-goal field. The clear metric is `rebound_rate = rebounds / saves`. The current output keeps `rebound_goals_against_rate` as a legacy alias with identical values; it must not be described as actual rebound goals against.

The new layer adds 525 goalie player-seasons, bringing the current NHL all-role panel to 5,263 rows. This materially improves full-position coverage, but it does not supply goalie tracking, puck-handling quality, rebound location, or shot-screen context.

### Physical coverage and gates

The NHL all-role panel has height and weight for 5,257 of 5,263 rows. Skater values come from season-filtered NHL Stats bio reports; goalie values come from the MoneyPuck player lookup. The filter identifies the athlete universe, not the date of the measurement. Every row is explicitly marked `physical_is_confirmed_season_measurement=false`.

[NHL EDGE](https://www.nhl.com/edge) can display top speed, speed bursts, skating distance, shot speed, zone time, and zone starts, but it is a manual/licensed acquisition path only. The [NHL terms](https://www.nhl.com/info/terms-of-service) prohibit unauthorized automated compilation and database/derivative use; no scraper should be added without written permission.

- **Go:** local noncommercial skater and goalie research with clear MoneyPuck attribution.
- **Conditional:** public derived work after confirming attribution/display requirements and excluding raw-file redistribution.
- **Satisfied provenance gate:** the current central source manifest includes all five 2021–2025 goalie summaries and their sidecar provenance.
- **No-go:** commercial model or portal use without MoneyPuck permission and an NHL source/marks review.
- **No-go:** interpret repeated height/weight as annual measurements or the legacy rebound alias as rebound goals.

## 8. Premier League

### v1 scope: broad roles only

The Premier League all-role model remains **GK, DEF, MID, and FWD in v1**. That is an evidence boundary, not a temporary display choice.

The five-season cache does not provide a reliable longitudinal ground truth for center-back, fullback, wingback, defensive midfield, central midfield, attacking midfield, left/right wing, second striker, or center forward. Name, body shape, event mix, or broad FPL position must not be used to manufacture those labels. A recent granular role model needs a licensed event/lineup or tracking source with dated deployment positions.

### Vaastav five-season common core

The broad all-role builder uses the Vaastav FPL archive for 2021-22 through 2025-26:

| File | Cache | Designated URL template |
|---|---|---|
| Player profiles | `data/raw/epl/vaastav/{season}/players_raw.csv` | `https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{season}/players_raw.csv` |
| Gameweeks | `data/raw/epl/vaastav/{season}/merged_gw.csv` | `.../data/{season}/gws/merged_gw.csv` |
| Teams | `data/raw/epl/vaastav/{season}/teams.csv` | `.../data/{season}/teams.csv` |

The raw-cache audit on 22 October 2026 found the following exact coverage. “Player IDs” are season-local FPL `element` IDs, not cross-season identities.

| Season | Gameweek rows | Player IDs | Last GW | Expected metrics + starts | Defensive-action fields | `opta_code` | Birth date |
|---|---:|---:|---:|---|---|---:|---:|
| 2021-22 | 25,447 | 737 | 38 | No | No | 0 / 737 | 0 / 737 |
| 2022-23 | 26,505 | 778 | 38 | Yes | No | 0 / 778 | 0 / 778 |
| 2023-24 | 29,725 | 865 | 38 | Yes | No | 0 / 865 | 0 / 865 |
| 2024-25 | 27,605 | 804 | 38 | Yes | No | 804 / 804 | 642 / 804 |
| 2025-26 | 29,757 | 841 | 38 | Yes | Yes | 841 / 841 | 822 / 841 |

The profile table supplies season-local ID, stable FPL `code`, name, team, broad element type, and birth date where available. Use `fpl:<code>` as the current cross-season canonical identity, not the transient `element`/`id`. The 2024-25 and 2025-26 `opta_code` field is the preferred direct key if a licensed Opta feed is later procured. The gameweek table supplies fixture, minutes, goals, assists, clean sheets, goals conceded, saves, yellow/red cards, penalties saved, creativity, and threat.

The 22 October feature pass also consumes optional fields only when present: `expected_goals`, `expected_assists`, `expected_goal_involvements`, `expected_goals_conceded`, `influence`, `ict_index`, `starts`, `clearances_blocks_interceptions`, `defensive_contribution`, `recoveries`, and `tackles`. It derives per-90 expected metrics, finishing over expected, goal prevention over expected, defensive actions per 90, defensive contribution per 90, and start rate. Older unavailable seasons stay missing; they are never backfilled to zero.

For 2025-26 outfield rows, `defensive_contribution` is a deterministic scoring copy of the official components: defenders use clearances + blocks + interceptions + tackles, while midfielders and forwards also include recoveries. Goalkeepers are recorded as zero. Use that field as a QA total or use the components, but do not give both independent weight in one composite. The [Premier League rule explanation](https://www.premierleague.com/en/news/4362211) sets the 2025-26 thresholds at 10 CBIT actions for defenders and 12 CBIRT actions for midfielders/forwards to earn two FPL points.

The role-specific v1 outcomes are:

- `GK`: saves per 90, goals conceded per 90, clean-sheet rate, and penalties saved per 90;
- `DEF`: team-context clean-sheet/goals-conceded outcomes, assists/creativity, goals, and discipline;
- `MID`: assists/creativity, goals/threat, and discipline;
- `FWD`: goals/threat, assists/creativity, and discipline.

Defender outcomes are explicitly limited team-context proxies. A clean sheet is not an individual defensive action label.

The [Vaastav repository license](https://github.com/vaastav/Fantasy-Premier-League/blob/master/LICENSE) covers repository software while stating that underlying data belong to Fantasy Premier League and Understat. Therefore this is an amber local-research source, not a green redistribution source.

### FPL-Core-Insights enhanced 2025-26 layer

The cache also contains `players.csv`, `teams.csv`, and all 38 Premier League gameweek folders from FPL-Core-Insights. Each gameweek has player-match statistics, lineups, and matches. Its schema includes tackles, tackles won, interceptions, recoveries, blocks, clearances, headed clearances, duels, dribbled-past, fouls, dispossessions, defensive contributions, top speed, distance covered, and sprint count.

Those columns are useful evidence of what a future licensed feed should contain, but they are not all-role v1 training inputs. No explicit repository data license was found, underlying provider rights are unclear, and the previous audit found 293 missing block values among 11,492 enhanced player-match rows. Fifty-one players had a mixture of observed and missing block values, 22 had all observed-appearance block values missing, and eight eligible defenders reached the earlier unified cohort with affected season totals. In particular, some season block totals were numeric sums over incomplete match coverage. Schema presence does not establish a valid metric, unit, or complete denominator for speed and tracking fields either.

This source is red for model training, publication, redistribution, and commercial use until both rights and metric-specific completeness are resolved.

### ESPN profile enrichment

The EPL profile cache uses:

- `https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams?limit=100&season=2025`;
- `https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams/{team_id}/roster?season=2025`.

It supplies name, team, position, date of birth, height, and weight. The match is partial: only 1,398 of 4,005 current all-role rows have both height and weight, and fuzzy name/team matches require manual review. The snapshot was retrieved after 2025-26, so it cannot be treated as a dated physical measurement for earlier seasons. Public JSON access does not assert an open-data license.

### Wikidata CC0 physical fill

The rights-cleared physical fallback is now implemented through the [Wikidata Query Service](https://query.wikidata.org/sparql). It queries only canonical EPL identities with a known date of birth and accepts an entity only when an exact English label or alias and the exact birth date both match. It does not fuzzy-match names. Ambiguous entities, unrecognized units, implausible values, and entity-level height or mass conflicts greater than five metric units are quarantined.

The current audit has 990 queryable identities and accepts 692 Wikidata entities: 692 have a usable height and 265 have a usable mass. The merge fills only missing values and never overwrites ESPN. Across the 4,005 all-role EPL rows, height coverage rises to 2,326 (58.1%) and weight-plus-height coverage rises to 1,784 (44.5%). All Wikidata quantities remain explicitly labeled as community-maintained, undated profile facts—not annual or season-specific measurements.

Refresh the cache with an identifiable user agent, sequential batches, and `429`/`Retry-After` handling:

```text
uv run possession-lab enrich-epl-wikidata --root .
```

The raw responses and source sidecars remain ignored by Git; the aggregate audit is written to `reports/epl/wikidata_physical_enrichment.json`.

### FBref evaluation — rejected for model use

FBref was evaluated but no FBref data were ingested. The current [Sports Reference Terms of Use](https://www.sports-reference.com/termsofuse.html), section 5, item 11(ii), explicitly prohibits using site content to support machine-learning methods that predict, classify, label, or score model inputs. That describes this athlete-scoring project directly. A manual export would not remove the restriction.

FBref also no longer supplies the advanced soccer panel originally sought. In its [20 January 2026 announcement](https://www.sports-reference.com/blog/2026/01/fbref-stathead-data-update/), Sports Reference said its advanced soccer provider terminated the feed and required deletion of that data. The surviving basic league tables largely duplicate the current FPL core, while player-page height and weight are current, undated profiles rather than a seasonal physical series. FBref remains excluded unless written permission explicitly covers model training, derived scores, persistent caching, publication, portal display, and redistribution.

### EPL go/no-go

- **Go:** local broad-role research for GK/DEF/MID/FWD with clear proxy labels and source warnings.
- **No-go:** create recent CB/FB/WB/DM/CM/AM/wing/striker models from the current cache.
- **No-go:** train release models on FPL-Core defensive or speed fields until rights and metric-specific completeness are resolved.
- **Go:** use strict Wikidata CC0 matches to fill missing EPL height and weight while retaining QID, match evidence, provenance, and undated-profile labels.
- **No-go:** ingest FBref content into model training or scoring without explicit written permission covering this use.
- **No-go:** describe the ESPN or Wikidata profile snapshots as annual physical history or as full-league physical coverage.
- **No-go:** redistribute cached community/ESPN raw files or commercialize the model before upstream rights review.

## 9. Recommended soccer benchmarks and licensed path

Two sources are useful, but neither removes the need for a licensed recent EPL feed.

### Pappalardo/Wyscout historical benchmark — recommended, green

The [Soccer match event dataset on Figshare](https://doi.org/10.6084/m9.figshare.c.4415000) accompanies Pappalardo et al., [“A public data set of spatio-temporal match events in soccer competitions”](https://doi.org/10.1038/s41597-019-0247-7). It includes a full 2017-18 Premier League season alongside four other major domestic leagues, the 2018 World Cup, and Euro 2016. The data paper describes 1,941 matches, 3,251 players, and roughly three million events.

The individual Figshare Events (`10.6084/m9.figshare.7770599.v1`), Matches (`10.6084/m9.figshare.7770422.v1`), and Players (`10.6084/m9.figshare.7765196.v3`) items report CC BY 4.0. The dataset contains event/subevent, outcome tags, pitch positions, match/player/team IDs, period, event time, and player/team/match lookups. It is the best rights-cleared option here for testing spatial event engineering, possession-chain definitions, and historical reproducibility.

Use it as an explicitly historical benchmark. It does not validate a 2025-26 player's current role, does not provide a recent EPL cohort, and its player role metadata is not a complete modern granular deployment label.

### StatsBomb Open Data — conditional, custom terms

The official [StatsBomb/Hudl Open Data repository](https://github.com/hudl/open-data) provides competition, match, event, lineup, and selected StatsBomb 360 JSON. Its README permits selected data for public research and genuine football-analytics interest, and requires StatsBomb source attribution and logo use when publishing, sharing, or distributing analysis. The repository also includes a custom [StatsBomb Public Data User Agreement](https://github.com/hudl/open-data/blob/master/LICENSE.pdf); that full agreement must be accepted and recorded for the intended use.

The official `competitions.json` index checked on 22 October 2026 listed Premier League 2003-04 and 2015-16, not a recent Premier League season. StatsBomb Open Data can therefore be a conditional historical event/lineup benchmark, but it is not the source for a current granular EPL model.

### SkillCorner Open Data — recommended methodology benchmark, green

The official [SkillCorner Open Data repository](https://github.com/SkillCorner/opendata) is MIT-licensed and currently offers ten 2024-25 A-League matches plus season aggregates. It is not Premier League player truth, but it is the strongest open blueprint here for build-plus-playing-profile engineering. Its aggregate files provide:

- physical output: total distance and metres per minute; running, high-speed-running, sprint, and high-intensity distance/count; medium/high accelerations and decelerations; explosive acceleration into high-speed running/sprinting; time to reach high-speed running/sprinting; and PSV99/top-five peak speed, split in and out of possession;
- off-ball running: runs in behind, coming short, overlap/underlap, pulling wide or into the half-space, support and ahead-of-ball runs, plus whether each run was targeted, received, dangerous, or followed by a shot/goal within ten seconds;
- passing context: pass opportunities, attempts, completions, expected-pass values, line-breaking passes, passes targeting runs, and dangerous or difficult passes.

Use the published aggregates as a feature-definition and scaling benchmark, not as an EPL training cohort. The directly published files include [physical aggregates](https://raw.githubusercontent.com/SkillCorner/opendata/master/data/aggregates/aus1league_physicalaggregates_20242025.csv), [off-ball-run aggregates](https://raw.githubusercontent.com/SkillCorner/opendata/master/data/aggregates/aus1league_obraggregates_20242025.csv), and [passing aggregates](https://raw.githubusercontent.com/SkillCorner/opendata/master/data/aggregates/aus1league_passingaggregates_20242025.csv).

For recent CB/FB/WB/DM/CM/AM/wing/striker modeling, procure a licensed provider feed whose contract explicitly covers the required EPL seasons, event/lineup or tracking fields, derived models, publication, and portal use. Opta is the cleanest identity path because the current FPL profiles already contain `opta_code`; StatsBomb, Wyscout, SkillCorner, and Sportradar are viable alternatives if their delivered identifiers and permitted uses are recorded. The contract must explicitly allow model training, persistent caching, derived features, public aggregate results, portal display, and cross-sport scoring. Record the contract version and competition coverage in the source matrix before ingestion.

## 10. Prioritized acquisition roadmap

### Stage 0 — finish and validate the existing cache

1. Freeze the newly consumed NFL explosive-play, NBA shot/free-throw/foul, NHL shot/faceoff/penalty/Corsi, and EPL expected/defensive fields behind schema checks.
2. Keep unavailable historical fields as missing, publish season-by-season coverage, and add minimum-opportunity/reliability flags before percentile calculations.
3. Regenerate every `.source.json` sidecar and the central manifest after any refresh; do not add a source whose rights note is unresolved.

### Stage 1 — add green, reproducible enrichment

1. **NFL first:** add the [nflverse Next Gen Stats release](https://github.com/nflverse/nflverse-data/releases/tag/nextgen_stats), joined on `player_gsis_id`, for transferable decision, separation, movement-efficiency, and expectation-adjusted skill features.
2. **Cross-sport profiles (implemented for EPL):** use [Wikidata's supported access methods](https://www.wikidata.org/wiki/Help:Data_access) for CC0 height (`P2048`), mass (`P2067`), and birth date (`P569`). EPL now requires an exact English label or alias plus exact birth date, retains the QID and match evidence, and quarantines ambiguous or conflicting matches. Extend the same strict pattern to other sports only where it adds coverage. Treat values as community-maintained and undated.
3. **Soccer methods:** use [SkillCorner Open Data](https://github.com/SkillCorner/opendata) to define physical/off-ball/passing feature families and the [Pappalardo/Wyscout benchmark](https://doi.org/10.6084/m9.figshare.c.4415000) to validate possession-chain and spatial-event code. Neither is a current EPL cohort.

### Stage 2 — procure the missing high-value feeds

1. **EPL is the top licensing priority:** obtain recent event/lineup or tracking data for granular roles, defensive actions, pressures, carries, passing under pressure, off-ball runs, speed, distance, accelerations, and position/deployment. Prefer a feed joinable by `opta_code`; otherwise maintain a reviewed provider-ID crosswalk to `fpl:<code>`.
2. **NBA:** license hustle, tracking, matchup, lineup, and combine data. Keep both the existing ESPN ID and licensed `nba_player_id`; crosswalk by provider ID first, then exact name/date-of-birth evidence. Do not automate NBA.com endpoints.
3. **NHL:** license EDGE/tracking or a charting feed for skating speed/distance, zone activity, shot speed, entries/exits, pressure, and deployment. Join on `playerId`; retain MoneyPuck as the noncommercial outcome layer only if the planned use remains permitted.
4. **NFL:** procure charting/tracking only for gaps NGS cannot solve—defense, coverage, blocking, route assignment, and special teams—while keeping GSIS ID as the canonical key.

### Stage 3 — operationalize only after rights and quality gates pass

1. Build season-versioned crosswalks, unit dictionaries, expected-value definitions, and missingness reports before training.
2. Store licensed raw data outside any public repository; publish only contract-permitted aggregates, model artifacts, and attribution.
3. Run chronological and athlete-disjoint validation, freeze the final test season, and show opportunity-weighted uncertainty and abstentions in the portal.

Low-priority substitutes should not distract from these stages. [football-data.org](https://www.football-data.org/) is useful for fixtures and tables, but its free tier does not provide the player-level playing profile needed here and paid terms must be checked for retention/model rights. Unlicensed mirrors, direct FPL scraping, NBA.com automation, and NHL EDGE scraping are not acceptable shortcuts.

## 11. Mandatory go/no-go checklist

The following gates apply before any training run is called release-ready.

1. **Provenance:** every raw input has an exact URL, retrieval time, SHA-256, byte count, and source-use note; the central manifest reflects the latest downloads.
2. **Rights:** every required source is green for the proposed use, or written clearance records why an amber/red source is allowed. Raw data from a red source are never bundled.
3. **Identity and grain:** the canonical player-season key is unique; team stints and provider total rows cannot double count; unresolved joins are quarantined.
4. **Opportunity:** every rate has a complete denominator on the same event scope. Missing exposure is not zero exposure.
5. **Role evidence:** every modeled role is observed at the intended granularity and has enough eligible players. Unsupported roles abstain.
6. **Metric completeness:** missingness is checked per metric and game. A numeric season sum is not complete merely because it is non-null.
7. **Physical timing:** profile values and dated tests are separate. Annual-change claims require dated, season-valid measurements and protocol metadata.
8. **Leakage:** evaluation is athlete-disjoint and chronological, with 2025 frozen as the final test season. No future profile or performance data may enter earlier training features.
9. **Peer normalization:** performance percentiles use season and role peers. Undated physical values may receive a season-cohort profile percentile but never an “annual measurement” label.
10. **Cross-sport claim:** the unified score is a build-and-transferable-performance analogy or guestimate, not the probability that an athlete will successfully switch sports.
11. **Portal release:** show source attribution, evidence status, uncertainty, role sample size, missing-data warnings, and abstention reasons. Do not silently convert unavailable dimensions or outcomes to zero.

Passing these gates makes the analysis reproducible and honestly scoped. It does not by itself establish causal athletic potential, a universal mental-awareness measure, or validated sport-switch success.
