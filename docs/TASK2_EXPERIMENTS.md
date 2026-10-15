# Task 2: models, experiments and saved evidence

Task 2 estimates the strict probability `P(next 30-minute rainfall > threshold)` for a station and issue time. All methods use the same target definition and chronological partitions: 2017–2021 for fitting, 2022 for selection, 2023 for probability calibration where applicable, and 2024 for evaluation. Labels require six exact future five-minute records and are purged at split boundaries.

## Information settings and model families

| Setting | Inputs available to the model | Directory name |
|---|---|---|
| A: short-term risk | Station/location, cyclic time features and the station's recent published rainfall | `short_term` |
| B: calendar risk | Station/location and cyclic time features | `calendar` |

A requires twelve observations ending at t−65 through t−10 minutes, each published by t. Both settings accept station, issue time and threshold through the query interface; A additionally reads a supplied clean observation table.

| Method | Probability construction | Query selector |
|---|---|---|
| Random forest (RF) | Seven rainfall-amount-bin probabilities combined with training-only within-bin survival distributions | `--predictor random_forest` (default) |
| Logistic regression (LR) | Binary exceedance model with rainfall threshold as an additional input | `--predictor binary_logistic` |
| Gradient-boosted trees (GBT) | Binary exceedance model with rainfall threshold as an additional input | `--predictor gbt` |
| Historical frequency | Station/month/hour frequencies, smoothed towards the global training frequency | Evaluation baseline; no `jobs/predict.py` selector |

LR and GBT expand each sampled anchor to seven training thresholds: 0, 0.2, 1, 2, 5, 10 and 20 mm. GBT uses 40 boosting iterations, step size 0.1, subsampling 0.8, minimum leaf size 25 and seed 2026; depth 3 or 5 is selected on 2022 and probability temperature on 2023. RF's survival construction guarantees probabilities cannot increase with the threshold; GBT has no such guarantee.

## Which experiments are available?

Fractions describe the data used to fit the classifier, after each setting's eligibility checks. The evaluation population is not sampled.

| Method and setting | 15% fitting sample | 30% fitting sample | 100% fitting sample |
|---|---|---|---|
| RF, A and B | Pipelines and 2024 metrics; additional 2022 tuning runs | Pipelines and 2022 validation statistics | Pipelines and 2024 metrics |
| LR, A and B | Pipelines and 2024 metrics | No saved experiment | Pipelines and 2024 metrics |
| GBT, A | Rounded aggregate summary | Pipeline and 2024 metrics | Pipeline and 2024 metrics |
| GBT, B | Metadata and per-threshold text export | Pipeline and 2024 metrics | Pipeline and 2024 metrics |

There are no saved 15% GBT pipelines. The A summary cannot supply per-threshold or daily comparisons; B's text export supplies per-threshold metrics but no daily errors. RF's 30% candidates belong to the validation study and have no 2024 evaluation.

Historical frequency and RF within-bin distributions use **all eligible training anchors** even when classifier fitting uses 15%. A `fraction=0.15` historical-baseline row in earlier run summaries identifies its containing run, not a 15% baseline fit.

## Find the models and their evidence

All paths below are relative to the repository root. Replace `<mode>` with `short_term` or `calendar`.

| Experiment | Artifact root | Contents |
|---|---|---|
| RF/LR 15% | `outputs/steps/task2-dual-v2/models/<mode>/` | RF `pipeline/`, LR `binary_pipeline/`, support distributions, station catalogue, historical baseline and test metrics |
| RF/LR 100% | `outputs/steps/task2-full-20261012/models/<mode>/` | Same package structure, full-sample fitting metadata and 2024 metrics |
| GBT 30% / 100% | `outputs/steps/gbt-sampling-20261014-run01/<mode>/sample30/` or `sample100/` | GBT `pipeline/`, metadata, catalogue, per-threshold metrics, reliability and daily scores |
| GBT 15%, A | `outputs/steps/gbt-sampling-20261014-run01/teammate-summary.md` | Reported rounded summary |
| GBT 15%, B | `outputs/steps/gbt-sampling-20261014-run01/calendar/sample15/` | Parsed metadata and CSVs, original text and import manifest |
| RF validation study | `outputs/steps/rf-sensitivity-20261010/<mode>/` | 15% tuning candidates, `sample30`, `selected30`, and paired daily validation statistics |

Inside each GBT experiment, `metrics/random_forest/` and `metrics/binary_logistic/` are scores from the **15% reference models** on that run's evaluation data. Their placement under `sample30` or `sample100` does not indicate a new RF/LR fit at that fraction. The 100% RF/LR fits are in `task2-full-20261012`.

The initial RF/LR experiment includes an explicit shared-sample A/B comparison in `task2-dual-v2/comparison/`. Other method summaries use their own setting's eligible 2024 population. The export checks reconcile cohort counts, event prevalence and available daily errors; row-level feature identity across separate runs is not established by those aggregate checks.

The saved GBT source and execution workflow are under the run's `source/`. Archive hashes are retained in `import_manifest.json`; `query_catalogue_provenance.json` records the training-only catalogue used for querying the received packages. The 100% RF/LR and GBT runs followed inspection of the initial 2024 results, so their scores are subsequent evaluations on that same year, not a new independent holdout.

## Query a saved model

