# 2025–26 cross-sport possession-winning data source audit

Prepared 30 September 2026; revised for a multi-season panel on 1 October 2026

## Executive conclusion

The project is feasible, but there is no single dataset that supplies every rostered player, current physical measurements, limb measurements, movement data, and possession-winning performance across the NFL, NBA, NHL, and elite soccer. The workable approach is a source stack for each sport, joined into a common longitudinal schema.

My recommended first-pass stack is:

| Sport | Roster universe | Possession-winning performance | Physical and movement data | Practical assessment |
|---|---|---|---|---|
| NFL | nflverse weekly rosters | nflverse weekly stats, advanced defense, snap counts, play-by-play, and participation | Roster height/weight plus historical combine and pro-day testing | Best starting sport: unusually complete, bulk-downloadable, and stable IDs; preserve separate FTN attribution and review upstream PFR rights |
| NBA | SportsDataverse game rosters/player core plus official NBA roster endpoints | NBA traditional, Hustle, defensive tracking, matchup, and speed/distance reports | NBA Draft Combine anthropometrics and drills | Excellent basketball detail, but NBA endpoints are undocumented and reuse restrictions require care |
| NHL | Official NHL bios, team rosters, and game roster spots | Official realtime/faceoff reports and play-by-play, enriched with MoneyPuck | NHL EDGE speed/distance plus sparse scouting-combine testing | Strong in-game skating layer; historical limb/testing coverage is sparse |
| Soccer | Premier League squads plus API-Football player/fixture records | API-Football for structured match/player statistics; official Premier League totals only as a validation reference unless permission is obtained | Height/weight from provider profiles and CC0 Wikidata enrichment | Premier League is the better primary cohort; no defensible free league-wide limb or tracking dataset exists |

For soccer, use the **Premier League as the primary league** and treat the 2025–26 Champions League as an optional second cohort. The Premier League gives a fixed 20-club, 380-match environment and more consistent role/opportunity comparisons. The Champions League has more clubs but unequal match counts and much stronger cross-league/team-strength effects. More importantly, UEFA's current terms expressly prohibit systematic collection and using UEFA content to train a model. There is no exact-season soccer source in this audit that is at once free, comprehensive, and clearly rights-cleared for model training.

The largest unavoidable gap is limb length. Arm length, hand size, wingspan, standing reach, and agility drills are useful for subsets of NFL and NBA players. They are sparse in hockey and essentially unavailable at league scale in soccer. **Leg length or inseam is not systematically published in any of the four leagues.** It should remain missing unless a verified measurement source is found; it should not be silently estimated from height.

## Revised multi-season scope

The 2025–26 audit is now the latest-season anchor, not the entire analysis dataset. The common panel will cover:

| Sport | Collection window | Final untouched predictive test |
|---|---|---|
| NFL | 2021–2025 | 2025 |
| NBA | 2021–22 through 2025–26 | 2025–26 |
| NHL | 2021–22 through 2025–26 | 2025–26 |
| Premier League | 2021–22 through 2025–26 | 2025–26 |

Use 2021–22 through 2023–24 for initial training, 2024–25 for validation/model selection, and 2025–26 for final testing. The completed 2025–26 season may also be used for descriptive rankings, but those descriptive features must be kept separate from the preseason predictive snapshot.

Physical values will be stored as dated measurement events. Height and limb dimensions may be carried forward with measurement-age flags; weight will use the closest reliable pre-season observation and will not automatically be treated as a genuine annual measurement. Combine tests remain historical tests, while in-game speed/distance remain season-specific performance measures.

The full statistical, data-model, temporal-validation, and implementation design is in the companion [Multi-season cross-sport possession-winning project roadmap](multi-season-project-roadmap.md).

## What “2025–26” means in each sport

| League | Season identifier to store | Coverage |
|---|---|---|
| NFL | 2025 | Regular season in 2025 plus postseason played in early 2026 |
| NBA | 2025-26 or API value 2025-26 | Regular season and, if desired, 2026 postseason as a separately flagged competition phase |
| NHL | 20252026 | Game type 2 for regular season; postseason must be requested separately |
| Premier League / UCL | 2025 or 2025/26, depending on source | Domestic or European season beginning in 2025 |

The 2025–26 seasons are complete as of this audit. Raw extracts should be snapshotted now, checksummed, and tagged with an access date because public endpoints and current-season community repositories can change.

## Source-status legend

- **Green — intended bulk/research source:** explicit download mechanism and a reasonably clear reuse basis, such as nflverse or a provider's designated download files.
- **Amber — public access with constraints:** public API/export or community release, but undocumented endpoints, noncommercial limits, underlying data rights, or unclear redistribution terms require attention.
- **Red — view/validation only:** terms prohibit scraping, systematic database creation, or model training. Do not use as an automated training feed without written permission.

“Publicly viewable” does not mean “openly licensed.” This audit identifies practical restrictions but is not legal advice. Recheck terms before publishing data, releasing a model, or commercializing an application.

---

# 1. NFL

For the active end-to-end collection, metric, modeling, QA, hidden-value, and cross-sport workflow, see the companion [NFL possession-creation and defensive-disruption archetype plan](nfl-possession-archetype-plan.md).

## Recommended core: nflverse

