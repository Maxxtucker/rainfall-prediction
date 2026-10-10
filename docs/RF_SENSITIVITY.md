# RF sampling and hyperparameter sensitivity

This follow-up uses the saved real Task 2 feature tables, never synthetic rainfall.
The original submitted A/B models are preserved. It does not use 2023 calibration
or 2024 test outcomes to select new candidates; only 2017–2021 training and 2022
validation partitions are read.

## Predeclared comparisons

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
`result/_SUCCESS` permits resuming completed candidates without refitting.
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

```bash
# An existing billed Dataproc cluster is required.
bash cloud/09_rf_sensitivity.sh rf-sensitivity-20261010
source cloud/_env.sh
gcloud storage rsync --recursive \
  "${PROJECT_ROOT}/steps/rf-sensitivity-20261010" \
  outputs/steps/rf-sensitivity-20261010
python3 scripts/analyze_rf_sensitivity.py --results outputs/steps/rf-sensitivity-20261010
PYTHONPATH=src python3 scripts/verify_rf_sensitivity_models.py --results outputs/steps/rf-sensitivity-20261010
python3 scripts/build_rf_sensitivity_report.py
python3 scripts/build_project_report.py
```

The local analyser adds frozen training station catalogues, empirical supports and explicit validation-only metadata to every fitted RF candidate so `jobs/predict.py --model .../short_term/sample30` (with recent clean data) or `.../calendar/sample30` can query it. These directories contain no newly fitted logistic baseline and no separate probability calibration. Original main-report model paths remain unchanged.
