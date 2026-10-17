# EPL 2025-26 recent-season possession association

This is a retrospective player-held-out association, not a temporal or next-season forecast.
Cohort: 400 players with at least 450 league minutes; 300 train and 100 unseen test athletes.
Inputs are broad FPL role, age, height, and weight. No same-season event statistic is an input.
Targets are genuine FPL-Core-Insights tackles, interceptions, recoveries, and blocks per 90.
The comparison baseline is the target's training-fold mean within broad role.

| Target | Test n | Ridge MAE | Role-mean MAE | Spearman |
|---|---:|---:|---:|---:|
| tackles | 100 | 0.569 | 0.563 | 0.5180634422800378 |
| interceptions | 100 | 0.287 | 0.291 | 0.7117501193364947 |
| recoveries | 100 | 0.772 | 0.768 | 0.6048846351768024 |
| blocks | 97 | 0.154 | 0.171 | 0.7074039901793886 |

Negative improvement is an honest result: it means the simple role mean beat the profile model.
Current profile snapshots and broad roles limit causal or scouting interpretation.