[nflverse-data](https://github.com/nflverse/nflverse-data) is the strongest free foundation in this project. Its main data license is [CC BY 4.0](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md). The 2025 releases were verified through Week 22 and cover all 272 regular-season games and 13 postseason games. That repository-level license should not be treated as automatically overriding separate FTN attribution/share-alike terms or upstream restrictions on PFR-derived snap, advanced-defense, and combine fields; keep those sources separately governed.

### Roster and identity tables

1. [2025 weekly rosters CSV](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2025.csv)
   - 46,849 player-week rows and 3,133 unique GSIS player IDs.
   - Fields include team, roster status, position, depth-chart position, jersey, date of birth, height, weight, college, experience, entry route, and draft information.
   - Use the union of weekly rosters, rather than a final-season roster, to capture players who were waived, traded, promoted, placed on injured reserve, or rostered briefly.
   - Primary join key: GSIS ID.
   - Documentation: [weekly rosters](https://nflreadr.nflverse.com/reference/load_rosters_weekly.html).

2. [Master players CSV](https://github.com/nflverse/nflverse-data/releases/download/players/players.csv)
   - 24,834 historical players.
   - Provides GSIS, PFR, ESPN, NFL/SMART, PFF, OTC, and other IDs alongside mostly stable biography fields.
   - This should be the identity crosswalk for NFL data.
   - Documentation: [players](https://nflreadr.nflverse.com/reference/load_players.html).

### Possession-winning and defensive performance

1. [2025 weekly player statistics](https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv)
   - 19,422 player-game rows and 2,024 players.
   - Key outcomes: solo and assisted tackles, tackles for loss, forced fumbles, sacks, QB hits, interceptions, passes defended, opponent-fumble recoveries, safeties, blocked kicks, return yards, and defensive touchdowns.
   - Join: player ID is the GSIS ID; game ID is also present.
   - Documentation: [player statistics](https://nflreadr.nflverse.com/reference/load_player_stats.html).

2. [2025 snap counts](https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_2025.csv)
   - 26,613 player-game rows and 2,189 players.
   - Defensive, offensive, and special-teams snaps and percentages.
   - Essential denominator for per-100-defensive-snap rates.
   - Join: PFR player ID and game ID.
   - Dictionary: [snap counts](https://nflreadr.nflverse.com/articles/dictionary_snap_counts.html).
   - This is PFR-derived. Review [Sports Reference’s upstream data-use policy](https://www.sports-reference.com/data_use.html) before using it for public/commercial model training.

3. [2025 PFR advanced defense release](https://github.com/nflverse/nflverse-data/releases/download/pfr_advstats/advstats_week_def_2025.csv)
   - 7,926 player-game rows and 944 defenders.
   - Targets, completions/yards/TD/YAC allowed, passer rating allowed, target depth, blitzes, hurries, QB hits, sacks, total pressures, combined tackles, missed tackles, and missed-tackle rate.
   - This is the best free bulk source in the stack for pressures and coverage opportunity.
   - Join: PFR player ID and game ID.
   - Documentation: [PFR advanced statistics](https://nflreadr.nflverse.com/reference/load_pfr_advstats.html).
   - Keep it as a conditional enrichment layer because Sports Reference’s upstream data-use policy places restrictions on AI/ML use; maintain a core model that can run without it.

4. [2025 play-by-play Parquet](https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2025.parquet)
   - 48,771 plays across all 285 games.
   - Contains down, distance, score, field position, time, EPA/WP, and player IDs for interceptions, sacks, half-sacks, QB hits, tackles for loss, tackles, forced fumbles, and recoveries.
   - Use this after the aggregate MVP to create leverage-adjusted outcomes and contextual opportunity features.
   - Documentation: [play-by-play](https://nflreadr.nflverse.com/reference/load_pbp.html).

5. [2025 participation data](https://github.com/nflverse/nflverse-data/releases/download/pbp_participation/pbp_participation_2025.csv)
   - 45,184 plays across all 285 games.
   - Player lists on the play, personnel/formation, defenders in the box, number of pass rushers, time to throw, play-level pressure, route, man/zone, and coverage type.
   - This is the best opportunity/context layer, but it comes from FTN. Preserve the required attribution “FTN Data via nflverse” and the separate **CC BY-SA 4.0** terms described in the [participation documentation](https://nflreadr.nflverse.com/reference/load_participation.html).

### Physical and testing data

1. Weekly rosters give listed height and weight.
   - Weight was present for all 3,133 unique 2025 rostered players in the audit.
   - Height was present for 2,974 players, or 94.9%.
   - Listed measurements are not necessarily re-measured in 2025.

2. [nflverse historical combine CSV](https://github.com/nflverse/nflverse-data/releases/download/combine/combine.csv)
   - 8,968 prospect records since 2000.
   - Height, weight, 40-yard dash, bench press, vertical jump, broad jump, three-cone, and short shuttle.
   - Join combine PFR ID to the master players PFR ID.
   - About 1,462 of the 3,133 players on a 2025 weekly roster matched this file.
   - It does not include arm length, hand size, wingspan, or the 10-yard split.
   - Dictionary: [combine fields](https://nflreadr.nflverse.com/articles/dictionary_combine.html).
   - This file is also PFR-derived and needs the same upstream-rights review.

3. Official NFL combine/profile data
   - The [NFL Combine Tracker](https://www.nfl.com/combine/tracker/) and individual player profiles can include height, weight, arm length, hand size, 40 time, 10-yard split, vertical, broad jump, cone, shuttle, bench, and—more recently—wingspan.
   - The site uses an undocumented backing API and short-lived browser authentication. It is not a stable public developer API. Treat it as an optional enrichment source, cache responsibly, and review [NFL terms](https://www.nfl.com/legal/terms/) before automating.
   - The community [NFL Draft Combine & Pro Day dataset](https://github.com/array-carpenter/nfl-draft-data) provides convenient 2007–2026 snapshots with arm, hand, sprint, agility, jump, bench, and recent wingspan fields. Its NFL person ID joins to nflverse SMART ID.
   - In the audit, the community coalesced file matched 1,865 of 3,133 rostered players; arm/hand were present for about 58.8% and wingspan for 9.6%.
   - The repository currently does not present a clear data reuse license. Use it for research/prototyping or reproduce the extraction with permission rather than treating it as a redistributable production asset.

### Best initial NFL features

- Pressures per 100 defensive snaps.
- Sack and QB-hit conversion per pressure.
- Interceptions plus passes defended per coverage target.
- Forced fumbles per tackle opportunity or defensive snap.
- Tackle-for-loss rate and missed-tackle rate.
- Yards, YAC, touchdowns, and passer rating allowed per target.
- Takeaway EPA and third-/fourth-down disruption EPA.
- Role indicators from position, depth position, alignment/personnel, box count, pass-rush participation, and man/zone coverage.

### NFL gaps

- No free, comprehensive 2025 in-game top-speed dataset for every defender. Combine 40 and 10-yard split are the consistent substitutes.
- Raw league-wide Next Gen Stats tracking is not publicly downloadable, even though the league collects tracking for every player on every play. See [NFL Football Operations' tracking overview](https://operations.nfl.com/game-operations-logistics/technology/performance-tracking-data-next-gen-stats).
- The [2026 Big Data Bowl](https://www.kaggle.com/competitions/nfl-big-data-bowl-2026-analytics/overview) is useful for designing spatial/reaction features, but its public sample is from earlier tracking data and is not a full 2025-season feed.
- Leg length/inseam is not systematically published.
- Combine participation and drill completion are non-random. Store a “tested/not tested/unknown” flag and the measurement year rather than treating missing as poor performance.
- Pressure definitions differ among PFR, NGS, PFF, and SIS. Use one definition within a model.

---

# 2. NBA

## Roster and biography

Use two layers:

1. **SportsDataverse/ESPN releases for a reproducible bulk roster and box-score foundation**
   - [2025–26 player core Parquet](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_player_core/player_core_2026.parquet)
   - [2025–26 per-game rosters Parquet](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_game_rosters/game_rosters_2026.parquet)
   - [2025–26 player box scores Parquet](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_player_boxscores/player_box_2026.parquet)
   - [2025–26 play-by-play RDS](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_pbp/play_by_play_2026.rds)
   - [2025–26 NBA player crosswalk](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nba_crosswalk/nba_player_crosswalk_2026.parquet)
   - In this repository, season 2026 means the 2025–26 NBA season.
   - The verified files contained 591 player-core records, including nine players who never appeared, and 1,326 games from 21 October 2025 through 13 June 2026. Height, weight, and date of birth were populated for all 591 core records.
   - The crosswalk is not complete: only 395 of 544 ESPN players in the audited crosswalk had an NBA ID. Audit unmatched rows using normalized name plus date of birth plus team; never join on name alone.
   - The repository's software is open, but that does not automatically grant redistribution rights to the underlying ESPN data.

2. **Official NBA Stats endpoints for the canonical NBA player ID and official fields**
   - [PlayerIndex client definition](https://github.com/swar/nba_api/blob/master/src/nba_api/stats/endpoints/playerindex.py)
   - [CommonTeamRoster documentation](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/commonteamroster.md)
   - [CommonPlayerInfo documentation](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/commonplayerinfo.md)
   - Query season 2025-26 and league 00, union all 30 team rosters, and retain NBA PLAYER_ID as the canonical key.
   - Fields include team, position, jersey, roster status, height, weight, date of birth, country, school, experience, and draft information.

To capture “everyone rostered,” keep the SportsDataverse per-game roster history and a player-team-date bridge. A single end-of-season team roster loses ten-day contracts, traded players, two-way players, and players waived earlier in the year.

## Possession-winning and defensive performance

1. [NBA traditional player statistics](https://www.nba.com/stats/players/traditional?Season=2025-26&SeasonType=Regular+Season)
   - Endpoint documentation: [LeagueDashPlayerStats](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/leaguedashplayerstats.md) and [PlayerGameLogs](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/playergamelogs.md).
   - Steals, blocks, defensive rebounds, personal fouls, turnovers, minutes, and games.
   - Request totals and derive per-minute/per-possession measures consistently rather than mixing display modes.

2. [NBA Hustle statistics](https://www.nba.com/stats/players/hustle)
   - Endpoint documentation: [LeagueHustleStatsPlayer](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/leaguehustlestatsplayer.md).
   - Deflections, charges drawn, contested two- and three-point shots, offensive/defensive loose balls recovered, box-outs, minutes, and games.
   - This is the most directly relevant NBA table for the possession-winning archetype.

3. [NBA defensive tracking](https://www.nba.com/stats/players/defense-dash-overall)
   - Endpoint documentation: [LeagueDashPtDefend](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/leaguedashptdefend.md).
   - Defended FGM/FGA/FG%, normal FG%, differential, frequency, and shot-distance categories.

4. Matchup data
   - [LeagueSeasonMatchups](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/leagueseasonmatchups.md)
   - [BoxScoreMatchupsV3](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/boxscorematchupsv3.md)
   - Defender/offensive-player IDs, partial possessions, matchup minutes, switches, turnovers, blocks/help blocks, shooting fouls, and defended shooting.
   - Matchup assignment is model-derived and should be treated as an estimate, not perfect ground truth.

5. Speed and distance
   - [LeagueDashPtStats](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/leaguedashptstats.md), using the SpeedDistance measure.
   - Offensive, defensive, and total miles plus average speeds.
   - The public feed does not provide league-wide raw tracking or player top speed. Average defensive speed and combine sprint/agility are the public substitutes.

## NBA Draft Combine physical layer

- [Official combine anthropometrics page](https://www.nba.com/stats/draft/combine-anthro?SeasonYear=2025-26)
- [DraftCombineStats documentation](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/draftcombinestats.md)
- [DraftCombinePlayerAnthro documentation](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/draftcombineplayeranthro.md)
- [DraftCombineDrillResults documentation](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/draftcombinedrillresults.md)

Available fields include:

- Height with and without shoes.
- Weight and body-fat percentage.
- Wingspan and standing reach.
- Hand length and hand width.
- Standing and maximum vertical jump.
- Lane agility and modified lane agility.
- Three-quarter-court sprint.
- Bench press.

Join on NBA PLAYER_ID when present and retain combine year. Older records may require a reviewed name/draft-year crosswalk. The NBA describes an archive of approximately 1,795 athletes over 25 years, but not every active player attended or completed every measurement; see the [NBA combine overview](https://api-hub.nba.com/news/nba-draft-combine-overview-2026).

The NBA combine does not systematically provide separate arm length or leg/inseam length. Wingspan-minus-height, wingspan/height, standing-reach residual, and hand-size ratios are defensible derived morphology features if clearly labeled.

## Best initial NBA features

- Steals, deflections, blocks, loose-ball recoveries, and charges per 100 possessions or per 36 minutes.
- Steals per deflection and recovered defensive loose balls per opportunity, where denominators are available.
- Contested shots and defended-shot differential, separated by shot distance.
- Defensive rebound percentage rather than raw defensive rebounds.
- Matchup turnovers/blocks and opponent shooting differential, with shrinkage for small samples.
- Defensive fouls and team/opponent turnovers as decision-cost controls.
- Average defensive speed and distance per minute as work-rate features, not “reaction speed.”

## NBA access and rights caveats

- The widely used nba_api package is a community client for NBA website endpoints, not an official supported developer API.
- [NBA Terms of Use](https://www.nba.com/termsofuse) allow limited private, noncommercial use with attribution but restrict creating a comprehensive, regularly updated database without permission.
- The [NBA Stats FAQ](https://www.nba.com/stats/help/faq) does not offer a general official bulk-download right.
- Use conservative request rates, cache raw responses, retain provenance, and obtain permission before a public/commercial database or product.
- Do not substitute Basketball Reference as an automated modeling feed: [Sports Reference's data-use rules](https://www.sports-reference.com/data_use.html) expressly restrict automated extraction and machine-learning use.

---

# 3. NHL

The detailed [NHL puck-winning and defensive-disruption archetype plan](nhl-possession-archetype-plan.md) is retained as a future-sport reference. The NFL is the active first implementation.

## Official NHL Stats REST reports

The endpoints below require no API key. Use season ID 20252026, regular-season game type 2, and request all rows. NHL player ID is the canonical join key.

1. [Skater bios](https://api.nhle.com/stats/rest/en/skater/bios?isAggregate=true&isGame=false&limit=-1&cayenneExp=seasonId=20252026%20and%20gameTypeId=2)
   - The verified report returned 940 skaters who played in 2025–26.
   - Player ID, height, weight, date of birth, position, shoots/catches, nationality, draft year/round/overall, and games played.
   - Pull the corresponding goalie bios/roster records as well if “all rostered players” is literal, but keep goalies outside the skater possession-winning model or model them as a separate role family.

2. [Realtime statistics](https://api.nhle.com/stats/rest/en/skater/realtime?isAggregate=true&isGame=false&limit=-1&cayenneExp=seasonId=20252026%20and%20gameTypeId=2)
   - Takeaways, giveaways, hits, blocked shots, shot attempts blocked, total shot attempts, time on ice, and supplied per-60 rates.

3. [Faceoff percentages](https://api.nhle.com/stats/rest/en/skater/faceoffpercentages?isAggregate=true&isGame=false&limit=-1&cayenneExp=seasonId=20252026%20and%20gameTypeId=2)
   - Faceoff counts and win percentages by offensive, neutral, and defensive zone and by even-strength, power-play, and short-handed state.

4. [Penalties](https://api.nhle.com/stats/rest/en/skater/penalties?isAggregate=true&isGame=false&limit=-1&cayenneExp=seasonId=20252026%20and%20gameTypeId=2)
   - Penalties taken/drawn, net penalties, penalty types, and per-60 rates.

5. [Puck-possessions report](https://api.nhle.com/stats/rest/en/skater/puckPossessions?isAggregate=true&isGame=false&limit=-1&cayenneExp=seasonId=20252026%20and%20gameTypeId=2)
   - SAT/Corsi and USAT/Fenwick percentages, individual attempt rates, five-on-five faceoff percentage, and zone starts.
   - Despite the report name, it does not give player-held puck duration, puck-battle wins, entries/exits, or pressure events.

6. [Goals for/against](https://api.nhle.com/stats/rest/en/skater/goalsForAgainst?isAggregate=true&isGame=false&limit=-1&cayenneExp=seasonId=20252026%20and%20gameTypeId=2)
   - On-ice goals and time by manpower state.

The [NHL Stats interface](https://www.nhl.com/stats/skaters?report=realtime&reportType=season&seasonFrom=20252026&seasonTo=20252026&gameType=2) also provides a manual export.

## Rosters, games, events, and shifts

Official public web endpoints include:

~~~text
https://api-web.nhle.com/v1/roster/{TEAM}/20252026
https://api-web.nhle.com/v1/player/{PLAYER_ID}/landing
https://api-web.nhle.com/v1/club-schedule-season/{TEAM}/20252026
https://api-web.nhle.com/v1/gamecenter/{GAME_ID}/play-by-play
https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={GAME_ID}
~~~

The 2025–26 play-by-play contains player IDs, state, time, zone, and rink coordinates for faceoffs, hits, giveaways, takeaways, blocked shots, shots, and penalties. It can support defensive-zone takeaways, block-location measures, manpower splits, and event-sequence features. Game records also contain roster spots; union them across games to capture everyone who dressed.

A season roster endpoint is a snapshot, not a complete history. Add the [official 2025–26 opening-day roster release](https://www.nhl.com/news/2025-2026-nhl-opening-day-rosters-announced). Even then, there is no clean official public record of every healthy scratch, injured-list membership, and call-up through the whole season. Flag this as a roster-universe limitation.

The endpoints are official infrastructure but undocumented. [Zmalski's community NHL API reference](https://github.com/Zmalski/NHL-API-Reference) is the most useful technical index. [NHL Terms of Service](https://www.nhl.com/info/terms-of-service) limit unauthorized automated compilation and generally restrict NHL content to personal, informational, noncommercial use. Obtain permission for a public or commercial product.

## NHL EDGE: the best public in-game athletic layer

Official endpoint patterns:

~~~text
https://api-web.nhle.com/v1/edge/skater-detail/{PLAYER_ID}/20252026/2
https://api-web.nhle.com/v1/edge/skater-comparison/{PLAYER_ID}/20252026/2
~~~

Useful fields:

- Maximum skating speed.
- Bursts above 22 mph, between 20–22 mph, and between 18–20 mph.
- Total skating distance and distance per 60.
- Maximum distance in a game and a period.
- Maximum and average shot speed.
- Puck-zone-time percentages and zone starts.
- League averages and position percentiles.

The NHL says EDGE covers every NHL player and club from 2021–22 onward; see the [official EDGE description](https://www.nhl.com/news/nhl-edge-advanced-stats-section-brings-fans-closer-to-game).

Important interpretation:

- Query one player at a time; there is no supported bulk CSV.
- Public EDGE does not expose raw player/puck XY tracking, acceleration, reaction time, player-held puck duration, puck battles, pressures, entries, or exits.
- Zone time describes where the puck is while the player is on the ice, not possession by that player.
- Maximum speed is noisy as an extreme value. Bursts per 60 and distance per 60 are more stable workload/mobility features.

## MoneyPuck advanced-statistics layer

MoneyPuck expressly lists complete 2025–26 downloads:

- [2025–26 skater season CSV](https://www.moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/skaters.csv)
- [2025–26 skater game-level ZIP](https://peter-tanner.com/moneypuck/downloads/seasonPlayersSummary/skaters/2025.zip)
- [Player biography lookup](https://www.moneypuck.com/moneypuck/playerData/playerBios/allPlayersLookup.csv)
- [2025–26 shot-level ZIP](https://peter-tanner.com/moneypuck/downloads/shots_2025.zip)
- [Download page and dictionary](https://www.moneypuck.com/data.htm)

The season file includes NHL player ID, player/team/position/situation, games, ice time, shifts, hits, takeaways, giveaways, defensive-zone giveaways, blocks, faceoffs, penalties, zone starts/ends, and extensive on-/off-ice Corsi, Fenwick, shot, danger, goal, and expected-goal measures. Keep “all” and “5-on-5” situation rows separate; do not sum overlapping situations.

The verified shot file contained 119,271 2025–26 shots with 124 attributes, including coordinates, preceding-event context, shift duration, xG, and rebound/freeze probabilities. It excludes blocked shots, which must come from the skater file or NHL play-by-play.

MoneyPuck is free for noncommercial use with attribution and asks users to use designated downloads rather than scraping other pages. Review its [license/access notes](https://www.moneypuck.com/data.htm).

## NHL Scouting Combine

- [Official all-time combine leaderboards](https://records.nhl.com/draft/combine/bench-press)
- [Official 2025 top-25 results PDF](https://media.nhl.com/site/vasset/public/attachments/2025/06/19060/2025ScoutingCombine_FitnessTestingResults_060725_FINAL.pdf)

The records site covers eight leaderboard categories, including bench-press power, pull-ups, horizontal jump, force-plate vertical jump, pro agility, grip strength, Wingate cycling, and VO2 max. The annual PDF adds wingspan and test variants.

This source is highly selective. Ninety prospects attended in 2025, but only the top 25 per test were published. It is not a complete participant dataset, and coverage among current NHL players is sparse. Arm length, leg length/inseam, and standing reach are not available at league scale. Treat combine data as optional enrichment with explicit missingness flags.

## Best initial NHL features

- Takeaways and giveaways per 60.
- Takeaway-to-giveaway balance, while retaining the components.
- Blocks per opponent shot attempt while on ice.
- Hits per 60, separated from takeaways because hits do not necessarily regain possession.
- Faceoff win probability by zone and manpower state.
- Five-on-five on-ice xGA/60, Corsi/Fenwick against, high-danger attempts against, and relative-to-teammate effects.
- Defensive-zone starts and time on ice as opportunity/context controls.
- EDGE speed bursts/60 and skating distance/60.
- Penalties taken/drawn as decision-cost and aggression controls.

Takeaways, giveaways, and hits are scorer-recorded and can have rink effects. Include venue/team controls or scorer-bias adjustments.

---

# 4. Soccer: Premier League primary, UCL secondary

## Recommended acquisition source: API-Football

[API-Football](https://www.api-football.com/) is the most practical low-cost structured feed found for a 2025–26 Premier League build. It is preferable to scraping a stats website, though its terms do not grant competition publication rights.

Use the provider's competition lookup to confirm IDs; the commonly used IDs are Premier League 39 and Champions League 2, with season 2025.

Core requests:

~~~text
GET https://v3.football.api-sports.io/players?league=39&season=2025&page={PAGE}
GET https://v3.football.api-sports.io/fixtures?league=39&season=2025
GET https://v3.football.api-sports.io/fixtures/players?fixture={FIXTURE_ID}
~~~

The player profile supplies provider player ID, name, age/date context, nationality, height, weight, photo/status, and team-season statistics. Player and fixture-player statistics can include:

- Appearances, starts, minutes, position, rating.
- Tackles, blocks, interceptions.
- Duels attempted/won and dribble-related fields.
- Fouls and cards.
- Passes and passing accuracy.
- Goals, assists, shots, and goalkeeper measures.

This feed is sufficient for an initial model using tackles, interceptions, blocks, duel success, minutes, fouls, and position. Check response coverage flags and field completeness before committing to a schema; API coverage can vary by competition and field.

It does not supply the fields needed for a full physical/pressing layer: no ball recoveries, pressure events, top speed, distance covered, wingspan, arm length, or leg length. Confirm the provider's competition/season coverage flags before extraction.

[Current pricing](https://www.api-football.com/pricing/) lists a free tier with 100 requests/day and all endpoints, but the free tier is limited in available seasons and the public page does not enumerate which seasons are included. The Pro tier is currently $19/month with 7,500 requests/day. Treat exact 2025 access as paid unless the account dashboard confirms otherwise. A player response contains 20 players per page, so the Premier League takes at least 25 player calls before fixtures; one request per fixture for detailed player lines adds roughly 380 calls.

[API-Football's terms](https://www.api-football.com/terms) allow users to build applications/projects and prohibit direct resale of the raw data. They also explicitly say the provider does not grant publication/commercial rights in the underlying competitions and that the user must obtain any required league/federation permission. Therefore:

- Good for a private research prototype and internal model, subject to the subscription terms.
- Do not redistribute the raw feed.
- Contact the provider and relevant rights holder before public/commercial release.

## Official Premier League sources: excellent validation, restricted training feed

- [2025–26 player directory](https://www.premierleague.com/en/players?competition=8&season=2025)
- [2025–26 opening squad lists](https://www.premierleague.com/en/news/4407896)
- [2025–26 updated squad lists](https://www.premierleague.com/en/news/4580687/202526-premier-league-squad-lists)
- [Official statistics definitions](https://www.premierleague.com/en/stats/clarification)

The official statistics catalogue confirms player-level minutes, tackles, tackle success, last-man tackles, blocks, interceptions, clearances, headed clearances, recoveries, duels won/lost, aerial battles, errors, fouls, and other fields. The League states that Opta collects and quality-checks the data.

The current site uses undocumented JSON endpoints behind its pages. A useful community description is [this reverse-engineered API reference](https://github.com/DanielTomaro13/football-invincibles/blob/main/PREMIER_LEAGUE_API.md), including competition 8 and season 2025. It describes player, squad, player-stat, and leaderboard endpoints. This is not an official developer API and can change without notice.

[Premier League terms](https://www.premierleague.com/en/terms-and-conditions) permit limited personal use but restrict systematic reuse and creating a database from site/app content without permission. The correct use here is:

- Use official squad releases to define and audit the player universe.
- Use manually viewed official totals to spot-check the provider feed.
- Do not build the training dataset by scraping the Premier League site or its undocumented API unless the League grants permission.

The Premier League identifies Opta/Stats Perform as its match-data collector and directs match-data and fixture-feed licensing enquiries through Football DataCo; see its [official data-source and permission note](https://www.premierleague.com/en/news/102426).

## Official Fantasy Premier League API

The current-season FPL service exposes undocumented endpoints such as the bootstrap, fixtures, gameweek-live, and player-summary feeds. They supply FPL IDs/codes, team/role, starts/minutes, fantasy totals, expected-goal fields, and a 2025–26 defensive-contribution aggregate, but not player height/weight or clean raw tackle/interception/recovery events.

It is not a historical API: the service rolls forward to the current season, so 2025–26 requires a previously frozen snapshot. [FPL terms](https://fantasy.premierleague.com/help/terms) restrict automated extraction and unauthorized use of game data. Treat FPL as an identity/reference aid, not a safe historical bulk modeling feed.

## Community 2025–26 Premier League release

[FPL-Core-Insights](https://github.com/olbauday/FPL-Core-Insights) provides convenient 2025–26 CSVs aligned to Fantasy Premier League player IDs. Its player-match tables include minutes, tackles/attempts/wins, interceptions, recoveries, blocks, clearances, headed clearances, dribbled-past events, ground/aerial duels, fouls, passing, touches, and expected-goal measures. Its own [data integration audit](https://github.com/olbauday/FPL-Core-Insights/blob/main/DATA_INTEGRATION_REVIEW.md) reports complete Premier League coverage of 380 matches and 12,754 player-match rows.

It is attractive for rapid prototyping, but it should not be the sole production source:

- Underlying field provenance and redistribution rights are not sufficiently clear for all columns.
- Some speed/distance fields were reportedly discontinued after a source requested that collection stop.
- The repository has no standard LICENSE file; informal permission in a README would not license embedded provider data in any event.
- Validate aggregates against the official Premier League display and treat the dataset as community-maintained.
- Its 2025–26 UCL coverage is partial: the repository audit reports 64 UCL fixture rows but detailed files for only 48, so do not call it a comprehensive UCL dataset.

## Physical profile enrichment

1. API-Football player profiles: height and weight, with varying completeness.
2. Premier League player pages: height/weight for many players, but use only within the site's permitted scope.
3. [Wikidata data access](https://www.wikidata.org/wiki/Wikidata:Data_access): date of birth, nationality, height, mass, position, club, and external IDs for a subset of players. Wikidata structured data is [CC0](https://www.wikidata.org/wiki/Wikidata:Licensing), making it useful as a lawful enrichment/crosswalk source, but coverage and freshness must be audited.

There is no credible free 2025–26 Premier League dataset of wingspan, arm length, standing reach, hand size, or leg/inseam length. Do not use fan-edited physical values without source-level verification.

There is also no freely licensed league-wide 2025–26 top-speed or raw tracking feed. If top speed is essential, the realistic choices are a licensed Opta/Stats Perform, SkillCorner, Second Spectrum, or similar commercial feed—or omitting that field from the soccer production model.

## UEFA Champions League

- [2025–26 competition/player statistics](https://www.uefa.com/uefachampionsleague/history/seasons/2026/statistics/players/) include minutes, top speed, distance covered, tackles won/lost, balls recovered, blocks, clearances, passing, possession-time, run, foul, and card views. UEFA player profiles also display height and weight.
- There is no documented public bulk API or export.

However, [UEFA's terms](https://www.uefa.com/termsconditions/) expressly prohibit systematic collection, automated scraping, creating a database, and using UEFA content to develop or train software, models, algorithms, or AI systems. UEFA.com should therefore be **view/validation only** unless written permission is obtained. API-Football can supply a UCL cohort under the provider agreement, while still requiring an underlying-rights review for publication/commercial use.

## Open datasets for soccer feature design—not the target season

These are valuable for developing spatial-awareness and reaction-style features before licensed Premier League tracking is available:

1. [SkillCorner Open Data](https://github.com/SkillCorner/opendata)
   - Ten 2024–25 Australian A-League matches with 10 Hz broadcast-derived player/ball tracking, lineups, dynamic events, and phase-of-play files.
   - Season aggregates include physical, off-ball-run, and passing measures.
   - Tracking has possession labels; dynamic events include pressure, space constraint, reception difficulty, time to impact, and expected-possession-value fields.
   - Two matches add 29-joint 3D body-pose samples.
   - Identity accuracy is reported at about 97%, and speed/acceleration require smoothing.
   - Excellent development data for algorithms; not a substitute for 2025–26 Premier League outcomes.
   - The repository has an [MIT license](https://github.com/SkillCorner/opendata/blob/master/LICENSE). Do not assume third-party uploads of Premier League/UCL tracking are authorized merely because an uploader applies an open label.

2. [StatsBomb Open Data](https://github.com/hudl/open-data)
   - Rich event data and selected 360 context for chosen competitions/seasons.
   - Does not contain a comprehensive 2025–26 Premier League or Champions League season.
   - Useful for prototyping pressure, possession-value, and spatial-context features with the required attribution.
   - It uses a [custom data license](https://github.com/hudl/open-data/blob/master/LICENSE.pdf), not a generic open-source software license; review attribution, publication, and redistribution conditions.

3. [Metrica Sports sample data](https://github.com/metrica-sports/sample-data)
   - A small synchronized event/tracking sample for testing movement pipelines.

## Best initial soccer features

- Tackles won, interceptions, blocks, recoveries, and clearances per 90.
- Prefer opponent-possession or opponent-touch denominators when available.
- Duel and aerial-duel win rates, with minimum-opportunity shrinkage.
- Fouls and cards per defensive action as decision-cost measures.
- Dribbled-past rate as a negative outcome.
- Turnovers/dispossessions and passing under pressure as ball-security controls.
- Position and role bands more granular than DEF/MID/FWD where reliable.
- Team possession, defensive line/team style, score state, and strength of opposition as contextual controls.

Do not call total tackles or distance covered “pressing.” A true pressure metric needs an event definition or tracking-based time/distance-to-ball rule.

---

# 5. Physical-data availability matrix

| Attribute | NFL | NBA | NHL | Premier League / UCL |
|---|---|---|---|---|
| Height and weight | Near-complete weekly roster data | Near-complete roster/player-core data | Official bios for players who appeared | Often available through profiles/providers; audit missingness |
| Date of birth / age | Strong | Strong | Strong | Generally strong |
| Arm length | About 59% of 2025 roster via modern combine/pro-day community snapshot; official source possible | Not a standard separate combine field | Not systematic | Not systematic |
| Wingspan | Recent/sparse, about 10% in audited community snapshot | Strong for combine attendees, not all active players | Very sparse annual top-performer publication | Not systematic |
| Standing reach | Not standard | Combine attendees | Not systematic | Not systematic |
| Hand length/width | Combine subsets | Combine attendees | Grip strength only for sparse combine leaders | Not systematic |
| Leg length/inseam | No systematic source | No systematic source | No systematic source | No systematic source |
| Sprint testing | 40, 10-yard split, shuttle/cone for combine/pro-day subsets | Three-quarter sprint and agility for combine subsets | Sparse pro-agility testing | No standardized league combine |
| Jump/power | Vertical, broad, bench | Vertical, bench | Sparse jump/Wingate/power testing | No standardized public league testing |
| In-game speed | No complete public defensive feed | Public average speed/distance, not raw top speed | EDGE max speed, bursts, and distance | No freely licensed complete 2025–26 feed |
| Raw player tracking | Sample competitions only, not full 2025 | Not public league-wide | Not public league-wide | Only small non-target open samples |

Recommended additional physical features:

- BMI only as a descriptive size ratio; do not interpret it as body composition.
- Height/weight residual within role.
- Wingspan-to-height and wingspan-minus-height.
- Standing-reach residual after height.
- Hand-size-to-height.
- Sprint momentum: mass × speed, clearly labeled as a combine proxy.
- Burst/power composites from jump, sprint, and mass, with protocol-specific normalization.
- Measurement age and years since measurement.
- Preferred foot/hand, shooting side, or handedness.

Never merge measurements from different protocols into one raw field without a source/protocol indicator.

---

# 6. A common possession-winning framework

Raw events are not directly comparable across sports. A sack, a steal, a takeaway, and a tackle are different events with different opportunities. The ensemble should consume comparable **latent dimensions**, each calculated within a sport first.

| Shared dimension | NFL examples | NBA examples | NHL examples | Soccer examples |
|---|---|---|---|---|
| Direct takeaway creation | Interceptions, forced fumbles, recoveries | Steals, some loose-ball recoveries | Takeaways, faceoff wins | Interceptions, recoveries, tackles that win possession |
| Disruption without immediate possession | Pressures, hits, passes defended, TFL | Deflections, blocks, contests, charges | Blocks, hits, stick/shot disruption where available | Blocks, clearances, pressures where genuinely measured |
| Opportunity | Defensive snaps, rush snaps, coverage targets | Possessions, minutes, matchup possessions | TOI, shifts, zone starts, opponent attempts | Minutes, opponent possession/touches, defensive phases |
| Conversion/accuracy | Sacks or hits per pressure; tackle success | Steals per deflection; defended-shot impact | Takeaways versus giveaways; faceoff probability | Tackle/duel success; recovery following action |
| Decision cost | Missed tackles, penalties, yards/TD allowed | Fouls, missed rotations proxies, opponent efficiency | Giveaways, penalties | Fouls, cards, dribbled-past events |
| Range/work rate | Sprint tests and participation context | Defensive distance and average speed | Speed bursts and distance/60 | Tracking distance/sprints when licensed |
| Contextual defensive value | EPA prevented/residual | Opponent efficiency residual | xGA/Corsi residual | xThreat/EPV prevented or possession-value residual |

Recommended first shared indices:

1. **Disruption frequency**
   - Within-sport percentile of possession-affecting actions per relevant opportunity.
2. **Conversion quality**
   - Probability that a pressure/contest/duel becomes a sack, turnover, stopped shot, or recovered possession.
3. **Range and repeatability**
   - Movement/workload measures plus game-to-game consistency, adjusted for playing time.
4. **Ball security / decision cost**
   - Negative events per opportunity, oriented so higher is better.
5. **Context-adjusted defensive value**
   - Out-of-sample residual after accounting for role, usage, team, opposition, zone/field position, and score/game state.

Normalize each component within **sport × season × role group** using a robust z-score or percentile, then combine the standardized dimensions. Do not directly pool raw counts.

---

# 7. “Mental” and game-awareness variables

The proposed concepts are worthwhile, but the names should follow what the data actually measures.

## Accuracy

Use observable, sport-specific definitions:

- NFL: tackle success, pressure-to-hit/sack conversion, ball production per target.
- NBA: recovered loose balls, steal conversion from deflections, opponent shot-quality/efficiency change.
- NHL: faceoff probability, takeaways net of giveaways, blocks per opponent attempt.
- Soccer: tackle/duel success, possession recovered after challenge, interceptions per opponent possession.

Create a shared “execution accuracy” percentile from those within-sport measures.

## Reaction speed

Box scores cannot measure neurological reaction time. Call the first version **response speed** or **time-to-impact** and only calculate it from tracking/event timestamps:

1. Define a trigger, such as pass release, change of possession, quarterback dropback, or ball-handler receiving the ball.
2. Detect the defender's first sustained movement toward the threat.
3. Measure reaction latency, time to close, closing velocity, and path efficiency.
4. Control for initial distance, angle, role assignment, and whether the player could see the trigger.

SkillCorner's open time-to-impact and tracking sample is appropriate for developing this logic. Full target-league production requires licensed tracking. Combine sprint/agility is an athletic proxy, not reaction time.

## Spatial awareness / anticipation

A defensible initial metric is an out-of-sample **anticipation residual**:

- Model the expected probability/value of a disruption from starting position, role, opponent action, game state, and team structure.
- Compare the player's actual disruption/value to that expectation.
- Estimate on a held-out period so the feature does not merely memorize the target.
- Apply empirical-Bayes shrinkage for players with few opportunities.

This remains partly tactical and coaching-driven; it should not be labeled innate “intelligence.” Coach review can validate whether the metric captures reading the play, assignment quality, or scheme.

---

# 8. Canonical data model

Use long tables rather than one very wide spreadsheet.

## player

- global_player_key
- sport, league
- canonical source ID
- all source-specific IDs
- normalized and display names
- date of birth, nationality
- primary/secondary position and role group
- preferred hand/foot/shooting side

## roster_spell

- player key, team key
- effective start/end date or week/game
- roster/registration status
- jersey and listed position
- source and retrieved timestamp

## measurement

- player key
- measurement type
- numeric value and unit
- measurement date/year and age
- protocol: combine, pro day, roster listing, in-game tracking, etc.
- source, raw source field, reliability tier
- measured / derived / imputed flag

## player_game

- player, game, team, opponent
- role/position, starter/substitute
- minutes, snaps, TOI, possessions, shifts, targets, rushes, or another sport-specific opportunity denominator
- raw possession-winning and negative events
- context fields: score state, field/zone, strength state, team possession, opposition strength

## player_season

- transparent aggregates derived from player_game
- provider aggregates kept separately for audit
- rates with numerator and denominator retained
- uncertainty interval and sample-size flag

## source_registry

- source name and URL
- terms/license URL and version/access date
- access method and rate limit
- season meaning and coverage
- raw-file checksum
- attribution text
- redistribution/training/publication restrictions

## Identity rules

- NFL: GSIS ID as primary; bridge PFR ID and NFL SMART/person ID through nflverse players.
- NBA: NBA PLAYER_ID as primary; retain ESPN ID and audited crosswalk.
- NHL: official NHL player ID.
- Soccer: create a crosswalk among API-Football ID, Premier League/FPL code, UEFA ID if used only for reference, and Wikidata QID. Match automatically only with a high-confidence combination such as normalized name + date of birth + club; review collisions and transfers.

Never use player name alone as a durable key.

---

# 9. Collection and quality-control plan

## Phase 1 — freeze source and rights decisions

1. Decide whether this remains private academic/noncommercial research or is intended for public/commercial use.
2. Record terms and attribution requirements before collection.
3. Exclude UEFA.com, PremierLeague.com, and Sports Reference automated feeds unless permission is obtained.

## Phase 2 — build the full roster universes

Repeat the roster process for every target season, retaining effective dates:

1. NFL: union weekly rosters for 2021–2025.
2. NBA: union per-game rosters and official team rosters for 2021–22 through 2025–26.
3. NHL: union bios/game roster spots, opening-day rosters, and team roster snapshots for all five seasons; retain a known gap for zero-game roster spells.
4. Premier League: union registration lists and the approved provider's player/lineup records for all five seasons.

Retain every rostered player and left-join performance. A player with zero minutes is different from a player with missing data.

## Phase 3 — add baseline performance and opportunity

- Pull raw totals and the relevant exposure denominator.
- Build player-game/week and player-team-season layers before the league-wide player-season panel.
- Store regular season and postseason separately.
- Keep provider definitions and raw fields before engineering.
- Add metric-definition, tracking-regime, and provider-version fields; do not pool across definition breaks silently.
- Reconcile league totals and a sample of individual game logs.

## Phase 4 — add physical measurements

- Store each measurement with date, protocol, and source.
- Record when the measurement became available so season-start features can use true point-in-time joins.
- Prefer verified measured values over inferred values.
- Retain multiple dated measurements rather than overwriting history.
- Select season features as of the relevant prediction date; include age and staleness of the selected measurement.
- Add explicit participation/missingness flags.

## Phase 5 — add context and event data

- NFL play-by-play/participation.
- NBA matchup and tracking aggregates.
- NHL play-by-play plus MoneyPuck.
- Soccer fixture-level player statistics; licensed event/tracking only if obtained.

## Phase 6 — engineer within-sport indices

- Rates per relevant opportunity.
- Role/team/opponent/context adjustment.
- Shrinkage for low samples.
- Position-relative robust z-scores and percentiles.
- Prior-season, three-season weighted-average, trend, and consistency features built as of an explicit anchor date.
- Training through 2023–24, validation on 2024–25, and a locked 2025–26 test to prevent leakage.

## Phase 7 — cross-sport ensemble

Train on shared standardized dimensions, not raw event columns. Keep separate products for:

1. Completed-season descriptive archetypes.
2. Returning-player forecasts using prior history.
3. Physical-only cold-start role similarity.
4. Physical plus source-sport performance.
5. Physical plus performance plus tracking-derived response/spatial features.

This preserves an honest comparison when advanced data is missing in one sport.

---

# 10. Recommended implementation order

1. **NFL first.** Best open bulk files, clearest IDs, complete temporal rosters, rich opportunity denominators, and strong historical testing.
2. **NBA second.** Best possession-winning detail through Hustle/matchup reports and strong combine morphology, with access/rights controls.
3. **NHL third.** EDGE adds real in-game speed; MoneyPuck and official feeds make a strong model, but roster history and combine coverage are weaker.
4. **Premier League fourth.** Start with API-Football and official squad validation; add UCL only after the domestic pipeline and rights position are stable.

The minimum viable build is a five-season player panel per sport, backed by common identity, roster-spell, dated-measurement, and source-registry tables. Build the NFL 2021–2025 panel as the reference implementation before mirroring it in the other sports.

---

# 11. Biases that must be designed around

- **Survivorship and selection bias:** the sample contains athletes who already reached an elite league. A model learns what elite selection systems chose, not the causal chance that an arbitrary athlete could switch sports.
- **Combine missingness:** invitations, injuries, opt-outs, and selective drill participation make missingness informative.
- **Measurement staleness:** combine measurements may be many years older than the season being modeled; listed annual weight may not be newly measured.
- **Repeated-player dependence:** five player-seasons from one athlete are not five independent athletes. Use temporal splits, clustered uncertainty, and appropriate weighting or hierarchical effects.
- **Era/source breaks:** NFL participation providers, NBA tracking technology, NHL API schemas, and soccer scoring/competition formats change inside the window and must be versioned.
- **Role/opportunity bias:** raw defensive actions depend heavily on scheme, possession, line combinations, matchups, score state, and playing time.
- **Scorer/provider bias:** tackles, takeaways, hits, pressures, matchups, and recoveries have provider-specific definitions.
- **Cross-sport unit mismatch:** top skating speed, 40-yard time, average basketball speed, and soccer tracking speed are not the same construct.
- **Target leakage:** if predicting future fit or value, calculate engineered features only from data available before the prediction date.
- **Small-sample instability:** rare events such as interceptions, charges, and forced fumbles need shrinkage and uncertainty intervals.
- **Roster ambiguity:** distinguish registered, active, dressed, and appeared.

## Final recommendation

Begin with a 2021–2025 NFL reference panel, then mirror the longitudinal schema for the NBA and NHL. For soccer, use the Premier League, acquire a five-season structured feed with verified rights and coverage, use official pages only for roster/manual validation unless permission is granted, and leave limb length and true tracking-derived reaction metrics missing until a licensed source is available.

This yields a defensible first dataset without pretending that public data contains measurements it does not, or that a public website automatically grants model-training rights.
