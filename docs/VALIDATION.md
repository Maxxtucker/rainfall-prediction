# Validation record — 9 October 2026

This file describes completed checks, replacing early setup notes that said real experiments were pending.

| Check | Evidence | Result |
|---|---|---|
| Task 1 real Spark analysis | Job `b3cffaef6c1943fba53c0f4d9af7d2f5`; `outputs/steps/task1-v5/metadata`, source and environment | Completed |
| Independent Task 1 table reconciliation | `outputs/steps/task1-v5/validation.json`; 8 checks rerun after cleanup | Passed |
| Task 2 A training/evaluation | Job `f8c99d157a674a2fa3389359ee89143c`; `short_term_job.json`, final model metadata | Completed |
| Task 2 B training/evaluation | Job `96255c49674c43be919384d586f2c79d`; `calendar_job.json`, final model metadata | Completed |
| Shared-sample A/B comparison | Job `c37857a1de864edfada7af59c571d4b2`; common labels, counts and daily scores | Completed |
| Saved model reload | `local_model_verification.json`: 140 RF probabilities per mode match cloud with maximum difference 0; both binary pipelines reload | Passed |
| Existing regression suite after cleanup | `python3 -m unittest discover -s tests`: 38 tests | Passed |
| Saved metric reconciliation | `scripts/analyze_task2_report.py`: reliability counts/prevalence and daily Brier reproduce aggregate metrics | Passed |
| Active Python and Bash syntax | AST parsing; `bash -n` | Passed |
| Combined report | Tectonic compiles; rendered pages inspected; no overflowing boxes in final log | Passed |

Tests use fabricated fixtures for missingness, strict threshold semantics, future-window completeness, publication latency, split purging, Spark scoring and plotting regressions. They do not establish meteorological accuracy. Actual performance comes from real held-out 2024 observations. The local Spark 3.5.3 fixture suite was run with Java 20/Python 3.13 available on this machine; reproducible use is recommended with Java 17/Python 3.11–3.12, and the recorded Dataproc runtime remains the experiment reference.

Task 1: 48,538,713 raw rows reconcile with 48,538,625 cleaned observations from 91 station IDs; 85/96 year-months have eligible stations. Task 2: every model's final metadata marks test evaluation completed; common sample has 5,729,508 anchors. No model was retrained during report/submission cleanup. The cluster was deleted after saving results.

Limits remain explicit: no 2026 holdout, unseen-station validation, operational live feed or controlled feature ablation. Seven-day moving-block intervals condition on fixed 2024 predictions and do not include refitting uncertainty. Historical revisions cannot be completely reconstructed from update fields.

## RF sensitivity follow-up (10 October 2026)

- All 41 updated tests passed (58.515 seconds), including nested deterministic samples and RF parameter overrides.
- Dataproc job `c134bedcdc4845408364f12c6bef9576` finished with state DONE. The experiment completion checkpoint records 14 scored candidates and 2,530.3 seconds through final output writing. Dataproc status propagation took additional time.
- Both original validation scores reproduce previous model-selection records within 3e-14. The exact old 15% sample counts and validation counts are asserted at runtime.
- Every new forest (12) reloads locally with the recorded parameters, seven classes, expected feature count and original full-training empirical support counts. No 2023/2024 evaluation partition was accessed.
- Outputs and paired 2022 calendar-day summaries are under `outputs/steps/rf-sensitivity-20261010/`; the cluster was deleted after collection.

## Report integration and workflow cleanup (10 October 2026)

The records above describe the original experiments and their checks. This revision did not retrain models, query GCP, or repeat Spark model-loading tests.

- The 13 lightweight tests selected by `python -m unittest discover -s tests -p 'test_rf_sensitivity*.py' -v` passed. They cover nested samples, RF parameter overrides, summary validation, and refusal to reuse existing run output.
- Reanalysis of a temporary copy of the recorded RF results reproduced paired-comparison values within `1e-12`, without changing model files. Preparing all 12 candidate packages twice on that copy produced identical metadata hashes. The checked-in experiment outputs were left unchanged.
- Changed Python files parsed successfully; the report build and RF cloud launcher passed Bash syntax checks; `git diff --check` passed.
- The canonical report compiled with XeLaTeX to 13 pages and 10 figures, with no unresolved references or overflowing boxes. The 2022 sensitivity results are separate from the original 2024 evaluation. The December maps and reliability figure were redrawn from saved data.
- The submission packager verified archive contents, SHA-256 hashes and ZIP integrity. It includes the canonical PDF and maintained report sources alongside the saved models and evidence.

These checks concern report accuracy and workflow behaviour. They add no new predictive-performance evidence.

