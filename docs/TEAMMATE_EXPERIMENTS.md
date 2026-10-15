# Teammate model experiments integrated on 15 October 2026

The original evaluated 15% RF/LR models in `outputs/steps/task2-dual-v2/models` are unchanged. The following results are supplemental; no cloud jobs were launched during integration.

| Evidence | Repository path | Verification scope |
|---|---|---|
| GBT 30% and 100%, A and B | `outputs/steps/gbt-sampling-20261014-run01/` | Raw metrics, daily Brier, counts/prevalence, recorded training source hash and model reload |
| GBT 15%, A | `teammate-summary.md` inside that result directory | Supplied rounded summary only; no model package |
| GBT 15%, B | `calendar/sample15/` inside that result directory | Metadata and per-threshold CSVs parsed from `gbt-calendar-results.txt`; no pipeline or daily errors |
| RF/LR 100%, A and B | `outputs/steps/task2-full-20261012/models/` | Metadata, training amount support, test counts/prevalence, RF daily Brier and model reload |
| Source archive hashes | Each imported run's `import_manifest.json` | Original downloads retained outside repository; no ZIP/TAR is embedded |

The original GBT source and workflow are retained under the imported run's `source/`. `jobs/train_gbt_sampling.py` uses the same fitting protocol, factoring the model helpers into `src/rainfall/boosted.py` and also writing a training-only station catalogue for future runs. Existing GBT pipeline weights and original metadata were not rewritten. Their query catalogue was copied from the original training-only catalogue; see `query_catalogue_provenance.json`.

## Model design

GBT is a binary classifier of `y30 > threshold`, with the query threshold as a numeric input. It trains one model per information setting and sampling fraction, not seven independent GBTs. The 7 training thresholds are 0, 0.2, 1, 2, 5, 10 and 20 mm. Each sampled anchor is expanded to all seven queries. The tree sequence has 40 boosting iterations, step size 0.1, subsampling 0.8, minimum leaf size 25 and seed 2026. Depth 3 or 5 is selected on 2022 mean Brier and temperature on 2023. A has recent-history features; B uses location/time features. Unlike the RF survival mixture, GBT does not guarantee non-increasing probabilities as the threshold increases.

The supplied GBT exports also score the original RF/LR at query thresholds 3, 7.5 and 15 mm. Those are supplementary 2024 diagnostics, not new training query thresholds. All equal-threshold means in the main comparison use the original seven thresholds only.

## Reproduce local summaries and query

```bash
python -m pip install -r requirements-report.txt
python scripts/analyze_teammate_results.py
python scripts/build_project_report.py
PYTHONPATH=src python scripts/verify_teammate_models.py
```

The summary script reads saved exports, does not fit models or edit pipeline files, and stops on mismatched daily counts/Brier or event prevalence. Matching counts and prevalence cannot prove row-level feature identity across independent reruns. `local_model_verification.json` records reload and fabricated-input probability checks, not new test accuracy.

```bash
export PYTHONPATH="$PWD/src"
spark-submit --master 'local[2]' jobs/predict.py \
  --model outputs/steps/gbt-sampling-20261014-run01/calendar/sample100 \
  --predictor gbt --station S50 --time '2026-10-15T15:00:00+08:00' \
  --threshold 3 --output outputs/local-gbt-query
```

A additionally needs `--clean /path/to/clean`. Full-training RF/LR use the original query interface with `--model outputs/steps/task2-full-20261012/models/calendar` (or `short_term`). GBT's finite training maximum flag is NULL because these imported binary models do not use the RF's finite-support survival distribution.

## Reproduce fitting on an existing GCP cluster

These commands incur cloud computation. They are provided for reproducibility, not run during integration. Configure `cloud/env.sh` first and reuse the clean data and prepared features described in the GCP guide.

```bash
bash cloud/10_gbt_sampling.sh gbt-a-15 short_term 0.15
bash cloud/10_gbt_sampling.sh gbt-a-30 short_term 0.30
bash cloud/10_gbt_sampling.sh gbt-a-full short_term 1.0
# Repeat with calendar, using new run names.
```

Set `RAINFALL_GBT_REFERENCE_MODELS` or `RAINFALL_GBT_DATA` to another per-mode parent root if necessary. The job checks feature metadata and reference cohort counts. Full-training RF/LR use existing `jobs/train.py --train-fraction 1.0 --eval-fraction 1.0 --depths 5,8 --trees 40` with `--data` pointing to each prepared feature root and a fresh `--output`.

## Interpretation

GBT's 100% scores are only slightly better than its reported 15% scores. The original RF has lower mean Brier than the supplied GBT runs, and the full-training RF/LR scores are close to the original 15% fits. These do not establish equivalence, statistical significance or a global optimum. The original historical baseline already used all eligible training anchors, so its unchanged 100% result is a consistency check. The teammate experiments were conducted after inspection of original 2024 results and are reported separately from that original test protocol.
