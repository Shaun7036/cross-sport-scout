# Possession Lab player explorer

The portal is a lightweight presentation layer over the existing unified model,
not a new modeling experiment. It uses plain HTML, CSS, and JavaScript and a frozen
JSON export. There is no login database, external analytics, remote inference, or
training in the browser. It is intended for private research presentation until
data-use permissions and model validation support a wider release.

## Run and refresh

From the repository root with the project dependencies installed:

```sh
uv run possession-lab build-portal
uv run possession-lab portal
```

The first command reads the four canonical `player_seasons.parquet` panels and
the hash-verified `models/ensemble/unified.joblib`. It exports season-start-year
2025 players, including those with missing measurements. The second serves
`portal/` on `http://127.0.0.1:8765`. It builds if there is no manifest; otherwise it
reuses the frozen snapshot. Stop with Ctrl+C. Use `--port` to change the port.
Do not use the development server to host the repository publicly.

`build-portal --output /absolute/path` can export JSON to an alternative frontend
directory. It does not copy the HTML/CSS/JavaScript into that directory.

The generated `portal/data/manifest.json` contains the player search index, model
and input provenance, sport/role definitions, and shared head evidence. Individual
player JSON files contain precomputed role results and observed native-sport
events. Hashed filenames are stable identifiers, not anonymization: these files
contain named players. All generated player data are ignored by Git; do not
commit them or source model binaries to make the frontend work.

After changing the model or processed panels, rerun the export and refresh the
browser. Existing exports do not update automatically when data or models change.
An immutable deployment must package the static frontend from the recorded source
commit and the matching locally generated data, preserving the export provenance.

## What the page means

Selecting a player initially uses their recorded native role when that role is
modeled. Changing the target sport holds their height and weight fixed; it does
not convert experience, skill, conditioning, or sport-specific testing.

- **Efficacy:** an estimated possession/disruption activity percentile relative
  to eligible elite peers in a particular sport and role. It is neither a
  probability of success nor a universal sporting-value scale. Comparing 70 in
  two roles does not imply equal contribution.
- **Prediction interval:** the fitted model's nominal 90% range for the role
  target, not a confidence interval around an established athlete ability.
  Calibration is imperfect and intervals are generally very wide.
- **Body fit:** how central the two-dimensional build is to the reference
  population. A common build is not necessarily an effective one.
- **Closest reference build:** an interpretable physical cluster summary, not a
  player comparison, causal explanation, or prediction based on that cluster
  alone. The actual estimate follows the selected model and active blend weights.
- **Observed season events:** contextual player statistics. These do not enter
  the height/weight model, and should not be confused with explanatory inputs.

Height and weight are the only learned input features in this release. Age is
shown for context, but is unused. Speed, wingspan, limb lengths, reactions,
awareness, and mental attributes have not been learned. Explanations describe
actual model components and reference measurements; they are not invented SHAP
attributions or claims that a given measurement caused a result.

The page identifies whether an athlete contributed eligible rows to fitted
training heads. The reference cohort includes contemporaneous 2025 records, so
these are not all held-out predictions or prospective forecasts. Source listings
of height/weight are often current or undated, not validated annual measurements.

## Ratings intentionally withheld

An em dash means unavailable or unsupported, never zero efficacy.

- Missing height or weight: no estimate is manufactured or filled with a league
  average.
- Known under-18 age: retained in the selector but outside the saved model's
  adult profile scope, with no inference performed.
- Out-of-domain build: primary efficacy is withheld; any experimental estimate
  remains explicitly labeled.
- No supporting held-out point evidence: primary efficacy is withheld even when
  a model can return a number. Neutral fallback heads are not evidence of a
  meaningful 50 rating.
- Insufficient training support: notably EPL forwards, which have no fitted head.
- **EPL defenders under review:** all primary DEF ratings are suppressed by a
  portal-only safeguard. Partially observed match-level blocks were aggregated
  over full-season exposure in some source records, and the nominal 90% DEF
  interval also undercovers. This is not silently repaired by presentation code;
  correction and model re-evaluation are separate work. Partial block totals are
  not presented as complete observed counts.

Source roles without a fitted head, including soccer goalkeepers, must be treated
as body-only comparisons against other roles, not native-role ratings.

Five role heads pass the current exploratory point checks, but **none** has a
bootstrap 95% improvement interval excluding zero. All displayed estimates remain
provisional, including the ones that pass those checks.

## Privacy and source use

The frontend uses only same-origin static assets and data. No user profile is
uploaded to a prediction service. Private hosting still creates another copy of
named-player derived data; it does not remove source licensing obligations.
Keep the site owner-private unless separately authorized and source redistribution
conditions have been reviewed. Do not expose fitted joblib files, raw downloads,
credentials, or unrelated repository files in the site archive.

The source adapters and export credits retain attribution to nflverse,
SportsDataverse, MoneyPuck, the FPL archives, FPL-Core-Insights, and profile
enrichments. Original source terms continue to apply. MoneyPuck data are for
noncommercial use with attribution. Neither this repo nor the portal relicenses
the underlying data.

## Verification

```sh
uv run ruff check src tests
uv run pytest -q
```

Exporter tests use small synthetic fixtures. Real-data review should additionally
compare sampled exported results against `score_ensemble`, inspect missing-data
and domain safeguards, and test the actual browser on desktop and narrow screens.
The portal has no effect on the canonical processed tables or fitted model.

## Initial presentation check — 21 October 2026

The initial local export contains 3,856 source-player records: NFL 1,484, NBA 591,
NHL 940, and Premier League 841. There are 3,377 complete height/weight profiles;
10 of those are known minors and are intentionally not scored. Fourteen of the
15 declared sport-role heads are fitted. Generated JSON occupies about 60 MiB.

Seven exporter tests and seven CLI/server tests supplement the existing suite
(101 tests total at this checkpoint). Ninety real athlete/head comparisons
matched core estimates and intervals within 1.42 × 10⁻¹⁴, with exactly matching
physical-fit outputs. The intentional EPL DEF presentation safeguard is excluded
from primary-rating parity. Lint and JavaScript syntax checks passed.

Browser review covered the normal NFL/NBA/NHL/EPL selections, same-body
cross-sport comparison, baseline selection, missing measurements, out-of-domain
builds, minors, unmodeled native roles, and EPL defender withholding. Layouts at
390 px and 1,280 px showed no horizontal overflow. This verifies the presentation
layer, not scientific validity of the underlying model.

The portal is available locally. Hosted Sites returned that it is not enabled
for this workspace; no hosted site or public data release was created.
