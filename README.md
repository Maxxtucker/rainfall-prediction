# Singapore rainfall: exploration and probability prediction

DSA5208 group project analysing Singapore rainfall observations from 2017–2024 with Apache Spark. We explore observed rainfall patterns and predict the probability that rainfall at a requested station will **strictly exceed q mm over the next 30 minutes**.

**Start with the [project report](report/project_report.pdf).** It brings together the data audit, rainfall analysis, model comparisons and supplementary evidence.

## What the project does

**Task 1 — Describe rainfall.** Clean five-minute observations, audit missing periods, and compare seasonal, annual, daily and spatial patterns. Coverage filters determine which station-periods enter each summary. Missing readings are not replaced with zero rainfall.

**Task 2 — Predict exceedance probabilities.** Compare random forest (RF), logistic regression (LR), gradient-boosted trees (GBT) and a historical-frequency baseline under two information settings:

| Setting | Available information | Intended use |
|---|---|---|
| A: short-term | Station/location, calendar features and recent rainfall | Near-term risk when recent observations are available |
| B: calendar | Station/location and calendar features | Historical risk at a requested time, including future dates |

A is the main forecasting setting. B provides a baseline and a calendar-based risk estimate when recent rain is unavailable. Each setting uses a pooled model across stations, with station ID included as a feature.

A label is the sum of six exact future five-minute observations, at t+5 through t+30. RF predicts seven rainfall-amount classes and combines their probabilities with training-derived within-class rainfall distributions. LR and GBT predict binary exceedance with q as an additional input. See [prediction semantics](docs/TASK2_CALENDAR_RISK.md) and the report for the full definitions.

## Experimental design and results

| Period | Role |
|---|---|
| 2017–2021 | Fit models; estimate historical frequencies and RF within-bin distributions |
| 2022 | Select model settings and alarm cutoffs |
| 2023 | Select RF/GBT probability temperature; LR uses no temperature calibration |
| 2024 | Evaluate probabilities and decisions |

Target windows reaching the next split boundary are excluded. Classifier fitting uses nested deterministic 15%, 30% and 100% samples of eligible training anchors (seed 2026). Validation and test populations are not sampled. Historical frequencies and RF within-bin distributions always use the full eligible training population.

The comparison contains **RF/LR/GBT × 15%/30%/100% in both settings**, evaluated on 2024. Each setting has its own eligible population: 5,729,508 test anchors for A and 6,374,476 for B. Mean Brier gives equal weight to seven thresholds: 0, 0.2, 1, 2, 5, 10 and 20 mm; lower is better.

| Setting | Classifier | 15% mean Brier | 30% mean Brier | 100% mean Brier |
|---|---|---:|---:|---:|
| A | RF | 0.01613051 | 0.01613151 | 0.01613638 |
| A | LR | 0.01944150 | 0.01943988 | 0.01944300 |
| A | GBT | 0.01622929* | 0.01623889 | 0.01622724 |
| B | RF | 0.02274285 | 0.02274079 | 0.02275362 |
| B | LR | 0.02301006 | 0.02301067 | 0.02301076 |
| B | GBT | 0.02290321 | 0.02290187 | 0.02288430 |

RF has the lowest mean Brier among the three classifiers at each fraction in both settings. Increasing the fitting sample changes these scores only slightly. In B, historical frequency has lower mean Brier (0.02252051) than all three classifiers. The report also compares ranking, calibration and rare-event performance; mean Brier alone does not describe every aspect of prediction.

*The 15% A GBT result is a received rounded aggregate summary. The 15% B GBT result has per-threshold text exports. Neither 15% GBT pipeline was supplied; the other classifier cells have saved pipelines and metric exports. Later experiments reused 2024 after initial results were available. The [experiment guide](docs/TASK2_EXPERIMENTS.md) records these evidence sources and execution batches.*

## Find the deliverables

| Content | Location |
|---|---|
| Submission report | [PDF](report/project_report.pdf), [LaTeX](report/project_report.tex), [editing/build guide](report/README.md) |
| Task 1 summaries and audits | `outputs/steps/task1-v5/` |
| RF/LR 15% packages | `outputs/steps/task2-dual-v2/models/<mode>/` |
| RF/LR 100% packages | `outputs/steps/task2-full-20261012/models/<mode>/` |
| RF 30% calibrated/tested packages | `outputs/steps/rf30-evaluation-20261016/<mode>/` |
| LR 30% independent fits | `outputs/steps/lr-sampling-20261015/<mode>/` |
| GBT 30% / 100% packages | `outputs/steps/gbt-sampling-20261014-run01/<mode>/sample30/` and `sample100/` |
| Complete experiment table and checks | [scores](report/task2/experiments_summary.csv), [validation](report/task2/experiments_validation.json) |
| RF one-factor tuning on 2022 | [analysis](outputs/steps/rf-sensitivity-20261010/analysis.md), [protocol](docs/RF_SENSITIVITY.md) |
| Supplementary rainfall views | [gallery](figures/task1-v5-report/index.html), [station explorer](figures/task1-v5-report/spatial_explorer.html) |

