# Singapore rainfall: exploration and probability prediction

DSA5208 coursework using the official 2017–2024 five-minute rainfall records and Apache Spark. The final English report covers both tasks. Group names and student IDs are intentionally blank and must be completed before submission.

## Submission contents

| Item | Location |
|---|---|
| Final report and editable LaTeX | `report/project_report.pdf`, `report/project_report.tex` |
| Trained model A, recent rainfall | `outputs/steps/task2-dual-v2/models/short_term/` |
| Trained model B, calendar risk | `outputs/steps/task2-dual-v2/models/calendar/` |
| Source code | `src/`, `jobs/`, `scripts/`, `cloud/`, `tests/` |
| Task 1 real aggregates and audits | `outputs/steps/task1-v5/` |
| Task 2 evaluation and execution evidence | `outputs/steps/task2-dual-v2/` |
| Feature preparation audits (large feature cache omitted) | `outputs/steps/task2-dual-v1/data/` |
| All-month figure gallery | `figures/task1-v5-report/index.html` |
| Offline 96-period station explorer | `figures/task1-v5-report/spatial_explorer.html` |
| Task 2 figures and numeric analysis | `figures/task2-report/`, `report/task2/analysis_facts.json` |

Both model directories must be kept intact: each contains the RF pipeline, binary logistic pipeline, empirical supports, station catalogue, historical-frequency baseline, metadata and metrics. No private bucket access is needed to inspect results or run B locally. Raw annual CSVs and full cleaned/feature Parquet are not bundled; reproduce them with the downloader and Spark stages below.

The GitHub repository contains expanded project files, including the saved models and report. Generated ZIP archives, compressed source snapshots, local cloud configuration, logs and old visual-review files are excluded. Packaging commands below create archives locally when needed for Canvas.

## Environment

Real experiments used Dataproc 2.2.87 (Debian 12), Spark/PySpark 3.5.3 on YARN, one e2-standard-4 master and two e2-standard-4 workers (each 4 vCPUs, 16 GB RAM, 80 GB pd-balanced disk), in asia-southeast1-c. Training used 128 shuffle partitions, 6 GB driver memory and adaptive SQL. Actual cluster/job JSON accompanies the results. Figures were produced locally on Apple M2 / 16 GB RAM. The experiment cluster has been deleted.

For local Spark use Java 17 and Python 3.11 or 3.12 with PySpark 3.5.3. LaTeX compilation additionally requires Tectonic or XeLaTeX. Create a virtual environment from the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export PYTHONPATH="$PWD/src"
```

## Run a saved model without retraining

B estimates historical calendar risk using only station/location and cyclic date/time. This example returns strict probability of more than 1 mm in the next 30 minutes:

```bash
spark-submit --master 'local[2]' jobs/predict.py \
  --model outputs/steps/task2-dual-v2/models/calendar \
  --station S50 --time '2026-10-09T21:00:00+08:00' --threshold 1 \
  --output outputs/local-calendar-query
```

Append `--predictor binary_logistic` to query the binary baseline. Station IDs must be in the training catalogue and times must be on a five-minute grid; naive timestamps mean Asia/Singapore. The year is used to resolve the date, not as a numeric climate-trend predictor.

A predicts short-term conditional risk and additionally requires clean observations near the requested time:

```bash
spark-submit --master 'local[2]' jobs/predict.py \
  --model outputs/steps/task2-dual-v2/models/short_term \
  --clean /path/to/clean-parquet \
  --station S50 --time '2024-12-01T15:00:00+08:00' --threshold 2 \
  --output outputs/local-short-term-query
```

A requires 12 exact history endpoints from t−65 through t−10 minutes, with both publication timestamps present and no later than t. Missing history is an explicit error; there is no silent substitution of B. To query A in 2026, provide current clean observations: the archived 2017–2024 files cannot supply them. No live ingestion service is included. B's output is historical risk, not a prediction of a particular future storm.

Reload and verify both saved RF and binary models against the small real cloud examples:

```bash
python3 scripts/verify_task2_models.py --results outputs/steps/task2-dual-v2
```

## Reproduce processing and training on GCP

Authenticate `gcloud`, enable billing in your project, then copy `cloud/env.example` to `cloud/env.sh` and fill in PROJECT_ID and a globally unique BUCKET. The example matches the measured 12-vCPU cluster. Creating the cluster starts billed resources.

```bash
cp cloud/env.example cloud/env.sh
# Edit cloud/env.sh before continuing.
bash cloud/01_setup.sh
source cloud/_env.sh
python3 scripts/download_data.py --output "$PROJECT_ROOT"
bash cloud/02_create_cluster.sh
python3 scripts/build_package.py
gcloud storage cp dist/rainfall.zip "${PROJECT_ROOT}/code/rainfall.zip"
gcloud storage cp jobs/smoke_test.py "${PROJECT_ROOT}/code/jobs/smoke_test.py"
gcloud dataproc jobs submit pyspark "${PROJECT_ROOT}/code/jobs/smoke_test.py" \
  --project "$PROJECT_ID" --region "$REGION" --cluster "$CLUSTER" \
  --py-files "${PROJECT_ROOT}/code/rainfall.zip"
