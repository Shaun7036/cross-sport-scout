# Unified physical-profile efficacy ensemble

The model estimates a role-specific possession/disruption activity percentile
among eligible elite-league peers. A 70 means an estimated 70th-percentile
activity composite for that role; it is not a 70% chance of professional success.
The scoring output can abstain: experimental point estimates remain
available for auditing, while the primary efficacy rating is null when evidence
or physical-reference coverage is inadequate.

The source snapshot was previously inspected during project QA, so this is not
a blind or prospective benchmark. The highest eligible role is a browsing
summary, not a separately calibrated sport-level or sport-switching prediction.

## Frozen evaluation

Athlete identities are split deterministically into 60% training, 20% calibration,
and 20% test. All seasons for a player stay together. Models use training athletes
from 2021–25, including contemporaneous 2025 reference players. Calibration and
test use only 2025 unseen athletes. This is not a temporal/preseason forecast.
EPL has only 2025 possession labels and weaker, same-season evidence. Targets are
normalized within sport × role × season, including inside every CV fold, because
provider/scoring changes make pooled-year ranks misleading (notably NHL takeaways).

Each head blends four physical experts (ridge, boosted trees, extra trees, soft
archetypes), a shared role-standardized polynomial ridge, and a neutral 50 expert.
Nonnegative weights use inner athlete-heldout predictions. Outer athlete-heldout
CV gates selection before calibration/test are opened. A final frozen-test
release gate requires positive rank association and MSE improvement; it does not
retune weights. Evidence-supported means exploratory held-out support, not a
statistically established cross-sport transfer claim.

| Sport:role | Evidence status | Train athletes | Test athletes | MAE | Neutral-50 MAE | MSE improvement |
|---|---|---:|---:|---:|---:|---:|
| nfl:EDGE | no_evidence | 131 | 12 | 24.26 | 22.76 | -5.5% |
| nfl:IDL | no_evidence | 132 | 28 | 26.99 | 27.44 | -1.7% |
| nfl:LB | no_evidence | 125 | 16 | 22.10 | 22.10 | 0.0% |
| nfl:OLB_HYBRID | provisional_point_gate_passed | 120 | 22 | 24.08 | 25.04 | 7.8% |
| nfl:CB | no_evidence | 175 | 19 | 23.30 | 23.03 | 2.3% |
| nfl:S | no_evidence | 141 | 18 | 27.47 | 27.47 | 0.0% |
| nba:guard | no_evidence | 185 | 48 | 24.26 | 24.26 | 0.0% |
| nba:forward | provisional_point_gate_passed | 168 | 36 | 25.29 | 26.09 | 1.3% |
| nba:center | no_evidence | 71 | 10 | 35.13 | 36.59 | 3.4% |
| nhl:defense | no_evidence | 227 | 43 | 23.87 | 23.90 | -4.3% |
| nhl:center | provisional_point_gate_passed | 207 | 45 | 24.43 | 26.72 | 4.6% |
| nhl:wing | no_evidence | 211 | 58 | 24.41 | 24.41 | 0.0% |
| epl:DEF | provisional_point_gate_passed | 76 | 21 | 24.79 | 26.07 | 16.7% |
| epl:MID | provisional_point_gate_passed | 80 | 33 | 26.38 | 28.71 | 8.8% |
| epl:FWD | insufficient_support | 19 | — | — | — | — |

Sport-macro results (equal weight per fitted role, including no-evidence heads):

| Sport | MAE | Neutral-50 MAE | MSE improvement |
|---|---:|---:|---:|
| epl | 25.59 | 27.39 | 12.7% |
| nba | 28.23 | 28.98 | 1.6% |
| nfl | 24.70 | 24.64 | 0.5% |
| nhl | 24.23 | 25.01 | 0.1% |

5 heads pass the exploratory point checks; 0 have a bootstrap 95% MSE-improvement interval wholly above zero. Passing a point check is not statistical confirmation.

Interval warning: nfl:EDGE has only 75.0% observed test coverage for its nominal 90% interval. This undercoverage must not be hidden or corrected using test labels.

Interval warning: nfl:S has only 77.8% observed test coverage for its nominal 90% interval. This undercoverage must not be hidden or corrected using test labels.

Interval warning: epl:DEF has only 52.4% observed test coverage for its nominal 90% interval. This undercoverage must not be hidden or corrected using test labels.


## Interpretation and limits

Only height and weight are learned common-model inputs. Age/BMI and optional
testing measurements are retained/reported but not silently turned into learned
mental or agility traits. Body measurements are often undated/current snapshots,
so repeated historical rows do not establish changing annual physiques. Missing
height/weight and missing target components are excluded rather than imputed.
At least 50 measured training athletes are required per head; held-out counts do
not decide expert inclusion. EPL forwards currently lack this support, and goalkeepers are
outside the target construct. Physical similarity is separate from efficacy.

Intervals use untouched calibration-athlete residuals (90% split-conformal order
statistic); finite-sample assumptions may fail under selection or distribution
shift. The test coverage/width and athlete-cluster bootstrap improvement intervals
are in evaluation.json. Wide intervals describe genuine uncertainty and must not
be hidden. Body OOD detection abstains outside raw training bounds or the 99%
two-dimensional Mahalanobis ellipse. League, coaching, role, pace and scorer
effects remain. Hits/blocks/pressures are disruption proxies, not demonstrated
possession changes. The chosen composite weights are research assumptions;
equal-domain-weight target sensitivity is included, not optimized against test.

Run `possession-lab efficacy --profile examples/athlete.json` to inspect all roles.
See [design and methods](../../docs/ensemble_design.md) for the full contract.
