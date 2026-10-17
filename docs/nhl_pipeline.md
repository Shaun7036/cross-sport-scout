# NHL acquisition and panel contract

The NHL adapter builds reproducible regular-season skater panels for season start
years 2021 through 2025. It uses MoneyPuck's designated files rather than scraping
HTML pages, and uses the NHL Stats report only for bio enrichment.

## Sources

| Data | Exact designated source | Raw grain |
|---|---|---|
| Season skater summary | `https://www.moneypuck.com/moneypuck/playerData/seasonSummary/{year}/regular/skaters.csv` | skater-season-team-situation |
| Player-game summary | `https://peter-tanner.com/moneypuck/downloads/seasonPlayersSummary/skaters/{year}.zip` | skater-game-situation; the adapter retains NHL game type `02` (regular season) |
| MoneyPuck player lookup | `https://www.moneypuck.com/moneypuck/playerData/playerBios/allPlayersLookup.csv` | current/undated player profile |
| NHL bio report | `https://api.nhle.com/stats/rest/en/skater/bios?...&cayenneExp=seasonId={YYYYYYYY}%20and%20gameTypeId=2` | one season-filtered player profile row |

Every downloaded file has a `.source.json` sidecar containing its URL, retrieval
time, SHA-256 digest, byte count, source, and license note. Existing cache content
is hash-checked before reuse.

MoneyPuck permits its data for non-commercial use and ad-hoc journalism with clear
MoneyPuck attribution; contact MoneyPuck for other uses. NHL data and marks remain
subject to NHL terms.

## Canonical definitions

The output event mappings are:

| Canonical field | MoneyPuck field |
|---|---|
| `takeaways` | `I_F_takeaways` |
| `blocks` | `shotsBlockedByPlayer` |
| `hits` | `I_F_hits` |
| `giveaways` | `I_F_giveaways` |
| `faceoff_wins` | `faceoffsWon` |
| `opportunity` | `icetime / 60`, in minutes |

MoneyPuck's `all` situation includes its `5on5` events. The adapter therefore
uses the `all` values for unsuffixed columns and puts the even-strength view in
`*_5v5` columns. These overlapping situations are never summed. If the source
contains separate team stints, counts and ice time are combined into one
player-season; an explicit `TOT`, `TOTAL`, or `ALL` row is preferred to avoid
double counting.

`player_id` is the NHL player ID as a string. Roles are deliberately broad:
`defense`, `center`, `wing`, and `skater_other`. Age is calculated on October 1
of the season start year.

## Coverage and physical-data caveat

Both panels are appearance-based. They include skaters with a MoneyPuck statistical
row, not every player who appeared on a reserve list or signed a contract. Zero-game
roster players are absent and this is recorded in the output. Goalies are out of
scope because this project is modelling skater possession/disruption roles.

The MoneyPuck player lookup is a current/undated snapshot. Its height and weight are
saved in `latest_player_bios.parquet` but are **not** silently used as historical
measurements. The modelling panel uses a season-filtered NHL Stats bio report to
identify each season's athlete universe, but the profile values themselves are
current/undated. In the 2021–2025 pull, every multi-season athlete had exactly the
same listed height and weight in every report. Consequently,
`physical_is_confirmed_season_measurement` is always false and
`physical_measurement_scope` explicitly prohibits annual-change interpretation.
Birth date is stable and may fall back to the MoneyPuck lookup for age calculation.

NHL EDGE data are not bulk-downloaded: there is no supported public bulk endpoint,
and thousands of per-player detail requests would be impolite and fragile. The
official public pages provide league leaders and individual detail, but not a
designated full-roster season file. Consequently, this baseline does **not** contain
top speed, speed-burst, or current skating-test measurements; its physical inputs are
listed height, listed weight, and age. Public sources also do not provide league-wide
wingspan, arm length, leg length, reaction-time, or cognitive/spatial-awareness tests.

## Outputs and validation

The adapter writes:

- `data/processed/nhl/player_seasons.parquet`: one appearing skater-season.
- `data/processed/nhl/player_games.parquet`: one appearing skater-game.
- `data/processed/nhl/latest_player_bios.parquet`: explicitly current/undated lookup.
- `reports/nhl/source_coverage.json`: coverage, uniqueness, range, situation, and
  game-to-season reconciliation checks.
- Shared EDA, archetype, and out-of-season model artifacts under `reports/nhl`.

Run all five seasons with:

```bash
possession-lab run --sport nhl --seasons 2021 2022 2023 2024 2025
```

The model should use exposure-aware rates or an offset and enforce a minimum ice-time
threshold during analysis. Raw totals mostly identify playing time, not efficiency.
