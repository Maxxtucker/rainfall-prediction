# RF sensitivity results: 2022 validation only

Original final models are preserved. Positive improvement means lower Brier error.

## short_term

| Candidate | Sample | Depth | Trees | Min leaf | Features | Validation Brier | Fit minutes |
|---|---:|---:|---:|---:|---|---:|---:|
| original15 | 15% | 8 | 40 | 25 | sqrt | 0.01669750 | -- |
| sample30 | 30% | 8 | 40 | 25 | sqrt | 0.01669544 | 2.0 |
| depth10 | 15% | 10 | 40 | 25 | sqrt | 0.01664745 | 1.9 |
| trees80 | 15% | 8 | 80 | 25 | sqrt | 0.01669631 | 2.4 |
| leaf50 | 15% | 8 | 40 | 50 | sqrt | 0.01671066 | 1.2 |
| features_half | 15% | 8 | 40 | 25 | 0.5 | 0.01668206 | 1.4 |
| selected30 | 30% | 10 | 40 | 25 | sqrt | 0.01663765 | 3.2 |

original15 → sample30: relative validation Brier improvement **0.012%**; conditional 95% seven-day block interval [-0.014%, 0.039%].

original15 → depth10: relative validation Brier improvement **0.300%**; conditional 95% seven-day block interval [0.213%, 0.389%].

depth10 → selected30: relative validation Brier improvement **0.059%**; conditional 95% seven-day block interval [0.036%, 0.082%].

Best tested 15% configuration: **depth10**. This choice was made on 2022, not on the 2024 test set.

## calendar

| Candidate | Sample | Depth | Trees | Min leaf | Features | Validation Brier | Fit minutes |
|---|---:|---:|---:|---:|---|---:|---:|
| original15 | 15% | 8 | 40 | 25 | sqrt | 0.02332733 | -- |
| sample30 | 30% | 8 | 40 | 25 | sqrt | 0.02332800 | 2.6 |
| depth10 | 15% | 10 | 40 | 25 | sqrt | 0.02331832 | 2.2 |
| trees80 | 15% | 8 | 80 | 25 | sqrt | 0.02332818 | 3.3 |
| leaf50 | 15% | 8 | 40 | 50 | sqrt | 0.02333420 | 1.4 |
| features_half | 15% | 8 | 40 | 25 | 0.5 | 0.02331674 | 1.5 |
| selected30 | 30% | 8 | 40 | 25 | 0.5 | 0.02330797 | 2.7 |

original15 → sample30: relative validation Brier improvement **-0.003%**; conditional 95% seven-day block interval [-0.070%, 0.047%].

original15 → features_half: relative validation Brier improvement **0.045%**; conditional 95% seven-day block interval [-0.089%, 0.124%].

features_half → selected30: relative validation Brier improvement **0.038%**; conditional 95% seven-day block interval [-0.092%, 0.148%].

Best tested 15% configuration: **features_half**. This choice was made on 2022, not on the 2024 test set.

## Limits

These intervals condition on fitted models and one sampling/RF seed. They do not include refitting variance. A confidence interval containing zero does not prove equivalence. The one-factor search is not exhaustive, and selecting the best candidate on 2022 can overfit that validation year. No new independent final-test claim is made.
