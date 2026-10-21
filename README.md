# Possession Lab

Research repository for physical archetypes, possession creation, and defensive disruption in the NFL, NBA, NHL, and Premier League.

The initial collection window is NFL 2021–2025 and 2021–22 through 2025–26 for the other leagues. NFL is the reference implementation. Each sport retains its own definitions, opportunities, roles, source attribution, and missing-data indicators.

The working release downloads, cleans, audits, explores, and models all four leagues. It includes 219 cached public source files (300.5 MiB), 38 processed tables, saved model artifacts, automated tests, and a unified physical-profile efficacy ensemble.

| League | Seasons | Player-seasons | Distinct athletes | Current model coverage |
|---|---|---:|---:|---|
| NFL | 2021–2025 | 7,279 defenders | 2,754 | Availability, opportunity, six disruption outcomes, physical role/association models |
| NBA | 2021–22 to 2025–26 | 2,932 | 1,057 | Steals, blocks, defensive rebounds, availability, opportunity, physical models |
| NHL | 2021–22 to 2025–26 | 4,738 skaters | 1,480 | Takeaways, blocks, hits, faceoffs, availability, opportunity, physical models |
| Premier League | 2021–22 to 2025–26 | 4,025 | 1,797 | Five-year availability/minutes; 2025–26 possession association models |

NFL also preserves 15,518 player-seasons across all listed positions before building the defensive modeling panel. NHL coverage is skaters who appeared; zero-game roster players are not reconstructed. Each sport's QA and source notes describe the exact universe.

## Run

Use Python 3.12 and uv:

~~~bash
uv sync --locked --extra dev --python 3.12
uv run possession-lab run --sport nfl
uv run possession-lab run --sport nba
uv run possession-lab run --sport nhl
uv run possession-lab run --sport epl
uv run possession-lab manifest
~~~

The default start years are 2021 through 2025. For NBA/NHL/EPL, 2025 means 2025–26. Downloads are cached with SHA-256 verification and provenance sidecars. Reruns reuse the exact local snapshot. A fresh download that differs from the tracked manifest fails clearly; use --accept-source-updates only when creating and evaluating a new data version. The public source may no longer serve the original snapshot, so preserve local raw files for exact reproduction. To process all sports in order:

~~~bash
uv run possession-lab run --sport all
~~~

Rebuild only EDA and models from existing processed data:

~~~bash
uv run possession-lab analyze --sport all
~~~

Inspect a candidate's physical role compatibility:

~~~bash
uv run possession-lab score --sport all --height-cm 188 --weight-kg 95 --age 25
~~~

This returns role-label probabilities, physical rate associations where supported, reference sample sizes, and out-of-distribution flags. It does not estimate the probability of entering or succeeding in a different sport. An example output is in [reports/example_physical_profile.json](reports/example_physical_profile.json).

## Unified efficacy ensemble

After processing the four sports, train the common model and score an athlete:

~~~bash
uv run possession-lab train-ensemble
uv run possession-lab efficacy --profile examples/athlete.json
uv run possession-lab efficacy --height-cm 188 --weight-kg 95 --age 25 --output work/athlete_rating.json
~~~

`efficacy` returns each sport's best provisionally supported role, all role estimates,
separate physical-fit percentiles, prediction intervals, model evidence, and unused
measurements. Metric and imperial JSON profiles are supported. A rating of 70
means an estimated 70th-percentile possession/disruption activity composite among
eligible elite peers in that role. It is not an entry probability or evidence of
successful sport switching. Ratings are ordinal within roles, not equal units of
sporting value. Unsupported, out-of-domain, and no-evidence roles have a null
primary rating; explicitly labeled experimental estimates remain auditable.

The ensemble combines four sport-role experts, a shared role-standardized expert,
and a neutral-50 baseline using nonnegative weights learned from athlete-heldout
predictions. Height and weight are the only common learned inputs in this release.
Age/BMI are retained for reporting; submitted limb lengths, wingspan, speed, and
mental attributes do not silently influence predictions without training coverage.
The ensemble uses sport × role × season target scales to limit provider/year drift.

This evaluation holds out athlete identities, with a frozen 2025 test and
separate calibration athletes. Training identities include 2025 contemporaneous
reference players; this is descriptive association, not a preseason forecast. EPL
possession evidence is 2025 only. See the [ensemble report](reports/ensemble/findings.md),
[design](docs/ensemble_design.md), and [example score](reports/ensemble/example_athlete.json).
Model binaries stay local; a fresh clone must process the source data and train.

Current result: five heads pass exploratory point checks, but every bootstrap 95%
improvement interval includes zero. Height/weight alone have not established
reliable efficacy prediction. Intervals are wide, and EPL defenders show marked
undercoverage. Treat all scores as research estimates, not validated player ratings.

## Player explorer

A small static web portal presents the current research snapshot. Select a player,
compare their body measurements against sport-specific roles, and inspect the
estimate, interval, closest reference archetype, and supporting evidence.

~~~bash
uv run possession-lab build-portal
uv run possession-lab portal
~~~

