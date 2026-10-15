# Boosted-model training-size comparison

All four new experiments completed and were downloaded and verified locally on 15 October 2026. The experiment cluster is STOPPED; its scheduled deletion remains 15 October 2026 at 17:23:45 Singapore time.

At 100% training, mean Brier is slightly lower than at 15% in both modes, but the observed gains are small (0.013% short-term; 0.083% calendar) and do not establish statistical significance.

 Training uses 2017–2021, depth selection uses 2022, temperature selection uses 2023, and evaluation uses 2024. Means equally weight the original seven thresholds (0, 0.2, 1, 2, 5, 10, 20 mm). Lower Brier and log loss are better.

| Mode | GBT training | Mean Brier | Mean log loss | Mean PR-AUC | Depth | Temperature |
|---|---:|---:|---:|---:|---:|---:|
| short_term | 15% | 0.01622929 | 0.07216669 | 0.315004 | 5 | 0.75 |
| short_term | 30% | 0.01623889 | 0.07219660 | 0.313947 | 5 | 0.75 |
| short_term | 100% | 0.01622724 | 0.07215140 | 0.314646 | 5 | 0.75 |
| calendar | 15% | 0.02290321 | 0.10789135 | 0.047363 | 5 | 1.0 |
| calendar | 30% | 0.02290187 | 0.10789162 | 0.047226 | 5 | 1.0 |
| calendar | 100% | 0.02288430 | 0.10782866 | 0.048703 | 5 | 1.0 |

short_term: Brier error changes by +0.059% at 30% versus 15%, and -0.013% at 100% versus 15%. The 100%-versus-30% change is -0.072%. These are relative error changes.

| Training | Fitted anchors | Test anchors per threshold | GBT Brier change vs saved 15% RF | Threshold-order violation rate |
|---|---:|---:|---:|---:|
| 30% | 5,608,769 | 5,729,508 | +0.672% | 0.049106% |
| 100% | 18,688,263 | 5,729,508 | +0.600% | 0.068076% |

| Threshold (mm) | 15% GBT Brier | 30% GBT Brier | 100% GBT Brier |
|---|---:|---:|---:|
| 0 | 0.03836080 | 0.03839146 | 0.03835398 |
| 0.2 | 0.03077272 | 0.03076290 | 0.03074380 |
| 1 | 0.01869863 | 0.01874618 | 0.01873371 |
| 2 | 0.01371812 | 0.01370211 | 0.01369607 |
| 5 | 0.00741864 | 0.00743666 | 0.00742522 |
| 10 | 0.00359944 | 0.00359632 | 0.00360102 |
| 20 | 0.00103672 | 0.00103662 | 0.00103691 |

calendar: Brier error changes by -0.006% at 30% versus 15%, and -0.083% at 100% versus 15%. The 100%-versus-30% change is -0.077%. These are relative error changes.

| Training | Fitted anchors | Test anchors per threshold | GBT Brier change vs saved 15% RF | Threshold-order violation rate |
|---|---:|---:|---:|---:|
| 30% | 8,233,882 | 6,374,476 | +0.699% | 0.523762% |
| 100% | 27,434,001 | 6,374,476 | +0.622% | 0.616445% |

| Threshold (mm) | 15% GBT Brier | 30% GBT Brier | 100% GBT Brier |
|---|---:|---:|---:|
| 0 | 0.05831338 | 0.05830069 | 0.05823336 |
| 0.2 | 0.04543310 | 0.04543172 | 0.04538057 |
| 1 | 0.02500931 | 0.02501555 | 0.02501187 |
| 2 | 0.01678426 | 0.01678102 | 0.01678096 |
| 5 | 0.00873433 | 0.00873589 | 0.00873513 |
| 10 | 0.00437590 | 0.00437593 | 0.00437591 |
| 20 | 0.00167215 | 0.00167229 | 0.00167229 |

The new sample sizes independently selected depth and temperature, so these results compare selected systems. They do not isolate sample size at fixed depth and calibration. The saved RF/LR baselines use 15%; the user’s separately completed 100% classifier results were not supplied for numerical comparison.

Daily counts and squared errors reconcile with exported Brier scores, and evaluation counts/prevalence agree across training fractions and saved baselines. Matching counts and prevalence do not by themselves prove identical raw observations. Results remain supplementary because this design followed inspection of the original 2024 scores. Differences reflect one fitted model per fraction and one seed; they do not establish refitting variance or independent future-year confirmation.

Sources: complete raw archive `../gbt-sampling-20261014-run01-results.zip`; prior 15% short-term archive and calendar export supplied by the user.
