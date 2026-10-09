# Task 2: two feature modes, one prediction target

Both models return strict P(Y30 > threshold). User query parameters are station,
prediction time (SGT, five-minute grid), threshold in mm.

| Mode | Features | Usage |
|---|---|---|
| A `short_term_v3` | Station/location, cyclic hour/date, last 3 observations, 15/30/60-min sums, 30-min max, 60-min wet count/dry fraction, 15-min trend | Issue at t for t..t+30, with available recent observations |
| B `calendar_risk_v2` | Station/location and cyclic hour/date only | Advance queries for future dates, based on historical regularities |

A currently uses **own-station history only**; neighbor features are not implemented.
Default latency 10 min: most recent interval ends t-10, and the 12-interval
history ends there. Both publication timestamps must be present and <=t. Missing
history never becomes zero. This conservative fixed policy can lose late records.
A does not silently fall back to B; insufficient history produces an explicit error.
To predict 2026 with A, supply current clean observation Parquet using `--clean`;
the existing 2017–2024 files cannot provide 2026 history. B needs no observations.
Neither mode uses numeric year to extrapolate climate change.

## Independent stages on an existing Dataproc cluster

```bash
bash cloud/08_task2.sh features task2-dual-new
bash cloud/08_task2.sh train-calendar task2-dual-new --train-fraction 0.15
bash cloud/08_task2.sh train-short-term task2-dual-new --train-fraction 0.15
bash cloud/08_task2.sh compare task2-dual-new
bash cloud/08_task2.sh predict-calendar task2-dual-new \
  --station S77 --time 2026-12-01T15:00:00+08:00 --threshold 5
bash cloud/08_task2.sh predict-short-term task2-dual-new \
  --station S77 --time 2024-12-01T15:00:00+08:00 --threshold 5
```

`features` reads existing cleaned data, writes separate `data/calendar` and
`data/short_term` features, audits and metadata. Both need six exact future records
at t+5,...,t+30 for the training label. B has no history requirement. For one mode
only, pass `--mode calendar` or `--mode short_term` to the feature job. Features,
models and comparison outputs refuse existing destination directories.

Each training stage saves its own RF distribution model, binary LogisticRegression
baseline (threshold feature), and smoothed station/month/hour climatology baseline.
`train` aliases `train-calendar`; `predict` aliases `predict-calendar`. To query the
binary model, append `--predictor binary_logistic` to either prediction command.
Use the independent feature stages above to avoid repeating cleaning and Task 1.

## Training and evaluation

2017–2021 train, 2022 select parameters, 2023 RF temperature calibration, 2024 final
test. Target windows reaching the next split boundary are excluded. Threshold
expansion and deterministic sampling keep all thresholds for an anchor together.
Default train fraction .15, evaluation fraction 1. Choose the training sample size
after reviewing audits, especially rare rain-amount classes.

Both modes use the same RF architecture/candidate settings. They train on their
respective eligible samples; B can use more anchors. `compare` reads both trained
models and evaluates RF probabilities on the **same intersection of 2024 anchors**.
It verifies matching threshold/split/sampling settings and labels, reports common
sample counts and short-term coverage, per-threshold Brier/log loss/PR-AUC/ROC-AUC,
reliability bins and paired daily error sums (for time-block uncertainty analysis).
Individual model evaluation also reports station/month subgroups, feature
importance and threshold-order violations for RF, binary and climatology.
Do not compare different-population individual metrics as if they were paired.

RF estimates amount-bin probabilities for {0}, (0,1], (1,2], (2,5], (5,10],
(10,20], (20,infinity), then combines them with training-only within-bin empirical
survival. This guarantees threshold monotonicity, but truncates the tail at the
largest training amount and approximates within-bin conditional distributions.
Binary LR uses one-hot station, standardized numeric features and threshold;
regularization .01/.1 selected on validation macro Brier. Its probabilities are
uncalibrated and threshold monotonicity is not constrained. Do not claim arbitrary
unseen-threshold accuracy without evaluating it separately.

Five-minute anchors share target intervals and are correlated, not independent
storms. Grey/missing data are never filled as dry weather. B uses a frozen latest
training station location catalogue; unknown stations are rejected. A uses
metadata from its newest available history observation. Station relocation,
nonrandom missingness and distribution shifts remain limitations.

## Verification

```bash
PYTHONPATH=src python3 -m unittest tests.test_spark_semantics tests.test_probability tests.test_calendar_risk
```

These tests use fabricated fixtures for semantic verification, not experiment
results. These fixture tests do not supply the reported real-data results.

## Completed real-data run (9 October 2026)

Models: `outputs/steps/task2-dual-v2/models/short_term` (A) and
`outputs/steps/task2-dual-v2/models/calendar` (B). Both use depth 8, 40 trees and
temperature 1.0. A has 2,802,737 sampled training anchors and 5,729,508 test anchors;
B has 4,115,222 sampled training anchors and 6,374,476 test anchors. Validation,
calibration and test use all eligible anchors. Feature preparation was reused from
`project/steps/task2-dual-v1/data`; models are under `project/steps/task2-dual-v2/models`
in the project bucket. See the downloaded `RESULTS.md` for scores and comparison.

With Spark 3.5.3 and Java available, run from the project root:

```bash
PYTHONPATH=src python3 jobs/predict.py \
  --model outputs/steps/task2-dual-v2/models/calendar \
  --station S50 --time 2026-10-09T21:00:00+08:00 --threshold 1 \
  --output outputs/task2-calendar-query
PYTHONPATH=src python3 scripts/verify_task2_models.py \
  --results outputs/steps/task2-dual-v2
python3 scripts/summarize_task2.py --results outputs/steps/task2-dual-v2
```

The verifier reloads both RF and binary pipelines and reconciles RF predictions
against the small real cloud audit examples. ROC and PR AUC reuse the same Spark
sorted score counts; equivalence to separate Spark evaluators is tested.
Download completed outputs into a fresh local directory: Spark overwrites metadata
with a new part filename, so merging partial and final downloads can retain stale
part files. Partial model downloads were removed during submission cleanup; use `models`
for prediction and submission.

AI assistance: OpenAI Codex assisted with feature/model implementation, tests,
training orchestration, evaluation summaries and documentation. Real results use
the supplied historical data; fabricated fixtures are limited to software tests.