bash cloud/05_clean_only.sh all clean-all-v1
bash cloud/06_analyze_only.sh clean-all-v1 task1-new \
  --shuffle-partitions 128 --raw "${PROJECT_ROOT}/raw"
bash cloud/07_download_task1.sh task1-new
bash cloud/08_task2.sh features task2-new
bash cloud/08_task2.sh train-calendar task2-new --train-fraction 0.15 --eval-fraction 1
bash cloud/08_task2.sh train-short-term task2-new --train-fraction 0.15 --eval-fraction 1
bash cloud/08_task2.sh compare task2-new
# Download to a fresh local directory after all jobs finish.
gcloud storage rsync --recursive "${PROJECT_ROOT}/steps/task2-new/models" outputs/steps/task2-new/models
gcloud storage rsync --recursive "${PROJECT_ROOT}/steps/task2-new/comparison" outputs/steps/task2-new/comparison
bash cloud/99_delete_cluster.sh
```

Use fresh run names: jobs reject existing destinations. Verify outputs are safely stored before deleting a cluster. The actual submitted experiment reused feature tables from `task2-dual-v1/data` while final models live in `task2-dual-v2/models`; `run.json` and job JSON record the overrides. A re-run may need quota or permissions appropriate to the user's own project. Data provenance and manifest handling: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Model and evaluation design

The target is the sum at exactly t+5,…,t+30 minutes; all six labels must exist. A and B use different eligible training populations. Train: 2017–2021; select hyperparameters: 2022; RF temperature: 2023; final test: 2024. Labels crossing the next split boundary are purged. Fitting uses a deterministic label-independent 15% training sample; validation, calibration and test retain every eligible anchor. Seven thresholds are evaluated: 0, 0.2, 1, 2, 5, 10 and 20 mm.

RF models estimate seven amount-bin probabilities and combine them with training-only empirical within-bin survival. Binary logistic regression takes the mode's features plus rainfall threshold. A smoothed station/month/hour historical-frequency baseline provides a substantive comparator. A/B paired comparison uses 5,729,508 identical test anchors. On this sample mean Brier is 0.01613 for A and 0.02283 for B (29.4% reduction). B's forest does not overall beat historical frequency on its own test population. These are 2024 results, not guarantees for 2026 or unseen stations. See [docs/TASK2_CALENDAR_RISK.md](docs/TASK2_CALENDAR_RISK.md).

## Reproduce figures and the report locally

Saved aggregates are enough; raw data, GCP and Spark are not required for these commands:

```bash
python3 scripts/validate_task1_results.py --results outputs/steps/task1-v5
# Optional: regenerate the complete Task 1 gallery in a fresh directory.
python3 scripts/plot_task1_report.py --results outputs/steps/task1-v5 --output figures/task1-regenerated
python3 scripts/analyze_task2_report.py
python3 scripts/build_project_report.py
cd report
tectonic project_report.tex
# Or: xelatex project_report.tex twice.
```

The current Task 1 report vectors already exist in `figures/task1-v5-report/`; regeneration is optional. Keep the directory structure when compiling. `project_report.template.tex` holds the combined narrative/layout; `task2/section_template.tex` holds metric-driven Task 2 text. `build_project_report.py` refreshes Task 2 numerical tables from saved results. The built-in single-file preview may not resolve external figures; the compiled PDF is the authoritative rendered artifact.

## Verification and packaging

```bash
python3 -m unittest discover -s tests
python3 scripts/build_submission.py
```

`build_submission.py` checks required inputs, builds `dist/rainfall-submission.zip`, excludes local configuration/caches/raw data and records SHA-256 hashes for every packaged file. It includes the report, source, saved models, evidence and gallery, without regenerating cloud resources. Extraction preserves the project directory layout. Before Canvas upload, fill in the blank group names/IDs, rebuild the PDF, and rebuild the archive. Verification evidence: [docs/VALIDATION.md](docs/VALIDATION.md). Review and claim-evidence map: [docs/REPORT_REVIEW.md](docs/REPORT_REVIEW.md).

## Source map and AI declaration

- `src/rainfall/data.py`, `exploration.py`: cleaning, completeness checks, Spark features and Task 1 summaries.
- `src/rainfall/model.py`, `probability.py`: MLlib pipelines, probability semantics and evaluation.
- `jobs/`: independent clean, analyse, feature, train, compare and predict entry points; semantic smoke job.
- `scripts/`: data/boundary downloads, plotting/report builders, result validation and model verification. `plot_task1.py` and `plot_results.py` remain because current plotting helpers and regression tests import them; they are not the final report workflow.
- `assets/`: boundary geometries and source/licence sidecars.
- `tests/`: fabricated semantic fixtures only; none are reported as experimental rainfall.

OpenAI Codex assisted with implementation, diagnostics, cloud execution, figures, analysis, report editing and repository organisation. Authors must review and take responsibility for submitted work; the report contains the AI declaration. Original executed source snapshots are retained as experiment provenance even where active source has since received documentation/layout changes.
