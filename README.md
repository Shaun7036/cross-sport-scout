# Athlete Translation Lab

This project compares athletes from the NFL, NBA, NHL, and Premier League. It first measures how a player performed against people in the same role and season, then explores which roles in another sport have a similar body type and broad performance profile.

The cross-sport results are research comparisons—not a probability that someone could successfully change sports.

## Run it in DataSpell

Use Python 3.12 if it is available. Open this folder as the DataSpell project:

```text
/Users/dannydevito/Documents/USC/SBA/SBA_26_27/SBA_Project_AllRoles_Fall2026
```

Then open DataSpell's terminal and run:

```bash
bash scripts/setup_local.sh
bash scripts/run_portal.sh friendly
```

Open [http://127.0.0.1:8768/friendly/](http://127.0.0.1:8768/friendly/) in a browser. Press `Ctrl+C` in the terminal when you want to stop the server.

You only need to run the setup command the first time, or after moving the repository or changing Python versions.

### DataSpell interpreter

After setup, choose this interpreter in DataSpell:

```text
<this project>/.venv/bin/python
```

If DataSpell previously remembered an environment from the repository's old location, remove that interpreter entry and select the one above.

## Choose a portal

The launcher works from any folder, so you do not need to change directories first.

| Command | What it shows | Address |
|---|---|---|
| `bash scripts/run_portal.sh friendly` | Simple player explorer | [127.0.0.1:8768/friendly/](http://127.0.0.1:8768/friendly/) |
| `bash scripts/run_portal.sh stories` | Guided examples and interesting cases | [127.0.0.1:8769/stories/](http://127.0.0.1:8769/stories/) |
| `bash scripts/run_portal.sh compact` | Compact research view | [127.0.0.1:8767/compact/](http://127.0.0.1:8767/compact/) |
| `bash scripts/run_portal.sh detailed` | Full evidence and diagnostics | [127.0.0.1:8766/](http://127.0.0.1:8766/) |
| `bash scripts/run_portal.sh report` | Three-page project report | [127.0.0.1:8770/report/](http://127.0.0.1:8770/report/) |
| `bash scripts/run_portal.sh legacy` | Earlier possession-only project | [127.0.0.1:8765/](http://127.0.0.1:8765/) |

Add `--port` if a port is already in use:

```bash
bash scripts/run_portal.sh friendly --port 9000
```

## Fix `No module named possession_lab`

This normally means the repository moved but its old virtual environment still points to the previous folder. Repair it with:

```bash
bash scripts/setup_local.sh
bash scripts/run_portal.sh check
```

The second command should print `Local environment is ready.` The launcher also adds the project's `src` folder explicitly, so it remains reliable when an IDE has a stale package link.

If setup cannot find `uv`, install it from [docs.astral.sh/uv](https://docs.astral.sh/uv/) or let the script use your installed `python3` and `pip` instead.

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
- [Features, uses, and limitations](portal-all-roles/report/guide.html)

## How to read the ratings

- **Observed percentile:** how the player performed against same-role players in that season.
- **Native forecast:** an experimental next-season estimate for the player's own sport and role.
- **Physical estimate:** how the player's listed height and weight resemble profiles associated with a target role.
- **Transfer estimate:** an exploratory comparison using build plus broad source-sport performance traits.

Percentiles are relative to a particular sport, role, season, and comparison group. An 80 in one sport is not automatically equivalent to an 80 in another. Body fit is also not the same as playing ability.

## Rebuild the research outputs only when needed

Most users can skip this section. To rebuild from the cached source data and retrain the models:

```bash
.venv/bin/python -m possession_lab.cli run-all-roles --root "$PWD"
```

This is slower than opening the portal. Raw data, processed player tables, generated player JSON, and fitted model files remain local and are intentionally not stored in Git.

## Check the code

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python -m ruff check src tests
```

## More detail

- [Original detailed README](README_LEGACY.md)
- [Methodology and project state](docs/all_roles_design.md)
- [Data sources and usage rules](docs/all_roles_data_sources.md)
- [Model evaluation](reports/all_roles/model_evaluation.json)
- [Role-level EDA](reports/all_roles/role_summary.csv)

The model is best used to explore hypotheses, compare role archetypes, demonstrate a reproducible sports-data workflow, and identify cases worth studying. It should not be used by itself for contracts, roster decisions, medical or safety decisions, or claims that an athlete would succeed after changing sports.
