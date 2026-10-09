# Task 2 real-data results

Both models estimate strict P(next 30-minute amount > threshold).
A uses available own-station history; B uses station/calendar only. No neighbor features.

On 5,729,508 shared 2024 anchors, the equal-threshold mean Brier score is 0.01613 for A and 0.02283 for B (29.4% lower for A). This is a reduction in probability squared error, not a percentage-point accuracy gain.
Brier is lower-is-better; PR-AUC is higher-is-better. AUC uses Spark numBins=1000 downsampling and can vary slightly with partitioning.

## A: short-term

RF depth 8, trees 40, temperature 1.0; train fraction 0.15, evaluation fraction 1.0.
Training: 2017–2021; validation: 2022; calibration: 2023; test: 2024.
Split counts: `{"train_full": 18688263, "train_sample": 2802737, "validation": 6133684, "calibration": 5465591, "test": 5729508}`.

| Threshold mm | Model | Test n | Event rate | Brier | PR-AUC |
|---:|---|---:|---:|---:|---:|
| 0.0 | binary_logistic | 5729508 | 0.06398 | 0.04862 | 0.53291 |
| 0.0 | climatology | 5729508 | 0.06398 | 0.05868 | 0.11410 |
| 0.0 | random_forest | 5729508 | 0.06398 | 0.03798 | 0.60842 |
| 0.2 | binary_logistic | 5729508 | 0.04892 | 0.03632 | 0.49990 |
| 0.2 | climatology | 5729508 | 0.04892 | 0.04574 | 0.09088 |
| 0.2 | random_forest | 5729508 | 0.04892 | 0.03090 | 0.55701 |
| 1.0 | binary_logistic | 5729508 | 0.02579 | 0.01991 | 0.36294 |
| 1.0 | climatology | 5729508 | 0.02579 | 0.02495 | 0.04671 |
| 1.0 | random_forest | 5729508 | 0.02579 | 0.01870 | 0.42180 |
| 2.0 | binary_logistic | 5729508 | 0.01686 | 0.01482 | 0.25157 |
| 2.0 | climatology | 5729508 | 0.01686 | 0.01652 | 0.03122 |
| 2.0 | random_forest | 5729508 | 0.01686 | 0.01349 | 0.31537 |
| 5.0 | binary_logistic | 5729508 | 0.00829 | 0.00932 | 0.12685 |
| 5.0 | climatology | 5729508 | 0.00829 | 0.00822 | 0.01587 |
| 5.0 | random_forest | 5729508 | 0.00829 | 0.00732 | 0.18851 |
| 10.0 | binary_logistic | 5729508 | 0.00378 | 0.00524 | 0.06296 |
| 10.0 | climatology | 5729508 | 0.00378 | 0.00377 | 0.00719 |
| 10.0 | random_forest | 5729508 | 0.00378 | 0.00354 | 0.10204 |
| 20.0 | binary_logistic | 5729508 | 0.00100 | 0.00186 | 0.01678 |
| 20.0 | climatology | 5729508 | 0.00100 | 0.00100 | 0.00182 |
| 20.0 | random_forest | 5729508 | 0.00100 | 0.00098 | 0.03035 |

## B: calendar risk

RF depth 8, trees 40, temperature 1.0; train fraction 0.15, evaluation fraction 1.0.
Training: 2017–2021; validation: 2022; calibration: 2023; test: 2024.
Split counts: `{"train_full": 27434001, "train_sample": 4115222, "validation": 7107898, "calibration": 6719274, "test": 6374476}`.

| Threshold mm | Model | Test n | Event rate | Brier | PR-AUC |
|---:|---|---:|---:|---:|---:|
| 0.0 | binary_logistic | 6374476 | 0.06360 | 0.06014 | 0.09657 |
| 0.0 | climatology | 6374476 | 0.06360 | 0.05812 | 0.11972 |
| 0.0 | random_forest | 6374476 | 0.06360 | 0.05890 | 0.11073 |
| 0.2 | binary_logistic | 6374476 | 0.04858 | 0.04614 | 0.08129 |
| 0.2 | climatology | 6374476 | 0.04858 | 0.04523 | 0.09759 |
| 0.2 | random_forest | 6374476 | 0.04858 | 0.04583 | 0.08901 |
| 1.0 | binary_logistic | 6374476 | 0.02569 | 0.02488 | 0.04282 |
| 1.0 | climatology | 6374476 | 0.02569 | 0.02476 | 0.05160 |
| 1.0 | random_forest | 6374476 | 0.02569 | 0.02490 | 0.04936 |
| 2.0 | binary_logistic | 6374476 | 0.01683 | 0.01655 | 0.02842 |
| 2.0 | climatology | 6374476 | 0.01683 | 0.01643 | 0.03495 |
| 2.0 | random_forest | 6374476 | 0.01683 | 0.01648 | 0.03387 |
| 5.0 | binary_logistic | 6374476 | 0.00834 | 0.00841 | 0.01434 |
| 5.0 | climatology | 6374476 | 0.00834 | 0.00826 | 0.01817 |
| 5.0 | random_forest | 6374476 | 0.00834 | 0.00826 | 0.01833 |
| 10.0 | binary_logistic | 6374476 | 0.00382 | 0.00390 | 0.00672 |
| 10.0 | climatology | 6374476 | 0.00382 | 0.00381 | 0.00857 |
| 10.0 | random_forest | 6374476 | 0.00382 | 0.00380 | 0.00895 |
| 20.0 | binary_logistic | 6374476 | 0.00103 | 0.00105 | 0.00214 |
| 20.0 | climatology | 6374476 | 0.00103 | 0.00103 | 0.00234 |
| 20.0 | random_forest | 6374476 | 0.00103 | 0.00103 | 0.00317 |

## Fair comparison on shared 2024 anchors

| Threshold mm | RF mode | Test n | Brier | PR-AUC |
|---:|---|---:|---:|---:|
| 0.0 | calendar | 5729508 | 0.05924 | 0.10968 |
| 0.0 | short_term | 5729508 | 0.03798 | 0.60910 |
| 0.2 | calendar | 5729508 | 0.04614 | 0.08811 |
| 0.2 | short_term | 5729508 | 0.03090 | 0.55818 |
| 1.0 | calendar | 5729508 | 0.02499 | 0.04837 |
| 1.0 | short_term | 5729508 | 0.01870 | 0.42154 |
| 2.0 | calendar | 5729508 | 0.01652 | 0.03290 |
| 2.0 | short_term | 5729508 | 0.01349 | 0.31548 |
| 5.0 | calendar | 5729508 | 0.00820 | 0.01759 |
| 5.0 | short_term | 5729508 | 0.00732 | 0.18850 |
| 10.0 | calendar | 5729508 | 0.00376 | 0.00847 |
| 10.0 | short_term | 5729508 | 0.00354 | 0.10200 |
| 20.0 | calendar | 5729508 | 0.00100 | 0.00292 |
| 20.0 | short_term | 5729508 | 0.00098 | 0.03036 |

Comparison audit: `{"counts": {"calendar": 6374476, "short_term": 5729508, "common": 5729508}, "short_term_coverage_of_calendar_test": 0.8988202324394978, "comparison": "RF models on identical test anchors; trained on their respective eligible samples", "thresholds": [0.0, 0.2, 1.0, 2.0, 5.0, 10.0, 20.0]}`.

Individual model metrics can use different eligible populations. Use the shared-anchor table for direct comparisons.
Five-minute windows overlap; samples are not independent storms. Binary LR is uncalibrated.
Calendar risk is a historical seasonal estimate, not a forecast of specific future storm conditions.