Open `http://127.0.0.1:8765`. These commands use the existing local processed
tables and verified unified model; they do not download data or retrain models.
The server binds only to this computer and serves only the `portal/` directory.
Use `--port 8989` if needed. Rebuild explicitly after changing data or models;
the server otherwise reuses the existing frozen export.

Player-level exports remain ignored by Git. The page makes no third-party
analytics, font, image, or model API requests. A rating is a provisional predicted
activity percentile within a role, not a success probability. Body fit is a
separate centrality diagnostic, not efficacy. The portal additionally withholds
all EPL defender ratings pending block-coverage review; this display safeguard
does not modify the saved model. See [portal operation and interpretation](docs/portal.md).

## Reports and evidence

- [NFL report](reports/nfl/report.md) · [HTML with charts](reports/nfl/report.html)
- [NBA report](reports/nba/report.md) · [HTML with charts](reports/nba/report.html)
- [NHL report](reports/nhl/report.md) · [HTML with charts](reports/nhl/report.html)
- [Premier League report](reports/epl/report.md) · [2025–26 possession association evaluation](reports/epl/recent_2025_association.md)
- [Research findings](reports/findings.md)
- [Data inventory](metadata/data_inventory.md) · [schemas](metadata/dataset_catalog.json) · [download manifest](metadata/download_manifest.json)
- [Model card and limitations](docs/model_card.md)
- [Unified ensemble evaluation](reports/ensemble/findings.md) · [per-role metrics](reports/ensemble/evaluation.csv)

Each sport report includes seasonal coverage, missingness, size/opportunity distributions, within-role physical correlations, role event rates, baseline comparisons, model selection, and temporal split details.

Returning-player model selection uses 2024; evaluation uses 2025. Baselines are retained when they win validation. Physical role models and physical effectiveness associations are evaluated separately from forecasts using prior performance. Source physical listings are frequently undated/current and are excluded from strict lagged-performance forecasts.

These are retrospective research evaluations with final corrected source snapshots. The 2025 results were inspected during pipeline development and QA; a future frozen evaluation is needed for confirmatory deployment claims.

## Physical measurements

The default models use height and weight where available, with age derived from date of birth. NFL optional measurement tables preserve arm length, hand size, wingspan, 40-yard and 10-yard tests, jumps, agility drills, and bench results. Test year/protocol and years since measurement remain explicit.

For 2025 NFL roster players, the optional inventory contains arm/hand measurements for 1,991 players, wingspan for 293, 40-yard times for 1,611, and 10-yard splits for 1,199. These conditional-source measurements are collected and cleaned but excluded from default training pending source-use review. Leg length remains unobserved.

## Soccer boundary

The historical FPL archive does not contain comparable five-year tackle/interception/recovery/block labels. These fields remain null for 2021–24. The enhanced 2025–26 source covers 380 matches and supplies genuine events, supporting a separately evaluated model on 400 players with 450+ minutes and a 100-player holdout.

The detailed model beats the role mean for blocks in this initial holdout, but not for every event. That distinction is retained in the reports.

## Repository layout

~~~text
src/possession_lab/       shared IO, EDA, models, inference, and sport adapters
tests/                   scoring, identity, scope, temporal and pipeline tests
data/raw/                cached original files plus provenance (local, ignored)
data/processed/          canonical Parquet tables and quarantine (local, ignored)
models/                  fitted joblib artifacts (local, ignored)
portal/                  static player explorer; generated data/ stays local/ignored
reports/                 tracked EDA, charts, QA, and aggregate evaluation
metadata/                tracked source hashes, dataset inventory, and schemas
docs/                    source/method notes and model card
outputs/                 original research plans and source audit
~~~

## Verify

~~~bash
uv run ruff check src tests
uv run pytest -q
~~~

Unit tests use small synthetic fixtures and do not redownload league data. Real-data QA is performed by each adapter and saved beside its panels. GitHub Actions runs the unit suite and lint checks.

## Data sources and use

Source adapters use [nflverse](https://github.com/nflverse/nflverse-data), [SportsDataverse](https://github.com/sportsdataverse/sportsdataverse-data), [MoneyPuck designated downloads](https://www.moneypuck.com/data.htm), [Vaastav's FPL archives](https://github.com/vaastav/Fantasy-Premier-League), [FPL-Core-Insights](https://github.com/olbauday/FPL-Core-Insights), and documented profile enrichments.

Data retain the original source terms. NFL participation includes separate NGS/FTN attribution; MoneyPuck permits noncommercial use with attribution. PFR and community enrichments remain separately governed. This private research repository versions code and aggregate reports without redistributing raw source tables.

## Research plans

- [NFL plan](outputs/nfl-possession-archetype-plan.md)
- [Multi-season design](outputs/multi-season-project-roadmap.md)
- [Source audit](outputs/2025-26-sports-data-source-audit.md)

Raw data, derived player tables, and fitted model binaries stay outside Git. Source code, source metadata, QA summaries, EDA, and model evaluation reports are versioned. Data retains the terms of each original source; the repository does not relicense it.