Replace `<mode>` with `short_term` (A) or `calendar` (B). Keep each model package intact: its metadata, pipeline and station catalogue are needed for prediction; RF also needs empirical support distributions.

RF30 reuses the standard depth-8, 40-tree weights from the earlier sensitivity study, followed by separate 2023 calibration and 2024 evaluation. Its tuned `selected30` candidates remain validation-only. LR30 was newly fitted in an LR-only run. RF/LR columns inside GBT exports are rescored **15% reference models**, not additional fits at the GBT fraction.

## Quick start: query a saved model

Use Java 17 and Python 3.11 or 3.12. PySpark is pinned to 3.5.3; the requirements include Python 3.12 compatibility support.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export PYTHONPATH="$PWD/src"
spark-submit --master 'local[2]' jobs/predict.py \
  --model outputs/steps/task2-full-20261012/models/calendar \
  --predictor random_forest --station S50 \
  --time '2026-10-16T15:00:00+08:00' --threshold 1 \
  --output outputs/local-rf-calendar-query
```

This asks B for the probability of more than 1 mm over the following 30 minutes. Use `--predictor binary_logistic` with the same package for LR. To use GBT, change the model path to `outputs/steps/gbt-sampling-20261014-run01/calendar/sample100` and the selector to `--predictor gbt`.

A additionally requires clean observations near the requested time:

```bash
spark-submit --master 'local[2]' jobs/predict.py \
  --model outputs/steps/rf30-evaluation-20261016/short_term \
  --predictor random_forest --clean /path/to/clean-parquet \
  --station S50 --time '2024-12-01T15:00:00+08:00' --threshold 2 \
  --output outputs/local-rf-short-term-query
```

A needs 12 exact history endpoints from t−65 through t−10 minutes, with both recorded update timestamps no later than t. Missing or unavailable history rejects the query. B requires a station in its training catalogue. Issue times must lie on a five-minute grid; times without an offset mean Singapore time. Output is a Spark JSON directory; choose a fresh path because the prediction job overwrites its output directory.

The repository contains saved models and aggregate results. Raw CSVs, full clean Parquet and feature caches are excluded. A queries beyond the archive require additional observations; no live ingestion service is included.

## Code map

| Stage | Entry points |
|---|---|
| Cleaning and rainfall analysis | `src/rainfall/data.py`, `src/rainfall/exploration.py`, `jobs/clean.py`, `jobs/analyze.py` |
| Feature windows | `jobs/features.py`, `src/rainfall/data.py` |
| RF/LR fitting and evaluation | `jobs/train.py`, `src/rainfall/model.py`, `src/rainfall/probability.py` |
| GBT fitting | `jobs/train_gbt_sampling.py`, `src/rainfall/boosted.py` |
| LR30 fitting / RF30 evaluation | `jobs/train_lr_sampling.py`, `jobs/evaluate_rf_sampling.py` |
| Saved-model queries | `jobs/predict.py` |
| Result reconciliation | `scripts/analyze_task2_experiments.py` |
| Report assembly and figures | `scripts/build_project_report.py`, `scripts/build_task2_experiments.py`, `scripts/plot_task2_experiments.py` |

## Rebuild the report and inspect evidence

With XeLaTeX installed, run from the repository root:

```bash
python -m pip install -r requirements-report.txt
bash report/build.sh
```

This reconciles saved experiment results, regenerates comparison figures and tables, assembles `report/project_report.tex`, and compiles `report/project_report.pdf`. It requires neither Spark nor GCP. Edit the maintained templates/sections listed in the [report guide](report/README.md) so later builds retain the changes.

For just the experiment reconciliation and its focused software checks:

```bash
python scripts/analyze_task2_experiments.py
python -m unittest discover -s tests -p 'test_task2_experiments.py'
```

See [data sources](docs/DATA_SOURCES.md) for provenance and [validation evidence](docs/VALIDATION.md) for completed checks and their scope.

## Reproduce training on GCP

Follow the [GCP setup guide](docs/GCP_GUIDE_ZH.md) and [experiment commands](docs/TASK2_EXPERIMENTS.md#reproduce-fitting). The recorded environment used Dataproc 2.2.87 / Debian 12, Spark 3.5.3, one master and two `e2-standard-4` workers in `asia-southeast1-c`. Training and evaluation wrappers are under `cloud/08_task2.sh` through `cloud/12_evaluate_rf_sampling.sh`. Use fresh output names. The recorded experiment clusters have been removed; cloud reproduction requires your own configuration and resources.

## Package the submission

After rebuilding and reviewing the report:

```bash
python scripts/build_submission.py
```

The command creates `dist/rainfall-submission.zip` with source, report, models, figures, evidence and a SHA-256 manifest. It excludes raw data, feature caches and local cloud configuration. Generated archives are not tracked in Git.

Group: Ma Xiaoxiao (A0259173X), Ye Sifan (A0262394Y), Chen Yuda (A0353182H). OpenAI Codex assisted with implementation, cloud execution, analysis and report preparation; the report includes the AI declaration. Synthetic records are used only in software tests.
