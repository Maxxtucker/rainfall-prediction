# RF sampling and hyperparameter sensitivity

This follow-up uses the saved real Task 2 feature tables, never synthetic rainfall.
The original submitted A/B models are preserved. It does not use 2023 calibration
or 2024 test outcomes to select new candidates; only 2017–2021 training and 2022
validation partitions are read.

## Comparison design

For each mode (A short_term and B calendar), score the original 15% forest and
fit a 30% forest with exactly the original configuration: 40 trees, depth 8,
minimum 25 observations per leaf, sqrt feature subsets, subsampling 0.8, seed 2026.
The deterministic station/time hash makes the 15% sample a subset of the 30%
sample. Original training-only empirical bin supports stay fixed; temperature is
1 for all validation comparisons. Full validation samples remain identical.

At 15%, vary one parameter at a time from the reference configuration:

| Candidate | Changed setting |
|---|---|
| depth10 | maximum depth 10 |
| trees80 | 80 trees |
| leaf50 | minimum 50 observations per leaf |
| features_half | feature subset fraction 0.5 |

Select the lowest equal-threshold mean validation Brier across the five 15%
configurations. If that configuration differs from the original, additionally fit
its matched 30% version. This is a bounded one-factor search, not an exhaustive
Cartesian grid. Earlier depth-5 experiments remain historical evidence; this run
adds new configurations rather than rerunning all previous fits.

Every fitted candidate pipeline, per-threshold/per-day validation squared-error
sum/count, sample counts, seed and timing is checkpointed to a new run root.
The runner requires an explicit, unused run name and refuses existing outputs,
including incomplete and legacy runs. There is no automatic checkpoint resume:
`result/_SUCCESS` alone cannot establish that source, data and model inputs match.
After an interrupted run or upload, keep its files and choose a new run name.
The cloud wrapper checks access and absence before uploading and preserves source
under the sibling `steps/<run>-source/` prefix, using create-only uploads; results
remain under `steps/<run>/<mode>/`. Both prefixes must be unused.
The reference forest is loaded from the existing saved model, not retrained.

## Interpretation

The primary controlled comparison is 15% versus 30% at fixed original parameters.
The matched selected-configuration comparison separates sampling from tuning.
Use paired calendar-day block resampling to quantify uncertainty, retaining all
stations and thresholds together. The intervals condition on fitted models and
one seed; they do not measure refitting variance or prove equivalence. An absent
or small improvement supports 15% as a compute/accuracy compromise for this
experiment, not a universal optimum. Intervals for selected configurations are not adjusted for the search. Validation-based tuning can overfit 2022;
newly selected candidates cannot be described as independently confirmed on the
already examined 2024 test set.

## Run and retrieve

The wrapper defaults to the recorded experiment's input prefixes,
`steps/task2-dual-v1/data` and `steps/task2-dual-v2/models`, in your configured
bucket. Both inputs and an existing Dataproc cluster must be available; choosing
a new output name does not recreate them.

```bash
# An existing billed Dataproc cluster is required.
bash cloud/09_rf_sensitivity.sh rf-sensitivity-new
source cloud/_env.sh
gcloud storage rsync --recursive \
  "${PROJECT_ROOT}/steps/rf-sensitivity-new" \
  outputs/steps/rf-sensitivity-new
python3 scripts/analyze_rf_sensitivity.py --results outputs/steps/rf-sensitivity-new
# Optional: make new downloaded forests queryable with jobs/predict.py.
python3 scripts/prepare_rf_sensitivity_models.py \
  --results outputs/steps/rf-sensitivity-new \
  --original-models outputs/steps/task2-dual-v2/models
PYTHONPATH=src python3 scripts/verify_rf_sensitivity_models.py --results outputs/steps/rf-sensitivity-new
```

For a fresh project built with the [GCP recipe](GCP_GUIDE_ZH.md), run the follow-up
before deleting the cluster and point it at the matching `task2-new` inputs:

```bash
source cloud/_env.sh
RAINFALL_SENSITIVITY_DATA="${PROJECT_ROOT}/steps/task2-new/data" \
RAINFALL_SENSITIVITY_MODELS="${PROJECT_ROOT}/steps/task2-new/models" \
  bash cloud/09_rf_sensitivity.sh rf-sensitivity-task2-new
```

Then retrieve `steps/rf-sensitivity-task2-new` into a fresh local directory and
use that path for analysis and verification. If preparing its model packages,
pass `--original-models outputs/steps/task2-new/models` so supports and station
catalogues come from the corresponding original run. The comparison design above
assumes the reference forest uses the stated settings; inspect its saved metadata
before applying this fixed candidate plan to another experiment.

The analyser only writes `candidate_summary.csv`, `analysis.md` and `analysis.json`; it does not change models. The explicit preparation command adds frozen training station catalogues, empirical supports and validation-only metadata to every fitted RF candidate so `jobs/predict.py --model .../short_term/sample30` (with recent clean data) or `.../calendar/sample30` can query it. These directories contain no newly fitted logistic baseline and no separate probability calibration. Original main-report model paths remain unchanged.

## Recorded experiment and report

The completed run in `outputs/steps/rf-sensitivity-20261010/` is the evidence used by the report. At the original fixed settings, 15% to 30% changes mean 2022 validation Brier by +0.012% relative improvement for A and -0.003% for B. A deeper forest improves A modestly; the best tested 15% settings are depth 10 for A and half-feature selection for B. This supports a computation/accuracy tradeoff for the reference settings, not equivalence of sample sizes.

These experiments save Brier scores and paired daily statistics. They do not establish an effect on PR-AUC or calibration. All new candidates are RF-only, without separate probability calibration or a new independent final-test evaluation. `original15` contains validation evidence for the reused forest; query that model from `outputs/steps/task2-dual-v2/models/`, not from the sensitivity directory.

`bash report/build.sh` assembles the canonical report from the recorded run and the original 2024 evaluation. Edit `report/task2/rf_sensitivity.template.tex` for the follow-up narrative; the table and quoted comparisons are filled from saved JSON. To generate a separate section for a different run, use `python3 scripts/build_rf_sensitivity_report.py --results PATH --output /tmp/rf_sensitivity.tex` and review the new results before replacing any report evidence. The report template describes this completed comparison and expects both modes and the tested candidates.
