# Unified physical-profile ensemble design

## What the output means

The ensemble accepts an adult athlete's physical profile and evaluates it against the observed elite
athletes in each supported sport and role. It keeps two 0–100 concepts separate:

1. **Physical compatibility**: role-relative similarity to the height-and-weight profiles observed among
   elite athletes in that sport and role.
2. **Expected disruption efficacy**: the role-relative standing of the model's expected possession or
   disruption profile, based on the supported body inputs and the evidence available for that sport-role.

Expected disruption efficacy is published as a primary rating only when its evidence gate passes. If the
gate fails, the primary rating is null. A numerical result may still be retained under an explicitly
`experimental` label for diagnosis; it is not silently promoted to a supported rating.

Neither output is a probability of entering a league, earning playing time, succeeding after a transfer,
or transferring skill between sports. Physical compatibility is not a role classifier: an athlete can
look physically typical for several roles. Expected efficacy is a standardized association within an
elite sport-role reference cohort, not evidence that raw events have identical meaning across sports.

## Core profile contract and learned inputs

The normalized profile schema is deliberately small:

| Feature | Input contract | Use in the chosen common efficacy model |
|---|---|---|
| `height_cm` | Required, finite, positive | Learned input. |
| `weight_kg` | Required, finite, positive | Learned input. |
| `age` | Optional; if supplied, 18–100 | Retained and reported, not learned. |
| `bmi` | Derived from normalized height and weight | Retained and reported, not learned. |

The **primary common efficacy model deliberately uses height and weight only**. Age and BMI remain in the
canonical feature schema for validation, provenance, and display. This implementation does not silently
impute missing ages into an age-inclusive model. A field's presence in the normalized profile is not a
claim that the estimator learned from it.

`prepare_profile_features` creates the four numeric schema columns on a copy of a canonical player table
and does not mutate the source table. `validate_profile` handles interactive or API input. It accepts
`height_cm`, `height_inches`, or a `height_ft` plus `height_in` pair, and accepts `weight_kg` or
`weight_lb`. Redundant aliases must agree after conversion. The validator rejects nonnumeric, nonfinite,
zero, and negative core values. It rejects ages below 18 because this is an adult-only model contract and
rejects ages over 100 as malformed input.

Unusual but positive height, weight, BMI, or age values are returned unchanged with warnings. They are
never silently clipped into the training distribution.

The normalized return shape is:

```text
{
  "features": {"height_cm": ..., "weight_kg": ..., "age": ..., "bmi": ...},
  "provided_extra_measurements": {...},
  "warnings": [...],
  "unsupported_features": [...]
}
```

## Unsupported inputs

Wingspan, arm length, leg length, hand measurements, top speed, combine splits, jumps, agility drills,
and body-fat percentage are retained in `provided_extra_measurements` when explicitly labelled with
their units. They are unsupported by the currently learned common model and do not affect either rating.
Their definitions, timing, equipment, and coverage vary by sport, so treating absence as a typical value
would manufacture comparability. They are retained only for transparent display and provenance.

Reaction speed, spatial awareness, anticipation, decision accuracy, and similar proposed mental or
game-awareness variables are not trained inputs. Public league data do not provide harmonized
athlete-level measurements with common protocols across these four sports. Such keys appear in
`unsupported_features`; they receive no synthetic value, proxy, or hidden default. The model makes no
claim about cognitive ability, tactical awareness, anticipation, or decision quality.

## Target construction

Raw tackles, blocks, pressures, takeaways, recoveries, and other events are never pooled across sports.
Each target retains its sport-specific definition and opportunity denominator. It is then mapped through
an empirical reference CDF fitted separately for each sport × role × season from training-athlete rows
only. This season-specific reference prevents a provider-definition or league-distribution change from
being misread as athlete decline. Every inner and outer fold refits its reference CDF using only that
fold's training athletes.

Within a role, available standardized target heads are combined using documented hand-set target weights
frozen as version 1. Changing those weights is a model-version change. A missing target remains
unavailable rather than becoming zero, and every result reports which target heads contributed.

## Expert library and nonnegative stack

Each local sport-role model supplies four height-and-weight experts:

- regularized ridge regression;
- histogram gradient boosting;
- extremely randomized trees; and
- a soft-archetype similarity expert.

A fifth learned expert is shared across roles and sports: polynomial ridge on height and weight after
role-standardization. A constant-50 expert supplies an explicit neutral baseline. The stack assigns
nonnegative weights to expert predictions. Those weights are learned only from inner out-of-fold
predictions for training athletes, so an expert is never weighted from its own in-sample fitted values.

The evidence gate uses outer athlete-grouped cross-validation inside the training partition. When that
nested evidence does not pass the prespecified baseline comparison, primary
`efficacy_rating` is null and any estimate is labelled experimental. Independently, a
sport-role-target head abstains when it has fewer than 50 measured training athletes. Held-out
eligibility counts never determine which experts are fitted. These are abstentions, not zero-efficacy ratings.

## Athlete-held-out partitions

