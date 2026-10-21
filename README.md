# Athlete Translation Lab

Athlete Translation Lab is a four-sport research project for describing how elite athletes perform within their current role and exploring which roles their build and demonstrated performance profile resemble in another sport. It covers the NFL, NBA, NHL, and Premier League across the 2021–2025 project seasons.

This repository is the independent **all-role** expansion. It preserves the earlier possession-winning work for reference, but the current workflow registers broad position groups represented by the available sources across all four sports. Registration or a fitted model head does not by itself establish predictive support.

The project deliberately returns four different quantities instead of hiding them inside one “efficacy” number:

| Output | Question answered | Interpretation |
|---|---|---|
| Observed role percentile | How did this player perform among same-role peers in this season? | Retrospective, opportunity-adjusted role-season comparison |
| Native forecast percentile | What does the model estimate for this player in the same role next season? | Research next-season backtest using lagged performance and listed physical profiles, shown with its evidence status |
| Cross-sport physical estimate | How strongly is this build associated with performance in a target role? | Physical association only; not a talent grade or causal effect |
| Cross-sport transfer guesstimate | How does the athlete's build plus source-sport performance profile resemble successful target-role athletes? | Exploratory analogy; not a sport-switch probability or validated outcome forecast |

A percentile is relative to one sport, role, season, and reference cohort. An 80 for an NBA guard and an 80 for an NFL wide receiver do not represent equal units of sporting value.

The full scientific contract is in the [all-role methodology guide](docs/all_roles_design.md). Source provenance, coverage, and release restrictions are in the [source-governance guide](docs/all_roles_data_sources.md).

## Current snapshot

The current local snapshot contains 27,652 player-seasons:

| League | Project seasons | Player-seasons | Broad role coverage |
|---|---|---:|---|
| NFL | 2021–2025 | 15,518 | QB, RB/FB, WR, TE, EDGE, IDL, LB, CB, S, K, P; OT, IOL, and LS retained as explicit abstentions |
| NBA | 2021–22 to 2025–26 | 2,866 | Guard, forward, center |
| NHL | 2021–22 to 2025–26 | 5,263 | Center, left wing, right wing, defense, goalie |
| Premier League | 2021–22 to 2025–26 | 4,005 | GK, DEF, MID, FWD |

These are derived snapshot counts, not promises about a changing upstream source. NFL includes all rostered player-seasons and unresolved generic position listings; NBA and NHL are appearance-based. Premier League roles remain broad because the current five-season public cache does not provide defensible longitudinal deployment labels for center-back, fullback, defensive midfield, wing, striker, and similar sub-roles.

## Quick start

Python 3.12 is recommended. From this repository:

~~~bash
uv sync --extra dev --python 3.12
uv run athlete-translation-lab run-all-roles
~~~

`run-all-roles` rebuilds the four all-role panels from the existing raw cache and prerequisite sport-specific processed panels, constructs role-season targets, trains the model families, updates aggregate reports, and rebuilds EDA. It does not acquire sources or rebuild those prerequisite base pipelines. Raw and processed player data and fitted model binaries remain local and are ignored by Git.

Useful narrower commands are:

~~~bash
# Rebuild aggregate EDA from existing all-role outputs
uv run athlete-translation-lab analyze-all-roles

# Retrain from the existing observed-score panel
uv run athlete-translation-lab train-all-roles

# Inspect the command surface
uv run athlete-translation-lab --help
~~~

The `possession-lab` command remains an alias for compatibility.

## Score a known player

Use the player's source sport and stable source ID. The latest available season is used unless `--season` is supplied.

~~~bash
# LeBron James (ESPN athlete ID 1966), translated to NFL roles
uv run athlete-translation-lab all-roles-score \
  --sport nba --player-id 1966 --season 2025 --target-sport nfl

# Stephen Curry (ESPN athlete ID 3975), translated to NHL roles
uv run athlete-translation-lab all-roles-score \
  --sport nba --player-id 3975 --target-sport nhl
~~~

Known-player scoring can return all four outputs because the processed row contains the native observed score and the fixed, season-relative performance dimensions needed by the bridge. Low-sample or abstention rows remain visible, but are not silently promoted to supervised labels.

## Score a custom athlete

A height/weight profile can receive physical-only target-role estimates:

~~~bash
uv run athlete-translation-lab all-roles-score \
  --height-cm 198 --weight-kg 102 --age 25 --target-sport nba
~~~

To request the transfer analogy for an athlete outside the repository, supply source sport, source role, eligibility, and already-normalized source-role performance dimensions. See [examples/all_roles_athlete.json](examples/all_roles_athlete.json):

~~~bash
uv run athlete-translation-lab all-roles-score \
  --profile examples/all_roles_athlete.json --target-sport nfl \
  --output work/example_all_roles_score.json
~~~

The dimension inputs are 0–100 source-role percentiles, not raw box-score values. Omitting them correctly withholds the performance-transfer guesstimate rather than inventing “mental” or game-awareness measurements.

## All-role player explorer

Build the static export and serve it locally:

~~~bash
uv run athlete-translation-lab build-all-roles-portal
uv run athlete-translation-lab all-roles-portal
~~~

Open `http://127.0.0.1:8766`. The export is rebuilt from the local processed tables and fitted all-role artifact. The server binds only to this computer and serves the `portal-all-roles/` directory. Use `--port 8989` to choose another port.

The explorer separates observed native performance, native forecast, physical estimate, and transfer guesstimate; it also displays withholding reasons, evidence status, out-of-domain checks, and model contributions. Generated player-level JSON under `portal-all-roles/data/` is intentionally ignored by Git.

## What the pipeline currently learns

- Observed targets use same-sport, same-role, same-season peers and shrink low-exposure rate statistics toward the cohort prior.
- Availability, per-opportunity quality, and total impact remain separate.
- Supervised models train only on `target_status == "eligible"` labels.
- Native forecast pairs require the player to remain in the same broad role and be eligible in both seasons.
- Fitted cohorts must have the same required inputs that the scorer requires at inference time: height and weight, plus the declared performance dimensions where applicable.
- NFL roles use the modal specific weekly depth-chart role for that season. Generic `DB`, `DL`, and `OL` listings are not guessed into narrower roles.
- OT, IOL, and LS stay in the NFL panel for roster coverage but abstain from performance scoring because no release-safe individual label is available in the current source set.
- Cross-sport bridges use only a predeclared intersection of broadly analogous performance dimensions. A bridge's evidence gate measures reconstruction among target-role athletes only; it is not evidence that performance transfers between sports.

The current learned physical inputs are height, weight, derived BMI, and age. Age may be imputed; height and weight are required. Arm length, wingspan, speed, jumps, agility tests, and other measurements are retained or inventoried where available, but are not silently used without adequate coverage and source-use clearance. Repeated current-profile measurements are not treated as annual measurements.

## Reports and artifacts

Start with these files:

- [Methodology and current state](docs/all_roles_design.md)
- [Sources, coverage, and release gates](docs/all_roles_data_sources.md)
- [Machine-readable metric registry](metadata/all_roles_metric_registry.json)
- [Machine-readable source matrix](metadata/all_roles_source_matrix.json)
- [Data-build summary](reports/all_roles/data_build.json)
- [Observed-target audit and frozen sanity checks](reports/all_roles/observed_targets.json)
- [Model evaluation](reports/all_roles/model_evaluation.json)
- [Role-level EDA summary](reports/all_roles/role_summary.csv)
- [Model evidence summary](reports/all_roles/model_evidence_summary.csv)
- [EDA summary](reports/all_roles/eda_summary.json)

Model counts and evidence outcomes are generated results. Read them from the current reports after rerunning the pipeline rather than copying old counts into downstream presentations.

## Repository layout

~~~text
src/possession_lab/all_roles_*.py   all-role adapters, targets, models, scoring, EDA, portal export
tests/test_all_roles_*.py           all-role unit and integration tests
data/raw/                           cached source snapshots and provenance sidecars (local, ignored)
data/processed/all_roles/           canonical and scored player-season tables (local, ignored)
models/all_roles/                   fitted all-role artifact (local, ignored)
portal-all-roles/                   static all-role explorer; generated data are local/ignored
reports/all_roles/                  aggregate QA, evaluation, EDA, and figures
metadata/                           metric registry, source matrix, and download manifest
docs/                               methodology, source governance, and legacy technical notes
~~~

## Verify

~~~bash
uv run ruff check src tests
uv run pytest -q -p no:cacheprovider
~~~

The suite uses synthetic fixtures and does not redownload league data. Real-data QA and frozen evaluation summaries are written to `reports/all_roles/` by the pipeline.

## Source and release boundary

Public accessibility does not imply permission to redistribute or commercialize the data. The current project combines sources with green, amber, and red governance postures. In particular, MoneyPuck requires attribution and restricts broader use, several ESPN/FPL-derived sources have unresolved upstream rights, and conditional NFL enrichments are excluded from release training.

Keep raw source tables, row-level derived exports, and model binaries outside Git. Preserve source sidecars and regenerate [the download manifest](metadata/download_manifest.json) after acquisition. Before publishing a portal, model, or dataset, follow the sport-specific go/no-go decisions in [the source-governance guide](docs/all_roles_data_sources.md).

## Legacy possession-only project

The earlier possession/disruption pipeline remains in this repository solely for comparison and reproducibility. It is separate from the all-role artifact and portal.

~~~bash
# Legacy sport-specific pipelines
uv run possession-lab run --sport all
uv run possession-lab analyze --sport all

# Legacy unified possession efficacy model
uv run possession-lab train-ensemble
uv run possession-lab efficacy --profile examples/athlete.json

# Legacy player explorer at port 8765
uv run possession-lab build-portal
uv run possession-lab portal
~~~

Legacy documentation and results include the [ensemble design](docs/ensemble_design.md), [legacy model card](docs/model_card.md), [legacy player explorer guide](docs/portal.md), [sport reports](reports/findings.md), and [ensemble findings](reports/ensemble/findings.md). Do not interpret a legacy possession-only score as one of the four all-role outputs.