## Observation-to-update delay audit (14 October 2026)

`scripts/audit_publication_delay.py` read all saved clean Parquet partitions locally, projecting only the timestamps and availability flag, without cloud compute. The count reconciles to 48,538,625 observations. Delay is the later of the two update timestamps minus the aligned observation timestamp; exact quantiles use linear interpolation. All records have both update timestamps and no negative delays. For 2017--2021 only (28,256,245 records), median delay is 9.5833 minutes, P90 is 15.0833 minutes, and 68.9255% are within ten minutes. Thus ten minutes is a buffer, not a guarantee: A still explicitly checks both timestamps at each anchor. Update metadata can reflect later revisions and must not be described as measured first-publication time. Full yearly and pooled results are in `outputs/steps/task2-dual-v2/publication_delay_audit.json`. These descriptive results do not change the fitted models or their latency setting.

Reproduce after downloading the clean data:

```bash
python scripts/audit_publication_delay.py --clean /path/to/clean --output outputs/steps/task2-dual-v2/publication_delay_audit.json
```

## Teammate GBT and full-training integration (15 October 2026)

- Imported four selected GBT pipelines (A/B at 30% and 100%) and two full-training model packages (each RF plus LR), preserving original 15% models and original teammate pipeline/metadata files. Archive and source hashes are retained in import manifests.
- The GBT metadata source SHA-256 matches its supplied source snapshot. Mean metrics are recomputed over the original seven thresholds, excluding diagnostic thresholds from these means. Counts and prevalence match the original per-mode test exports; daily squared-error sums reconstruct imported GBT/reference Brier within 1e-12. Full-training empirical amount supports exactly match the original full-training supports. These aggregated checks do not independently establish row-level input identity.
- All eight selected model pipelines reload with the pinned local Spark 3.5.3 runtime and return finite normalized probabilities for fabricated feature rows. The GBT calibration output remains between zero and one. A real invocation of `jobs/predict.py --predictor gbt` using calendar/sample100 returns a valid query result at threshold 3 mm. This checks the interface, not forecast accuracy in 2026.
- The complete regression suite passes: 56 tests in 60.607 seconds. New tests detect corrupted daily Brier, differing prevalence despite equal counts, and unsafe archive paths.
- GBT 15% figures remain summary-only: no corresponding pipeline or raw metric export was supplied. They are explicitly distinguished in code-generated report tables and documentation.
- No cloud model fitting or cluster operations were performed during integration. Existing trained results are supplementary, including interior-threshold diagnostics at 3, 7.5 and 15 mm.

### Calendar 15% GBT text export

The subsequently supplied `gbt-calendar-results.txt` contains metadata and per-threshold metrics for calendar 15% GBT and reference models. `scripts/import_gbt_text.py` parses the concatenated JSON/CSV blocks, preserves the original text and source hash, and does not assign the unlabelled threshold-order blocks. Recomputed calendar 15% means match the supplied rounded summary; metadata, test counts, event prevalence and positive confusion counts are checked. No 15% pipeline or daily-error export is present. Short-term 15% remains summary-only. This supersedes the earlier statement that both 15% modes had only summary evidence.

## Part 2 report and workflow reorganisation (15 October 2026)

- `analyze_task2_experiments.py` reconciles the saved exports and writes derived facts, summaries and checks under `report/task2/`. All 18 existing summary rows preserve their original mean Brier, mean log loss, mean PR-AUC and 1 mm PR-AUC values exactly. The new 1 mm log-loss column is read from the corresponding per-threshold export.
- Six focused aggregation/artifact tests and four existing import/reconciliation tests passed. They cover exclusion of additional thresholds from the seven-threshold means, missing or duplicate metric rows, full-training historical-frequency semantics, summary-only null fields and the report-only write boundary.
- Figure `22_training_fraction` uses relative Brier improvement from each model's 15% result. Figure `23_threshold_risk` weights saved reliability bins by their sample counts; RF and GBT test counts and event rates agree within each mode. The weighted values reproduce the high-threshold probability findings in the text.
- The report retains all 20 figures present in main and adds these two panels. XeLaTeX produces 22 pages without unresolved references or overflowing boxes. The methods/results, tables, figure labels and discussion were reviewed against the saved evidence; model and sampling labels were checked independently.
- Changed Python files parse, the report build passes Bash syntax checks, and `git diff --check` passes. The build refreshes the Part 2 summaries and figures before assembling the PDF.
- Source experiment outputs and fitted model files were not modified. This revision used saved aggregate evidence; it did not run Spark, fit models, load pipelines or launch cloud jobs. The earlier model-reload and full-suite records above describe the preceding integration.
