# The Multi Sport Scouter static site

This folder is the public, static presentation layer. The Python project remains responsible for data acquisition, model training, validation, and the frozen player export. Astro renders the portfolio pages; no Python server or live model is required in production.

## Run locally

Install Node.js 24. From the repository root, run the same commands in Windows PowerShell,
Command Prompt, DataSpell's terminal, macOS, or Linux:

```text
npm --prefix site ci
npm --prefix site run dev
```

The 14 allowlisted presentation profiles are already tracked in `public/data/`, so a fresh clone
does not need Python or the private research artifacts. The explorer remains fully functional on
GitHub Pages because it reads these static files in the visitor's browser.

If your terminal is already inside `site/`, the equivalent commands are `npm ci` and `npm run
dev`.

## Refresh curated data (maintainers only)

After rebuilding the full local research snapshot, maintainers can refresh the public profiles:

```text
npm --prefix site run data
```

This optional command runs the Python exporter through `uv`. It reads the ignored
`portal-all-roles/data/` snapshot and writes only the 14 allowlisted, derived examples. It will
not work from a normal clone unless that full snapshot has been generated locally first.

## Validate and build

```text
npm --prefix site run check
npm --prefix site run build
npm --prefix site run preview
```

The deployable result is written to `site/dist/`.

For a portfolio subpath, set `ASTRO_BASE` when building. For example:

```text
ASTRO_SITE=https://example.com ASTRO_BASE=/projects/athlete-translation npm --prefix site run build
```

Copy the resulting `site/dist/` contents into the matching public folder of the portfolio repository, or use the manual GitHub Pages workflow included in this repository.

## Source map

| Area | Files |
|---|---|
| Shared page shell | `src/layouts/` and `src/components/` |
| Landing page | `src/pages/index.astro` |
| Player explorer | `src/pages/explorer/index.astro`, `src/scripts/explorer.js`, `src/styles/explorer.css` |
| Model stories | `src/pages/stories/index.astro`, `src/styles/stories.css` |
| Presentation findings | `src/pages/research/findings.astro`, `src/styles/findings.css` |
| Research prose | `src/pages/research/*.md` |
| Global design | `src/styles/global.css` |
| Curated public data | `public/data/` |
| EDA figures | `public/images/eda/` |

## Public-data boundary

Everything under `public/` is downloadable by any visitor. The exporter uses an explicit player allowlist and writes derived presentation fields only. Do not copy raw data, processed player-season tables, saved models, provider imagery, or the full local portal export into this folder without a separate release-rights review.

