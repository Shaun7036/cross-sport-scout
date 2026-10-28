# The Multi Sport Scouter

This project compares athletes from the NFL, NBA, NHL, and Premier League. It first measures how a player performed against people in the same role and season, then explores which roles in another sport have a similar body type and broad performance profile.

The cross-sport results are research comparisons—not a probability that someone could successfully change sports.

## Quick start: presentation website

The current presentation is the Astro site in [`site/`](site/). A fresh GitHub clone already
contains its compact public player data, so you do not need Python, `uv`, the saved models, or the private
research dataset just to view it.

Install [Node.js 24](https://nodejs.org/). Then open PowerShell, Command Prompt, DataSpell's
terminal, or a macOS/Linux terminal in the repository folder and run:

```text
npm --prefix site ci
npm --prefix site run dev
```

Open the address printed in the terminal, normally
[http://localhost:4321/](http://localhost:4321/). Press `Ctrl+C` to stop the site.

Do **not** run `npm --prefix site run data` after a normal clone. That is a maintainer-only
refresh command that expects the larger local research snapshot, which is intentionally not in
Git.

## Optional Python research environment

Install [`uv`](https://docs.astral.sh/uv/) only if you want to run tests, retrain models, or work
on the research pipeline:

```text
uv sync --extra dev --reinstall-package possession-lab
uv run python scripts/run_portal.py check
```

The project uses Python 3.12 by default. The full Python player explorers described below need a
locally generated snapshot under `portal-all-roles/data/`; a fresh GitHub clone does not include
it. The tracked `report` view remains available without that snapshot:

```text
uv run python scripts/run_portal.py report
```

## Choose a portal

The Astro site above is the recommended presentation. This table documents the older local
Python views used during development. Except for `report`, they require the ignored full player
snapshot and are not expected to work from a fresh clone.

| View | What it shows | Address |
|---|---|---|
| `profile` | Native-first player profile, followed by model comparisons | [127.0.0.1:8771/profile/](http://127.0.0.1:8771/profile/) |
| `friendly` | Simple player explorer | [127.0.0.1:8768/friendly/](http://127.0.0.1:8768/friendly/) |
| `stories` | Guided examples and interesting cases | [127.0.0.1:8769/stories/](http://127.0.0.1:8769/stories/) |
| `compact` | Compact research view | [127.0.0.1:8767/compact/](http://127.0.0.1:8767/compact/) |
| `detailed` | Full evidence and diagnostics | [127.0.0.1:8766/](http://127.0.0.1:8766/) |
| `report` | Six-page project report, feature guide, validation evidence, and visuals | [127.0.0.1:8770/report/](http://127.0.0.1:8770/report/) |
| `legacy` | Earlier possession-only project | [127.0.0.1:8765/](http://127.0.0.1:8765/) |

Add `--port` if a port is already in use:

```text
uv run python scripts/run_portal.py friendly --port 9000
```
## What is already available

The current local snapshot covers the 2021–2025 project seasons:

| League | Player-seasons | Broad roles |
|---|---:|---|
| NFL | 15,518 | 14 role groups, including explicit no-score groups |
| NBA | 2,866 | Guard, forward, center |
| NHL | 5,263 | Center, wings, defense, goalie |
| Premier League | 4,005 | Goalkeeper, defender, midfielder, forward |

The portal uses the existing local player export, so you do **not** need to rebuild or redownload everything just to explore it.

Read the visual project report for the research journey, data coverage, findings, model design, assumptions, and limitations:

- [Research process](portal-all-roles/report/index.html)
- [Findings and models](portal-all-roles/report/findings.html)
- [Engineered features and role definitions](portal-all-roles/report/features.html)
- [Training and validation](portal-all-roles/report/validation.html)
- [EDA and model graphs](portal-all-roles/report/visuals.html)
- [Features, uses, and limitations](portal-all-roles/report/guide.html)

The visual page compares dataset size, physical-data coverage, scoring eligibility, model evidence gates, 2025 holdout error, and the current cross-sport validation boundary.

## Where to edit the web pages

Edit the current presentation under `site/src/`: the landing page is
`site/src/pages/index.astro`, the explorer is `site/src/pages/explorer/index.astro`, and the
shared styles are under `site/src/styles/`. The table below is for the older Python-served pages.

| Page | Words and layout | Styling | Player interactions |
|---|---|---|---|
| Native-first profile | `portal-all-roles/profile/index.html` | `portal-all-roles/profile/styles.css` | `portal-all-roles/profile/app.js` |
| Friendly | `portal-all-roles/friendly/index.html` | `portal-all-roles/friendly/styles.css` | `portal-all-roles/friendly/app.js` |
| Stories | `portal-all-roles/stories/index.html` | `portal-all-roles/stories/styles.css` | `portal-all-roles/stories/app.js` |
| Compact | `portal-all-roles/compact/index.html` | `portal-all-roles/compact/styles.css` | `portal-all-roles/compact/app.js` |
| Detailed | `portal-all-roles/index.html` | `portal-all-roles/styles.css` | `portal-all-roles/app.js` |
| Report | `portal-all-roles/report/*.html` | `portal-all-roles/report/styles.css` | `features.js` and `validation.js` power the two generated evidence pages |

See [Editing the web portals](docs/editing_the_web_portals.md) for the full source map, how the generated player JSON reaches each page, and the safe edit-and-check workflow.

## How to read the ratings

- **Observed percentile:** how the player performed against same-role players in that season.
- **Native forecast:** an experimental next-season estimate for the player's own sport and role.
- **Physical estimate:** how the player's listed height and weight resemble profiles associated with a target role.
- **Transfer estimate:** an exploratory comparison using build plus broad source-sport performance traits.

Percentiles are relative to a particular sport, role, season, and comparison group. An 80 in one sport is not automatically equivalent to an 80 in another. Body fit is also not the same as playing ability.

## Rebuild the research outputs only when needed

Most users can skip this section. To rebuild from the cached source data and retrain the models:

```text
uv run possession-lab enrich-epl-wikidata --root .
uv run python scripts/run_lab.py run-all-roles --root .
```

The first command refreshes the rights-cleared EPL height/weight fallback; it reuses validated cached batches unless the input identities change. The full rebuild is slower than opening the portal. Raw data, processed player tables, generated player JSON, and fitted model files remain local and are intentionally not stored in Git.

## Check the code

```text
uv run ruff check src tests scripts/run_portal.py
uv run pytest -q -p no:cacheprovider
```

GitHub Actions runs the same locked environment and test suite on Windows, macOS, and Linux.

## What a GitHub clone includes

The source code, tests, report pages, and report graphs are tracked and portable. The report can run immediately after setup, even without the private local player snapshot:

```text
uv run python scripts/run_portal.py report
```

The full player explorers also need `portal-all-roles/data/`, which is generated locally and intentionally excluded from Git because it is about 453 MB and includes source-dependent player data. Raw data, processed tables, and fitted models are excluded for the same size, reproducibility, and redistribution reasons. Do not force-add those folders before reviewing [Data sources and usage rules](docs/all_roles_data_sources.md).

## More detail

- [Original detailed README](README_LEGACY.md)
- [Methodology and project state](docs/all_roles_design.md)
- [Data sources and usage rules](docs/all_roles_data_sources.md)
- [Model evaluation](reports/all_roles/model_evaluation.json)
- [Role-level EDA](reports/all_roles/role_summary.csv)

The model is best used to explore hypotheses, compare role archetypes, demonstrate a reproducible sports-data workflow, and identify cases worth studying. It should not be used by itself for contracts, roster decisions, medical or safety decisions, or claims that an athlete would succeed after changing sports.

## Static portfolio site

The maintainable public presentation now lives in [`site/`](site/). It uses Astro presentation
pages, Markdown research notes, and one vanilla-JavaScript player explorer. Python generates the
frozen public data during a maintainer refresh; no Python process runs on the deployed website.

```text
npm --prefix site ci
npm --prefix site run dev
```

The main explorer includes 6,904 compact derived player profiles. The 14 presentation cases now
live on a separate Featured page for future storytelling. The tracked files in
`site/public/data/` are ready to use. See [`site/README.md`](site/README.md) for the source map,
optional data-refresh command, build commands, subpath configuration, and public-data boundary.
