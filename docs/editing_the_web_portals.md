# Editing the web portals

The portals are ordinary HTML, CSS, and JavaScript. There is no React build, bundler, or template compiler. Edit the files below, run the local server, and refresh the browser.

## Where each page lives

All paths are relative to the repository root.

| View | Page structure and words | Appearance | Browser behavior | Default address |
|---|---|---|---|---|
| Native-first profile | `portal-all-roles/profile/index.html` | `portal-all-roles/profile/styles.css` | `portal-all-roles/profile/app.js` | `http://127.0.0.1:8771/profile/` |
| Detailed explorer | `portal-all-roles/index.html` | `portal-all-roles/styles.css` | `portal-all-roles/app.js` | `http://127.0.0.1:8766/` |
| Compact explorer | `portal-all-roles/compact/index.html` | `portal-all-roles/compact/styles.css` | `portal-all-roles/compact/app.js` | `http://127.0.0.1:8767/compact/` |
| Friendly explorer | `portal-all-roles/friendly/index.html` | `portal-all-roles/friendly/styles.css` | `portal-all-roles/friendly/app.js` | `http://127.0.0.1:8768/friendly/` |
| Guided stories | `portal-all-roles/stories/index.html` | `portal-all-roles/stories/styles.css` | `portal-all-roles/stories/app.js` | `http://127.0.0.1:8769/stories/` |
| Research report | `portal-all-roles/report/index.html`, `findings.html`, `features.html`, `validation.html`, `visuals.html`, and `guide.html` | `portal-all-roles/report/styles.css` | `features.js` and `validation.js` render generated aggregate evidence | `http://127.0.0.1:8770/report/` |

The earlier possession-only portal is separate: `portal/index.html`, `portal/styles.css`, and `portal/app.js`.

Use this rule of thumb:

- Change headings, explanatory text, navigation, or layout sections in the relevant HTML file.
- Change colors, spacing, typography, charts, and responsive behavior in the relevant `styles.css`.
- Change dropdowns, player selection, score explanations, URL parameters, or JSON rendering in the relevant `app.js`.
- Change model outputs or generated player fields in Python, not in the browser files.

Each explorer has its own frontend files on purpose. A wording or design change in the friendly page does not automatically change the compact or detailed page. The report navigation is repeated in each report HTML file, so add or rename a report link in every report page.

## Where the displayed data comes from

The explorers all read one shared static export:

```text
portal-all-roles/data/manifest.json
portal-all-roles/data/players/<generated-id>.json
```

`manifest.json` contains the searchable player catalog, sports, roles, defaults, snapshot notes, and model evidence counts. Each file under `data/players/` contains one athlete's observed, forecast, physical, body-fit, and transfer results.

These files are generated and ignored by Git. Do not correct them by hand: the next export will replace those edits.

The export path is:

```text
processed player-season data + fitted models
                    ↓
src/possession_lab/all_roles_portal.py
                    ↓
portal-all-roles/data/manifest.json and data/players/*.json
                    ↓
the profile, detailed, compact, friendly, and stories JavaScript files
```

The main Python files are:

- `src/possession_lab/all_roles_portal.py` — chooses the latest eligible player rows, calculates body-fit references, scores profiles, and writes strict JSON.
- `src/possession_lab/all_roles_score.py` — creates the underlying observed/forecast/physical/transfer score payloads and withholding reasons.
- `src/possession_lab/portal_server.py` — serves only the static portal folder on `127.0.0.1` and disables stale browser caching.
- `src/possession_lab/cli.py` — maps the portal commands to their folders, entry pages, and default ports.

The report is different: its prose and charts are tracked directly in `portal-all-roles/report/`. When model results change, update its numbers from the evidence files under `reports/all_roles/`, not from a screenshot or a player page.

## Safe to edit versus generated

Safe, tracked source files:

- every portal `.html`, `.css`, and `.js` file listed above;
- `src/possession_lab/` when intentionally changing export, scoring, or serving behavior;
- report pages and their explanatory chart markup;
- tests under `tests/`.

Generated or local-only files:

- `portal-all-roles/data/`;
- `data/raw/` and `data/processed/`;
- `models/`;
- most player-level predictions and large derived outputs.

Generated data are excluded from Git for size, reproducibility, and source-rights reasons. Do not force-add them to GitHub without completing the source and redistribution review in `docs/all_roles_data_sources.md`.

## Small edit-and-check workflow

From the repository root, install the project once:

```text
uv sync --extra dev
```

Start the page you are changing. This launcher command is the same in Windows PowerShell, Command Prompt, macOS, and Linux:

```text
uv run python scripts/run_portal.py profile
uv run python scripts/run_portal.py detailed
uv run python scripts/run_portal.py compact
uv run python scripts/run_portal.py friendly
uv run python scripts/run_portal.py stories
uv run python scripts/run_portal.py report
```

Then:

1. Edit the matching HTML, CSS, or JavaScript file.
2. Refresh the browser. The server sends `Cache-Control: no-cache`, so a normal refresh should show the change.
3. If you changed export or scoring Python, rebuild the shared player export first:

   ```text
   uv run python scripts/run_lab.py build-all-roles-portal
   ```

4. Run the checks before committing:

   ```text
   uv run ruff check src tests
   uv run pytest -q -p no:cacheprovider
   ```

Do not open the HTML with a `file://` URL. The explorers fetch relative JSON files, so they need the local server. Press `Ctrl+C` in the terminal to stop it.

## GitHub and deployment note

The source code itself is portable because `uv` creates the correct environment for the operating system. The tracked six-page report runs from a fresh clone without player JSON. The full player explorers are not self-contained GitHub Pages sites because their generated `data/` directory is deliberately not committed. A public deployment needs either a release-cleared static export or an approved data-hosting/API plan. Keep that distinction visible: cross-platform source code does not automatically grant permission to publish the underlying datasets.
