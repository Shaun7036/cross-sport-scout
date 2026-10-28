---
layout: ../../layouts/ResearchLayout.astro
title: From four leagues to one careful comparison
description: The research process and data pipeline behind The Multi Sport Scouter.
kicker: Research journey
summary: The project began with possession-winning athletes and grew into a broad-role comparison across the NFL, NBA, NHL, and Premier League.
---

## The research question

The project asks whether an athlete’s listed build and demonstrated style of play resemble the profiles associated with roles in another sport.

That question contains three smaller questions that must remain separate:

1. **Description:** where did the athlete rank against people playing the same role in the same season?
2. **Forecasting:** what does prior information suggest about their next season in that same role?
3. **Analogy:** which roles elsewhere have similar physical and broad performance profiles?

> The cross-sport output is an exploratory analogy—not the probability of making a roster or learning a new sport successfully.

## The current research panel

| League | Player-seasons | Broad roles | Main opportunity measure |
|---|---:|---:|---|
| NFL | 15,518 | 14 | Games, snaps and role-specific chances |
| NBA | 2,866 | 3 | Minutes and games |
| NHL | 5,263 | 5 | Ice time and games |
| Premier League | 4,005 | 4 | Minutes and appearances |

The five-season window covers 2021 through 2025. For basketball, hockey and football, the season label refers to the season beginning in that year.

## Six pipeline stages

### 1. Preserve the source

Every acquisition keeps its source URL, retrieval time, file hash, season and usage notes. Raw files are kept separate from derived modeling tables.

### 2. Build a common row shape

Each sport becomes one player-season table containing identity, broad role, opportunity, listed physical fields and sport-specific performance measures.

### 3. Define defensible roles

The project uses broad roles supported by public data. It avoids inventing precise tactical assignments that would require tracking, lineup or coaching information.

### 4. Make seasons comparable

Performance is converted to a percentile within the same sport, role and season. Low-opportunity results are pulled toward the peer-group average and receive less training weight.

### 5. Look forward chronologically

Models learn from completed seasons and predict the following season. The 2025 season remains frozen for final evaluation, while earlier seasons provide rolling checks.

### 6. Publish with guardrails

The site explains the type of score, supporting evidence and prediction range. It withholds an answer when required measurements, overlap or validation evidence are missing.

## Why Python is still part of a static site

Python remains responsible for acquiring data, training models, validating them and exporting a frozen public snapshot. Astro and Markdown present that snapshot without running models or requiring a Python server when a visitor opens the portfolio.

