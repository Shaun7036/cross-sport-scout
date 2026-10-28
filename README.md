# Athlete Translation Lab

This project compares athletes from the NFL, NBA, NHL, and Premier League. It first measures how a player performed against people in the same role and season, then explores which roles in another sport have a similar body type and broad performance profile.

The cross-sport results are research comparisons—not a probability that someone could successfully change sports.

## Quick start with `uv`

Install [`uv`](https://docs.astral.sh/uv/), clone or download this repository, and open a terminal in the project folder. These commands are the same on Windows, macOS, and Linux:

```text
uv sync --extra dev --reinstall-package possession-lab
uv run python scripts/run_portal.py friendly
```

Open [http://127.0.0.1:8768/friendly/](http://127.0.0.1:8768/friendly/) in a browser. Press `Ctrl+C` in the terminal when you want to stop the server.

`uv sync` creates the project's `.venv` and installs the locked dependencies. The explicit reinstall also refreshes the editable package path after moving the repository. Run it after the first clone, after pulling dependency changes, or after a move. The project uses Python 3.12 by default.

Optional operating-system wrappers do the same thing. On macOS, the setup wrapper also repairs
hidden filesystem flags that can follow a copied `.venv` and prevent DataSpell from loading the
editable package:

[/TODO: project should only launch via uv, not through pwshell or cli scritps. /]: # ()
```bash
# macOS or Linux
./scripts/setup_local.sh
./scripts/run_portal.sh friendly
```

```powershell
# Windows PowerShell
.\scripts\setup_local.ps1
.\scripts\run_portal.ps1 friendly
```

## Choose a portal

The Python launcher is shared by Windows and macOS. Replace `friendly` with any view below.

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

The portals use plain HTML, CSS, and JavaScript—there is no frontend build step.

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

The maintainable public presentation now lives in [`site/`](site/). It uses Astro for shared layouts and deployment, Markdown for the research pages, and one vanilla-JavaScript player explorer. Python still generates the frozen public data through `uv`; no Python process runs on the deployed website.

```text
npm --prefix site ci
npm --prefix site run data
npm --prefix site run dev
```

The portfolio edition intentionally includes nine curated, derived player profiles instead of the complete local 6,904-player export. See [`site/README.md`](site/README.md) for the source map, build commands, subpath configuration, and public-data boundary.
