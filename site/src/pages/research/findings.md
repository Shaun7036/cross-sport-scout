---
layout: ../../layouts/ResearchLayout.astro
title: What the exploratory analysis showed
description: Important EDA findings across the four athlete datasets.
kicker: Findings
summary: The most useful discoveries were practical warnings about unequal samples, opportunity, physical-data timing, and what a missing result means.
---

## Dataset scale is uneven

Role sizes range from large NFL receiver and defensive cohorts to much smaller specialist groups. A single confidence rule cannot treat every role equally.

<img src="../../images/eda/role_cohort_counts.png" alt="Player-season counts by sport and role" loading="lazy">

## Playing time changes the meaning of a statistic

Tackles, sacks, steals, recoveries, goals and assists all depend on opportunity. The pipeline therefore records role-appropriate exposure, creates rate or efficiency measures where defensible, and reduces the influence of short samples.

## Physical completeness is not physical history

The NFL has genuine historical testing measurements for some athletes. Much of the NBA, NHL and Premier League physical data comes from current or undated profiles. Repeating a profile value beside several seasons does not turn it into several measurements.

<img src="../../images/eda/listed_build_map.png" alt="Listed height and weight coverage by sport and role" loading="lazy">

## Broad roles are more honest than false precision

Public data can support NBA guard, forward and center or Premier League goalkeeper, defender, midfielder and forward. It cannot consistently separate every tactical assignment across five seasons.

## No score is not a zero

The pipeline retains rostered athletes even when it cannot produce a defensible performance target. Offensive linemen and long snappers are important examples: their identities and builds remain useful, but the available public summaries do not justify a released individual quality score.

## Playing profile can add information—but not everywhere

The build-plus-profile model is compared with the build-only model before it can be promoted. Some roles clear this incremental test and others do not.

<img src="../../images/eda/profile_increment_vs_build.png" alt="Comparison of build-only and build-plus-profile model error" loading="lazy">

## Team context did not clear the final evidence gate

Completed-season workload share and leave-one-player-out teammate strength were tested as optional native-forecast inputs. No role beat both the existing role/history model and the stronger history baseline confidently enough, so none entered the deployed estimates.

This is a useful negative result: a plausible feature is not automatically a useful predictive feature.

