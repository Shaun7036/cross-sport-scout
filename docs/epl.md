# Premier League adapter

The adapter builds two related datasets without pretending their fields are interchangeable.

## Five-season common core

For start years 2021 through 2025, archived Fantasy Premier League files from
[vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League) provide the roster universe, the stable FPL `code`, broad FPL role,
fixture appearances, and minutes. Season-local FPL element IDs are used only to join a season's files;
the canonical identifier is `fpl:<code>`.

The older FPL schema does **not** observe tackles, interceptions, recoveries, blocks, pressures, or
forced turnovers. Those fields remain null for 2021-22 through 2024-25. A null means “not collected,”
not zero.

## Enhanced 2025-26 layer

[FPL-Core-Insights](https://github.com/olbauday/FPL-Core-Insights) publishes Premier League player-match tables with tackles, tackles won,
interceptions, recoveries, blocks, clearances, duels, fouls, and dispossessions. The adapter downloads
all 38 league gameweeks, filters to players who appeared, maps season element IDs back to the stable FPL
code, and verifies that exactly 380 league matches are represented.

The repository did not publish an explicit license when this adapter was written. Treat this layer as a
research/prototyping source and do not redistribute its raw files without a rights review. Its
`defensive_contributions` field reflects the new 2025-26 FPL scoring rule and is stored as
`defensive_contributions_raw`; it is never pooled with older-season outcomes.

## Physical profiles

Height, weight, and date of birth are conservatively matched to the
[ESPN Premier League roster endpoint](https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams?limit=100&season=2025) within
team. Recent Vaastav player tables also supply birth dates, which take precedence for season-age
calculation and retain an `age_source` label. The output retains the ESPN ID, match method, match score,
and source date. ESPN profile values are snapshots retrieved after the target season; they are not
presented as measurements taken during each historic season. Wingspan, arm length, and leg length remain
null because no credible league-wide public source was found.

## Outputs

- `data/processed/epl/player_seasons.parquet`: all rostered players, one row per player-season.
- `data/processed/epl/player_games.parquet`: appearances, one row per player-match.
- `data/processed/epl/physical_profiles.parquet`: matched, dated profile snapshots.
- `data/processed/epl/qa.json`: row counts, metric coverage, identity checks, and source-boundary checks.
- `reports/epl/recent_2025_association.json` and `.md`: held-out recent-season model evidence.
- `reports/epl/recent_2025_predictions.parquet`: unseen-player test predictions and baselines.
- `models/epl/recent_2025_*_per90.joblib`: fitted profile/role pipelines for the four event targets.

The shared analysis layer only models genuine observed outcomes. Because detailed possession-winning
events exist for one season, it correctly skips temporal event forecasting. A separate 2025-26 model
uses a reproducible player-grouped holdout, players with at least 450 minutes, event rates per 90, and
only broad role, age, height, and weight. It compares a regularized profile model with a training-fold
role-mean baseline and uses no same-season event statistic as a predictor. This is a retrospective
association test—not a validated next-season prediction model—and negative baseline improvement is
retained rather than hidden.