Install the [local environment](../README.md#quick-start-query-a-saved-model) first. Keep each complete model package together.

```bash
export PYTHONPATH="$PWD/src"
spark-submit --master 'local[2]' jobs/predict.py \
  --model outputs/steps/task2-full-20261012/models/calendar \
  --predictor binary_logistic --station S50 \
  --time '2026-10-15T15:00:00+08:00' --threshold 1 \
  --output outputs/local-lr-full-query

spark-submit --master 'local[2]' jobs/predict.py \
  --model outputs/steps/gbt-sampling-20261014-run01/calendar/sample100 \
  --predictor gbt --station S50 --time '2026-10-15T15:00:00+08:00' \
  --threshold 3 --output outputs/local-gbt-query
```

Select `short_term` and add `--clean /path/to/clean-parquet` for A. Use five-minute issue times and a station present in the training catalogue. B's future-date output is historical calendar risk. A needs observations around the requested time, and the project does not include live ingestion.

For newly downloaded RF sensitivity results, the explicit preparation step adds their query support files:

```bash
python scripts/prepare_rf_sensitivity_models.py \
  --results outputs/steps/rf-sensitivity-20261010 \
  --original-models outputs/steps/task2-dual-v2/models
```

Then query a candidate such as `.../calendar/sample30` with `--predictor random_forest`. Its metadata identifies it as a validation candidate.

## Refresh tables and the report

Run from the project root. These commands use saved aggregates and do not fit models or require Spark:

```bash
python scripts/analyze_task2_report.py
python scripts/analyze_rf_sensitivity.py --results outputs/steps/rf-sensitivity-20261010
python scripts/analyze_task2_experiments.py
python scripts/redraw_report_figures.py
bash report/build.sh
```

`analyze_task2_report.py` derives the initial model results and shared A/B comparison. `analyze_rf_sensitivity.py` computes validation comparisons and conditional block intervals. `analyze_task2_experiments.py` reconciles the model/fraction grid and writes `experiments_facts.json`, `experiments_summary.csv`, `interior_threshold_comparison.csv` and `experiments_validation.json` under `report/task2/`. `plot_task2_experiments.py`, called by `redraw_report_figures.py`, produces the training-fraction and threshold-risk figures. `build_task2_experiments.py` supplies numerical table fields to the main report builder. Editing and figure paths are documented in [report/README.md](../report/README.md).

The main comparison averages the seven training thresholds equally. The additional query thresholds 3, 7.5 and 15 mm are separate 2024 diagnostics. Their RF/LR values come from the 15% reference models. They should not be included silently in seven-threshold means or treated as new training thresholds.

## Reproduce fitting

Use the [GCP guide](GCP_GUIDE_ZH.md) to configure a project, prepare features and create a Dataproc cluster. Fitting consumes cloud resources. Reuse the prepared per-mode feature roots and choose fresh output names.

For RF/LR, the training job fits both classifiers and the historical baseline. For example, using the recorded feature-root layout:

```bash
source cloud/_env.sh
bash cloud/08_task2.sh train-calendar task2-full-new \
  --data "${PROJECT_ROOT}/steps/task2-dual-v1/data/calendar" \
  --train-fraction 1.0 --eval-fraction 1.0 --depths 5,8 --trees 40
bash cloud/08_task2.sh train-short-term task2-full-new \
  --data "${PROJECT_ROOT}/steps/task2-dual-v1/data/short_term" \
  --train-fraction 1.0 --eval-fraction 1.0 --depths 5,8 --trees 40
```

Use `--train-fraction 0.15` with another run name for the 15% design. Replace `--data` with the feature root from your own preparation run. The controlled RF-only validation study uses [cloud/09_rf_sensitivity.sh](../cloud/09_rf_sensitivity.sh); its fixed-parameter and tuning comparisons are specified in [RF_SENSITIVITY.md](RF_SENSITIVITY.md).

For GBT, run one setting and fraction at a time:

```bash
bash cloud/10_gbt_sampling.sh gbt-a-15-new short_term 0.15
bash cloud/10_gbt_sampling.sh gbt-a-30-new short_term 0.30
bash cloud/10_gbt_sampling.sh gbt-a-full-new short_term 1.0
# Use calendar and fresh run names for B.
```

`RAINFALL_GBT_DATA` and `RAINFALL_GBT_REFERENCE_MODELS` override the default parent feature/model roots; the wrapper appends the selected mode. Each wrapper call writes one experiment directly under `steps/<run>/`, whereas the recorded multi-job export groups its outputs by mode and sample. `jobs/train_gbt_sampling.py` and `src/rainfall/boosted.py` contain the current GBT workflow and helpers; the received execution source remains in the recorded run.

## Code responsibilities

| Stage | Main files |
|---|---|
| Feature windows and chronological splits | `jobs/features.py`, `src/rainfall/data.py`, `src/rainfall/model.py` |
| RF/LR training and evaluation | `jobs/train.py`, `src/rainfall/model.py` |
| Controlled RF validation study | `jobs/rf_sensitivity.py`, `cloud/09_rf_sensitivity.sh` |
| GBT training and calibration | `jobs/train_gbt_sampling.py`, `src/rainfall/boosted.py` |
| Saved-model prediction | `jobs/predict.py` |
| Unified model/fraction summary | `scripts/analyze_task2_experiments.py` |
| Report tables and comparison figures | `scripts/build_task2_experiments.py`, `scripts/plot_task2_experiments.py` |
| Report assembly | `scripts/build_project_report.py`, `report/task2/section_template.tex` |
| Archive/text import provenance | `scripts/import_teammate_results.py`, `scripts/import_gbt_text.py` |

Recorded software and model checks are listed in [VALIDATION.md](VALIDATION.md). They describe completed checks and are separate from running the statistical summary commands above.
