---
layout: ../../layouts/ResearchLayout.astro
title: Features and engineered playing profiles
description: A plain-language guide to the physical, native, and transferable features used by the models.
kicker: Feature guide
summary: Features are grouped by the kind of claim they can support. The project does not put every available statistic into one undifferentiated model.
---

## Listed build

The current build layer uses height, weight, body-mass index derived from those two fields, and age. These values support body-fit descriptions and physical-association models.

Body fit answers **“How typical is this listed height and weight for the target role?”** It does not measure talent.

## Native history

The same-sport forecast may use:

- the previous observed role percentile;
- availability relative to role peers;
- sustained three-season performance;
- listed build and age;
- prior sport-specific performance domains.

Only completed-season information may predict the following season.

## Shared performance themes

Sport-specific metrics are converted into a smaller set of common themes before cross-sport comparison.

| Theme | Examples of source evidence |
|---|---|
| Scoring and finishing | Goals, shooting efficiency, receiving or scoring production |
| Creation and distribution | Assists, passing creation, playmaking |
| Possession security | Turnovers, giveaways, puck or ball retention |
| Defensive disruption | Pressures, sacks, steals, blocks, interceptions, takeaways |
| Recovery and rebounding | Rebounds, recoveries, contested possession recovery |
| Progression and territory | Carrying, passing progression, field or ice advancement |
| Discipline and efficiency | Penalties, fouls, cards, efficiency and decision costs |

These labels provide common language, not proof that the underlying techniques are identical.

## Opportunity and reliability

Every target records an opportunity measure appropriate to the sport and role. Low-opportunity players can contribute to training with reduced weight, but only full-strength eligible seasons judge the frozen test.

## Team context

Two completed-season context descriptors were tested:

1. share of the team’s opportunity at the same broad role;
2. reliability-weighted strength of the player’s other teammates.

The player is removed from their own teammate-strength calculation. Team identity and future-season context are never model inputs, and these fields never enter cross-sport comparisons.

## Partial pooling

Related roles can sometimes stabilize a thin role model. The current system begins with a role-specific estimate and tests a small blend toward a predeclared family such as NHL forwards.

The role-only model remains the default. Pooling is used only when its frozen athlete-clustered comparison has a positive lower confidence bound. At present, only NHL right wing cleared that gate.

## Deliberately excluded features

Wingspan, limb length, top speed, agility, reaction speed, awareness and “game IQ” are not yet general model inputs. The project does not have one rights-cleared, season-dated and comparably measured source for these attributes across all four sports.

