# NFL reference pipeline

Run:

~~~bash
uv run possession-lab run --sport nfl
~~~

This downloads 35 cached files: weekly rosters, player statistics, play-by-play, participation, snap counts and advanced defense for five seasons, plus the player crosswalk, schedule, historical combine and optional official/coalesced measurement extracts.

GSIS identifies a player. PFR and SMART IDs bridge conditional enrichments. Missing GSIS roster rows enter quarantine. The descriptive regular-season roster universe is preserved before filtering the defensive modeling panel.

Default opportunity is observed participation on a valid regular-season pass/run scrimmage play. Core event numerators are normalized from play-by-play on the same scope. Half-sacks receive 0.5 credit. Team-attributed forcing/recovery fields prevent offensive return-tackle events from being assigned to the defense.

The reported_player_games.parquet file retains the published weekly totals. It is not substituted for the scrimmage-scope event layer: tackles and forced fumbles can include special-team actions, and historical TFL credit conventions differ. The PBP-derived target is explicitly named negative_play_tackle_credits; official weekly TFL is retained as official_tackles_for_loss. The qa.json report shows both totals rather than pretending they are identical.

Player-play event credits are checked against participation. Player-seasons with uncovered credited plays have opportunity_complete=False, retain observed_opportunity for audit, and use a null modeling denominator. They are excluded from rate fitting rather than assigned an inflated rate. Attributed safeties and unique pass-disruption plays have explicit definitions; overlapping sacks/QB hits are not blindly added.

The 2022 cancelled Buffalo–Cincinnati game is excluded from completed-game counts. Other selected seasons have 272 completed regular-season games; 2022 has 271. Postseason source rows remain in raw snapshots and are excluded from this model.

OLB remains an ambiguous hybrid role. Outside/slot corner and box/deep safety assignments are not claimed without alignment evidence.

Raw participation changes provider from NGS through 2022 to FTN from 2023 onward. Both require their own CC BY-SA attribution. The provider is retained. These are exposure denominators, not individual pass-rush or coverage opportunities.

The measurement_events.parquet file preserves archived height/weight listings. The conditional_test_measurement_events.parquet file adds dated-year arm/hand/wingspan, speed, jump, agility and strength measurements where present. The conditional_player_season_measurements.parquet file chooses a measurement no later than that season and retains protocol and years since measurement. 2021 testing has the pro-day-format caveat.

PFR and community combine enrichments are stored separately with source terms and are excluded from default model features/targets. The primary models therefore do not silently depend on third-party pressure definitions or unreviewed combine reuse.

See [the model card](model_card.md), [the NFL report](../reports/nfl/report.md), and [the original detailed plan](../outputs/nfl-possession-archetype-plan.md).
