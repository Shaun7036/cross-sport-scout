# Data inventory

219 cached source files; 300.5 MiB before derived tables.

The raw files, processed player tables and fitted binary models are local artifacts.
Re-run the command line pipeline to recreate them from the tracked source manifest.

| Sport | Seasons | Player-seasons | Distinct athletes | Forecast |
|---|---|---:|---:|---|
| NFL | 2021, 2022, 2023, 2024, 2025 | 7,279 | 2,754 | trained |
| NBA | 2021, 2022, 2023, 2024, 2025 | 2,932 | 1,057 | trained |
| NHL | 2021, 2022, 2023, 2024, 2025 | 4,738 | 1,480 | trained |
| EPL | 2021, 2022, 2023, 2024, 2025 | 4,025 | 1,797 | trained |

## Processed tables

| Table | Rows | Columns |
|---|---:|---:|
| data/processed/epl/forecast_pairs.parquet | 3,184 | 80 |
| data/processed/epl/physical_profiles.parquet | 499 | 10 |
| data/processed/epl/player_games.parquet | 56,272 | 53 |
| data/processed/epl/player_seasons.parquet | 4,025 | 54 |
| data/processed/nba/excluded_non_standings_rows.parquet | 282 | 58 |
| data/processed/nba/forecast_pairs.parquet | 2,341 | 83 |
| data/processed/nba/physical_profile_snapshots.parquet | 2,932 | 22 |
| data/processed/nba/player_games.parquet | 160,121 | 31 |
| data/processed/nba/player_seasons.parquet | 2,932 | 61 |
| data/processed/nba/player_team_seasons.parquet | 3,385 | 34 |
| data/processed/nba/unresolved_player_rows.parquet | 66 | 66 |
| data/processed/nfl/all_rostered_player_seasons.parquet | 15,518 | 49 |
| data/processed/nfl/conditional_advanced_defense.parquet | 38,341 | 32 |
| data/processed/nfl/conditional_anthropometrics.parquet | 15,215 | 49 |
| data/processed/nfl/conditional_combine.parquet | 8,968 | 21 |
| data/processed/nfl/conditional_player_season_measurements.parquet | 92,270 | 11 |
| data/processed/nfl/conditional_player_seasons.parquet | 7,279 | 28 |
| data/processed/nfl/conditional_snap_counts.parquet | 126,562 | 18 |
| data/processed/nfl/conditional_test_measurement_events.parquet | 101,143 | 9 |
| data/processed/nfl/defender_event_credits.parquet | 205,163 | 11 |
| data/processed/nfl/forecast_pairs.parquet | 5,795 | 83 |
| data/processed/nfl/games.parquet | 1,424 | 46 |
| data/processed/nfl/measurement_events.parquet | 31,128 | 8 |
| data/processed/nfl/participation_credit_gaps.parquet | 29 | 11 |
| data/processed/nfl/player_games.parquet | 53,013 | 28 |
| data/processed/nfl/player_identity.parquet | 24,854 | 39 |
| data/processed/nfl/player_seasons.parquet | 7,279 | 49 |
| data/processed/nfl/reported_player_games.parquet | 90,585 | 14 |
| data/processed/nfl/unresolved_roster_2021.parquet | 23 | 36 |
| data/processed/nfl/unresolved_roster_2022.parquet | 26 | 36 |
| data/processed/nfl/unresolved_roster_2023.parquet | 5 | 36 |
| data/processed/nfl/unresolved_roster_2024.parquet | 7 | 36 |
| data/processed/nfl/unresolved_roster_2025.parquet | 18 | 36 |
| data/processed/nfl/weekly_rosters.parquet | 221,234 | 37 |
| data/processed/nhl/forecast_pairs.parquet | 3,798 | 65 |
| data/processed/nhl/latest_player_bios.parquet | 3,400 | 9 |
| data/processed/nhl/player_games.parquet | 236,069 | 41 |
| data/processed/nhl/player_seasons.parquet | 4,738 | 39 |

Field names and types are in dataset_catalog.json; download URLs, SHA-256 hashes, access timestamps and source terms are in download_manifest.json.
