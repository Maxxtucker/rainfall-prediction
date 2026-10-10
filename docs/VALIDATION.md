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
