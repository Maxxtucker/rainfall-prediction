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

Fractions describe the data used to fit the classifier, after each setting's eligibility checks. The main comparison is the full RF/LR/GBT × 15%/30%/100% grid in both A and B. Within each setting, every cell uses the same complete eligible 2024 population and seven-threshold mean Brier. The evaluation population is not sampled. RF uses the same 40-tree, depth-8, minimum-node-size-25, sqrt-feature, 0.8-subsampling, maxBins-90 configuration at all fractions.

| Method and setting | 15% fitting sample | 30% fitting sample | 100% fitting sample |
|---|---|---|---|
| RF, A and B | Pipelines and 2024 metrics | Existing reference-configuration pipelines, 2023 calibration and 2024 metrics | Pipelines and 2024 metrics |
| LR, A and B | Pipelines and 2024 metrics | Separate LR-only pipelines and 2024 metrics | Pipelines and 2024 metrics |
| GBT, A | Rounded aggregate summary | Pipeline and 2024 metrics | Pipeline and 2024 metrics |
| GBT, B | Metadata and per-threshold text export | Pipeline and 2024 metrics | Pipeline and 2024 metrics |

There are no saved 15% GBT pipelines. The A summary cannot supply per-threshold or daily comparisons; B's text export supplies per-threshold metrics but no daily errors. The standard 30% RF now also has 2023 calibration and 2024 evaluation. Other tuning candidates remain validation-only; their scores are not inserted into the test grid.

Historical frequency and RF within-bin distributions use **all eligible training anchors** even when classifier fitting uses 15%. A `fraction=0.15` historical-baseline row in earlier run summaries identifies its containing run, not a 15% baseline fit.

## Separate training batches

Each A/B setting and each algorithm is fitted independently; these are not combined into one ensemble. The experiments share the feature-generation rules, 2017–2021 fitting years, deterministic station–time sampling (seed 2026), and full evaluation populations within each setting.

1. Initial RF/LR: 15% fitting; 2022 selection, RF temperature on 2023, 2024 test.
2. RF sensitivity: 15% versus 30% and one-factor tuning, evaluated on 2022 only.
3. Full-training RF/LR: separate 100% fits, evaluated on 2024.
4. GBT: separate 15%, 30% and 100% fits; depth selected on 2022, temperature on 2023, evaluation on 2024. The original RF/LR 15% models are only rescored as references inside these exports.
5. LR30 follow-up: separately fit A and B at 30%, reselect L2 regularisation from 0.01/0.1 using seven-threshold mean 2022 Brier, and evaluate the selected models on 2024. This does not refit RF or GBT and applies no temperature calibration to LR.

6. RF30 evaluation completion: reuse the saved standard `sample30` forest weights exactly, select temperature on 2023 using the original grid, select alarm cutoffs on 2022, and score 2024. This does not train another forest. The original 2022 sensitivity results stay intact; the new calibrated/tested package is stored separately.

Later batches reuse 2024 after earlier results were inspected; they do not create another independent holdout. Every batch is retained under its own artifact directory.

## Find the models and their evidence

All paths below are relative to the repository root. Replace `<mode>` with `short_term` or `calendar`.

| Experiment | Artifact root | Contents |
|---|---|---|
| RF/LR 15% | `outputs/steps/task2-dual-v2/models/<mode>/` | RF `pipeline/`, LR `binary_pipeline/`, support distributions, station catalogue, historical baseline and test metrics |
| RF/LR 100% | `outputs/steps/task2-full-20261012/models/<mode>/` | Same package structure, full-sample fitting metadata and 2024 metrics |
| RF 30%, calibrated/tested | `outputs/steps/rf30-evaluation-20261016/<mode>/` | Exact copies of standard `sample30` forest weights; original full-training support/catalogue; 2023 temperature selection and 2024 metrics |
| LR 30% | `outputs/steps/lr-sampling-20261015/<mode>/` | Independent `binary_pipeline/`, both regularisation candidates, objective histories, validation/test metrics, reliability and daily scores |
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

For the standard 30% RF with completed calibration and testing, query `outputs/steps/rf30-evaluation-20261016/<mode>/` using `--predictor random_forest`. The following path instead queries a validation-only tuning package.

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

`analyze_task2_report.py` derives the initial model results and shared A/B comparison. `analyze_rf_sensitivity.py` computes validation comparisons and conditional block intervals. `analyze_task2_experiments.py` rejects incomplete grids or non-2024 comparison cells, reconciles the model/fraction grid and writes `experiments_facts.json`, `experiments_summary.csv`, `interior_threshold_comparison.csv` and `experiments_validation.json` under `report/task2/`. `plot_task2_experiments.py`, called by `redraw_report_figures.py`, produces the complete training-fraction grid and matched-30% threshold-risk figures. The algorithm overview holds fitting fraction fixed at 100%; the additional-query table holds it fixed at 30%. `build_task2_experiments.py` supplies numerical table fields to the main report builder. Editing and figure paths are documented in [report/README.md](../report/README.md).

The main comparison averages the seven training thresholds equally. The additional query thresholds 3, 7.5 and 15 mm are separate 2024 diagnostics. The main interior-query table now compares RF, LR and GBT all fitted at 30%, with matching counts and event prevalences. The mean-risk plot also uses 30% for every algorithm. Legacy RF/LR 15% scores inside the GBT exports remain in the provenance facts and are not relabeled as matched 30% fits. Extra thresholds are excluded from seven-threshold means.

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

For the separate A/B LR30 follow-up (on an existing cluster), use a fresh run name:

```bash
bash cloud/11_lr_sampling.sh lr30-new
```

This fits two regularisation candidates per setting, records convergence histories, saves and reloads each selected model, and exports 2022/2024 metrics plus 2024 daily errors. It uses the original LR pipeline with `maxIter=100`; 30% refers to eligible station-time anchors before expansion to seven threshold labels.

To complete evaluation of existing standard RF30 weights, without fitting again:

```bash
bash cloud/12_evaluate_rf_sampling.sh rf30-evaluation-new
```

This reads `rf-sensitivity-20261010/<mode>/sample30/pipeline`, copies the exact pipeline bytes to a fresh package, and reuses the original training-only supports and station catalogue. It validates settings against the original reference forest before calibration/test. `scripts/verify_rf_sampling.py` compares every pipeline file hash with the original candidate and smoke-tests the copied models.

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
| RF30 calibration and test | `jobs/evaluate_rf_sampling.py`, `cloud/12_evaluate_rf_sampling.sh` |
| Separate LR30 fitting | `jobs/train_lr_sampling.py`, `cloud/11_lr_sampling.sh` |
| GBT training and calibration | `jobs/train_gbt_sampling.py`, `src/rainfall/boosted.py` |
| Saved-model prediction | `jobs/predict.py` |
| Unified model/fraction summary | `scripts/analyze_task2_experiments.py` |
| Report tables and comparison figures | `scripts/build_task2_experiments.py`, `scripts/plot_task2_experiments.py` |
| Report assembly | `scripts/build_project_report.py`, `report/task2/section_template.tex` |
| Archive/text import provenance | `scripts/import_teammate_results.py`, `scripts/import_gbt_text.py` |

Recorded software and model checks are listed in [VALIDATION.md](VALIDATION.md). They describe completed checks and are separate from running the statistical summary commands above.
