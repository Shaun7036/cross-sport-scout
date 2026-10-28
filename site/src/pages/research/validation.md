---
layout: ../../layouts/ResearchLayout.astro
title: How the models are trained and checked
description: Chronological testing, athlete-disjoint diagnostics, calibration, prediction ranges, and validation boundaries.
kicker: Training and validation
summary: Every model must answer a future-season question and beat declared baselines before stronger language is allowed.
---

## Training, validation and frozen testing

The main evaluation is chronological:

1. learn from seasons before the target season;
2. create a prediction using only information available beforehand;
3. evaluate the frozen 2025 season once;
4. compare the model with neutral, prior-season and sustained-history baselines.

The 2025 results do not choose features or tune thresholds after the fact.

## Athlete-disjoint diagnostics

A separate pre-2025 diagnostic groups rows by athlete so the same person cannot appear in both sides of a fold. This measures generalization to unseen identities. It complements chronological testing but does not replace it.

## Prediction ranges

Nominal 90% ranges use rolling-origin absolute residuals, retaining one latest residual per athlete. The reported frozen empirical coverage shows how often the range actually contained the held-out result.

A wide range is not a presentation defect. It is an honest sign that the available data does not justify a precise estimate.

## Calibration and top-decile checks

Predictions are grouped into fixed percentile bins and compared with observed outcomes. The reports also test whether predicted top-decile athletes are actually concentrated near the top of the held-out cohort.

## Predeclared face-validity cases

Stephen Curry’s scoring profile and LeBron James’s creation profile were declared before the final check. They confirm that the engineered domains recognize obvious elite cases without allowing those players to tune the model.

Their broad role scores answer a larger question. Curry can have an elite scoring dimension while his overall guard score also reflects availability, defense, recovery, possession security and other components.

## Evidence-gated additions

Team context and related-role partial pooling were not added merely because they sounded plausible.

- **Team context:** zero role heads cleared every declared comparison.
- **Partial pooling:** one head—NHL right wing—produced a small but supported improvement.

## The cross-sport validation boundary

The project can validate native descriptions and next-season target-role models. It cannot validate actual success after changing sports because there is no large, representative set of elite athletes making those transfers.

Cross-sport scores therefore remain analogies for research and follow-up, never conversion probabilities.

