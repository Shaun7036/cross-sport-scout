# First research findings

Prepared 17 October 2026 from the completed 2021–2025 / 2021–22 to 2025–26 source snapshots.

## Body shape predicts broad role better than individual effectiveness

The NFL body-only role classifier uses height and weight and excludes unspecified position labels. On 244 athletes first seen with sufficient body data in 2025, it assigns one of six broad defensive roles with 69.7% accuracy, compared with a 19.7% majority-class baseline. Balanced accuracy is 61.4%.

NBA broad guard/forward/center classification reaches 80.2% accuracy versus a 55.7% majority baseline on 106 unseen athletes. NHL center/wing/defense classification is much weaker: 40.5% versus 37.1% on 116 athletes. EPL broad-role classification reaches 50.0% versus 41.3% on 104 athletes.

These figures describe role labels among players who already reached the elite league. They do not measure the probability that someone from another sport could succeed. Position-label granularity and cohort composition differ, so the percentages are not a league ranking.

After controlling for broad role, adding height and weight produces small or inconsistent improvements in NFL event-rate prediction. For example, the held-out physical model's sack-rate MAE is 0.283 versus 0.283 for a role mean, while QB-hit MAE is 0.525 versus 0.523. This supports using physical traits for compatibility and adding actual performance evidence to assess effectiveness.

## Prior performance helps, but rare possession changes remain difficult

The returning-player evaluation uses 2024 to select the model, then evaluates 2025. Rates are per 100 observed defensive scrimmage plays in the NFL and per 100 minutes for NBA/NHL. Each number is meaningful only in that sport and target's unit.

| League / outcome | Selected model | 2025 MAE | Previous-season rate MAE | 2025 R² |
|---|---|---:|---:|---:|
| NFL sacks | Ridge | 0.263 | 0.301 | 0.310 |
| NFL QB hits | Ridge | 0.511 | 0.566 | 0.357 |
| NFL interceptions | Ridge | 0.100 | 0.109 | 0.030 |
| NFL forced fumbles | Ridge | 0.126 | 0.137 | 0.013 |
| NBA steals | Ridge | 1.046 | 1.110 | 0.188 |
| NBA blocks | Previous-season rate | 0.838 | 0.838 | 0.440 |
| NBA defensive rebounds | Ridge | 2.380 | 2.647 | 0.495 |
| NHL takeaways | Ridge | 0.648 | 0.722 | -0.106 |
| NHL blocks | Ridge | 1.357 | 1.479 | 0.440 |
| NHL hits | Previous-season rate | 2.687 | 2.687 | 0.703 |
| NHL faceoff wins | Previous-season rate | 2.793 | 2.793 | 0.854 |

Interceptions and forced fumbles have very low explained variance. NHL takeaway R² remains negative despite a lower absolute error than the other tested baselines. Those outcomes are not ready to support confident individual rankings.

NBA block persistence wins 2024 validation even though ridge performs better in the 2025 evaluation. The selected model remains persistence: changing it after inspecting 2025 would invalidate the stated selection rule.

For opportunity volume, previous-season persistence wins 2024 validation in NFL, NBA and NHL. The expected-count pipeline uses that selected baseline. EPL minutes favor the hurdle model. Logistic availability estimates beat prevalence on validation in all four datasets.

## Soccer supports a narrower, separately tested possession model

The five-year FPL panel provides identity, broad role, minutes and appearance outcomes. The collected detailed event source covers 2025–26 only. Earlier tackle/interception/recovery/block fields stay missing.

The enhanced layer covers 380 matches and 11,492 player appearances. Its recorded totals are 12,604 tackles, 6,267 interceptions, 35,556 recoveries and 2,709 blocks; field definitions and missing coverage are retained.

A separate 2025–26 association model uses 400 players with at least 450 minutes, holding out 100 entire athletes. Inputs are role, age, height and weight, with training-fold imputation. There are no same-season event predictors.

| Target, per 90 minutes | Profile model MAE | Role mean MAE | Interpretation |
|---|---:|---:|---|
| Tackles | 0.569 | 0.563 | Role mean slightly better |
| Interceptions | 0.287 | 0.291 | Small profile-model improvement |
| Recoveries | 0.772 | 0.768 | Role mean slightly better |
| Blocks | 0.154 | 0.171 | Profile model improves in this holdout |

This is a retrospective association test, not a next-season forecast. It needs independent seasons and better historic measurement timing.

## The data cleaning changes the scientific interpretation

NFL weekly totals can include special-team tackles and forced fumbles. Using them over a scrimmage denominator creates extreme rates for players who mostly play special teams. The primary NFL numerator and denominator now use the same scrimmage-play scope.

NFL participation switches from NGS to FTN in 2023. It identifies players on a play, not every individual rush or coverage assignment. Pressure exposures must retain that limitation.

An event-by-event participation audit found three 2025 player-games with 29 credited metric rows but no matching defender participation. Their three player-seasons retain the observed partial exposure for inspection and are excluded from rate-model evaluation. The PBP negative-play tackle measure is explicitly separated from official TFL because those definitions differ before 2024. Double-fumble recovery order, attributed safety counts, and overlapping sack/hit credits have dedicated checks.

NBA All-Star and NBA Cup championship games need explicit removal from ESPN season_type=2 rows. The resulting five seasons each reconcile to 1,230 standings games and 82 games per team.

MoneyPuck all-situation and 5-on-5 rows overlap. They are stored in separate columns and never summed. All NHL game totals reconcile exactly to seasonal TOI and the selected event counts.

Historical NBA and NHL height/weight records are often regenerated current profiles. They do not establish genuine annual body-mass changes. The forecast therefore uses prior event history and excludes those undated physical values; physical association models disclose their different interpretation.

## Next research priorities

1. Establish comparable pressure, coverage and missed-tackle usage rights and definitions, then evaluate the already-cleaned NFL enhanced table.
2. Add broader prospect testing and limb measurements under suitable source terms; quantify selection and measurement-age effects.
3. Add scheme, opponent and game-state adjustment, using player-play records rather than attributing whole-team EPA to an individual.
4. Obtain NBA hustle/tracking and NHL skating-speed coverage with consistent history.
5. Acquire a comparable multi-season soccer defensive feed.
6. Freeze a future evaluation before promoting hidden-value rankings or a cross-sport success claim.

The current command-line scorer is a physical compatibility prototype. A trained, validated cross-sport transfer ensemble remains a later research stage.
