# Model releases

This release is a research baseline built from actual public source snapshots. The tasks have separate interpretations.

## Unified physical efficacy ensemble (v1)

The `efficacy` command is distinct from the original role classifier and returning-player
forecast. It combines four local experts, one shared role-standardized polynomial
expert, and a neutral-50 expert into separate sport-role heads. Nonnegative stack
weights use inner athlete-disjoint out-of-fold predictions; outer folds gate model
selection. Height and weight are the only learned common inputs. Identifiers,
opportunity, season and event counts never enter the physical regressors.

The response is a shrunk possession/disruption activity composite, mapped to an
elite-peer percentile within sport, role and season. The complete reference
transform is refitted inside each training fold. This avoids confusing provider/year
drift with physical associations. Domain weights are hand-specified research choices
with an equal-weight sensitivity audit, not empirically established definitions of
overall defensive value. Low-minute players and missing body/event records do not
become low-efficacy labels; they are outside this model's eligible universe.

All seasons of an athlete share a deterministic train/calibration/test partition.
Training athletes contribute 2021–25, including 2025 contemporary reference rows;
calibration and frozen test use unseen 2025 athlete identities. EPL has only 2025
possession labels. This is a descriptive contemporaneous association evaluation,
not a point-in-time or preseason forecasting experiment. Final-test metrics can
withhold a primary rating but do not retune model weights. These tests were inspected
during development; a prospective external dataset remains necessary for
confirmatory claims.

The scorer reports all roles, separate physical similarity, provisional 90%
prediction intervals, sample sizes and evidence status. It abstains on insufficient
measured reference support, out-of-domain physiques and unhelpful held-out models.
Experimental estimates are labeled and retained for auditing. Primary sport output
selects the highest supported in-domain role estimate; that maximum has no separate
sport-level calibration, and should not be treated as a validated sport ranking.
Intervals cover an individual's observed activity target, not uncertainty in the
population mean or a professional-success probability. No true sport-switching
outcomes or measured mental/reaction features are available.

See [ensemble design](ensemble_design.md) and [evaluation](../reports/ensemble/findings.md).

## Returning-player forecasting

Development targets are 2022 and 2023, validation is 2024, and the evaluation target is 2025. Outside the NFL, these numbers identify the season start year. Every candidate is selected from the previous season, so a player who does not return remains a zero-opportunity outcome.

The pipeline predicts appearance, opportunity, and each supported event rate. It compares availability with prevalence, opportunity with prior-season persistence, and effectiveness with role means and prior rates. Model and baseline selection use 2024 only. Selected component models are refitted through 2024 before evaluating 2025.

Features are previous-season opportunity, three-observation exponential averages, prior role, prior age, and prior event rates. Identifiers are join/group keys. Current physical listings are excluded because source records do not prove historical publication dates.

Default rate errors are measured per 100 sport-specific units: NFL scrimmage participation or minutes in the other leagues. Those raw errors cannot be compared between sports.

Effectiveness evaluation is conditional on positive future opportunity. Availability and total-count evaluation retain nonreturners. Expected contribution uses a rate estimate multiplied by the selected unconditional opportunity estimate; availability is multiplied once only when the selected opportunity component is the hurdle model.

These are retrospective development evaluations. Final source snapshots contain statistical corrections, and 2025 outputs were inspected during pipeline QA. A future frozen evaluation on genuinely unobserved data is needed before making confirmatory deployment claims.

## Physical role compatibility

A logistic classifier maps observed height and weight to broad role labels. Development athletes are first seen with sufficient body data by 2024, and the 2025 test athletes were not seen earlier with sufficient body data. First-seen year is not assumed to be actual professional entry year. A recent-only physical source uses a separately identified descriptive athlete holdout. Unspecified/unknown role labels are excluded from the classifier.

Body listings are often current or undated. This model therefore measures descriptive body-role association among selected elite athletes. Its probabilities do not measure a person's probability of becoming a professional or succeeding after a cross-sport transition.

## Physical effectiveness association

Separate ridge models relate body measurements and age to an event rate conditional on role and at least 100 opportunity units. Entire athletes are isolated by deterministic SHA-256 partitions; model fitting uses seasons through 2023, selection uses 2024, and evaluation uses different athletes in 2025.

The model must be compared with a role-mean baseline. A good correlation across roles does not prove physical measurements explain differences within a role. Current results and baseline errors remain visible, including failures to improve.

Current source listings make this an association model, rather than a historical deployment forecast.

## Archetypes

Physical archetypes use unique athletes and body measurements within a broad role. Play-style archetypes use empirical shrinkage and role-relative event rates. Cluster counts and silhouette are descriptive; bootstrap stability is reported. Event-based clusters do not independently prove that a cluster is successful.

## Missing data and selection

Missing labels remain null. An absent observation, a structural zero, and no opportunity are distinct. Imputation and scaling are fitted on development data. Prospect testing is selected by invitations, injury and drill participation; it is not representative of every rostered athlete.

Athletes in these datasets already passed elite selection systems. No model in this release estimates the causal effect of body type or the probability that an arbitrary person could switch sports.

## Soccer boundary

Detailed tackles, interceptions, blocks, and recovery labels are available in the collected 2025-26 enhanced source, not as consistent five-year targets. The pipeline can model historical availability and minutes, but it will not fit a five-year possession forecast from incompatible fantasy proxies. A separately reported 2025 association model has a different evaluation design.

## Scope still requiring richer data

Complete rush/coverage assignments, NFL top speed, NBA hustle/tracking, NHL full-roster EDGE measurements, five-year comparable soccer defensive events, and directly measured cognition are outside this first baseline. Existing source adapters and data cards expose these gaps.