A stable athlete hash assigns identities—not rows—to 60% training, 20% calibration, and 20% test
partitions. Its salt is frozen independently of model version and recorded in the registry. One athlete
can never appear in more than one partition.

- Training athletes may contribute usable rows from 2021 through 2025, including 2025. This supports a
  contemporaneous physical association and sport × role × season reference distributions.
- Calibration and test athletes contribute only their 2025 rows. Their identities are unseen during
  model fitting.
- Inner and outer validation folds remain athlete-grouped and refit both experts and season reference
  CDFs inside each fold.
- The frozen 2025 unseen-athlete test partition is used for the external report and a release gate
  (positive rank association and MSE improvement, at least 15 test and 9 calibration athletes).
  It is not used to select experts, learn weights or tune thresholds. Failed release evidence withholds
  the primary rating without changing frozen predictions. Prior project QA has inspected this source
  snapshot; this is not a new blind or prospective benchmark.

This is a descriptive contemporaneous evaluation: given height and weight, how well does the fitted
association generalize to unseen elite athletes in a 2025 reference? It is **not** a temporal, preseason,
player-development, cognitive-ability, or cross-sport-transition forecast.

The Premier League has genuine disruption targets only for 2025–26. Its evaluation is therefore a
same-season unseen-athlete holdout under the same descriptive contract, not a temporal event forecast.

## Calibration and uncertainty

The calibration partition supplies split-conformal residual quantiles for provisional prediction
intervals. These intervals summarize residual behavior under the held-out calibration contract. Their
usual coverage rationale depends on exchangeability; source-definition changes, season drift, the
selected elite-athlete population, and an outside-sport athlete can violate that assumption. The
intervals are therefore provisional diagnostics, not guaranteed cross-sport-transition coverage.

The current run has five heads passing exploratory point checks, but all 95% bootstrap improvement
intervals include zero. No head has statistically established improvement. EPL defenders' nominal-90%
interval has only 52.4% observed test coverage; this is explicitly flagged as poorly calibrated, not
repaired using test outcomes. A primary numerical score is still only a provisional research estimate.

## Out-of-distribution checks and physical fit

Out-of-distribution checks use the two learned body inputs. The report tests both the raw training bounds
for height and weight and a two-dimensional Mahalanobis distance in the applicable body-reference cohort.
Values are not clipped when they cross either check.

Physical compatibility is calculated and displayed separately from disruption efficacy. It describes
body-profile fit to a sport-role reference; it does not rescue an efficacy head that abstained or failed
the evidence gate. Conversely, evidence for a disruption association does not turn physical fit into a
probability of playing that role.

The sport-level summary is the maximum eligible role estimate, a convenience for browsing. That
maximum has no separate sport-level calibration, and its interval is not a simultaneous interval over
all roles. Comparing the sport summaries is exploratory, not a validated ranking of sport-switching
potential.

## Required reporting

For every sport-role result, the implementation reports:

- sport, role, season, and reference cohort;
- primary or experimental status and any abstention reason;
- model and baseline athlete-held-out results;
- input, target, and physical-profile coverage;
- expert provenance and the frozen target-weight version;
- which target heads contributed and which were unavailable;
- physical out-of-distribution status, raw-bound checks, and input warnings;
- provisional interval and calibration size when available; and
- source-timing and interpretation limitations.

The rating omits technical skill, tactics, assignment, coaching, health, development, competition level,
roster constraints, and the opportunity an athlete would receive. It must not be labelled a transferable
success probability.

## Evidence boundaries

The four sport panels do not have identical evidence depth. The Premier League common panel has five
seasons of roster and minutes data, but genuine tackles, interceptions, recoveries, and blocks are
available only for 2025–26 from the enhanced source. Its efficacy model therefore uses an entire-player
holdout within that season and is explicitly retrospective.

The NHL source shows a marked takeaway-rate shift starting in 2024. The audit establishes distribution
drift, not its cause; it does not independently establish a formal definition change. A pooled-year
target CDF produced low 2025 ranks partly because it compared different seasonal distributions. The
implemented sport × role × season reference CDF addresses that scale issue while preserving the
descriptive, contemporaneous scope. It cannot correct all scorer, provider or assignment biases.

Across sports, many height and weight values are current or archived profile listings rather than dated
measurements taken in each season. A current listing repeated onto historical rows is not historical body
change and cannot support a point-in-time claim. Combine measurements may be older than performance
outcomes, while current roster measurements may be newer. Every rating retains the applicable
source-timing warning.

All training cohorts consist of athletes who already reached an elite league. Results are conditional on
that selected population. They cannot estimate an outside athlete's probability of reaching a league
without representative non-elite examples and a different study design.

## Method references

- [scikit-learn `StackingRegressor` documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.StackingRegressor.html), for the general out-of-fold stacking pattern. The implemented stack additionally constrains weights to be nonnegative and includes a constant-50 expert.
- [scikit-learn `GroupKFold` documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html), for identity-grouped folds that keep an athlete out of both sides of a split.
- Angelopoulos and Bates, [*A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification*](https://arxiv.org/abs/2107.07511), for split-conformal methodology and its assumptions.
