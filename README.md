# Singapore rainfall: exploration and probability prediction

DSA5208 group project using Singapore's official 2017–2024 five-minute rainfall records and Apache Spark. Task 1 explores seasonal, annual, daily and spatial patterns; Task 2 estimates the probability that a station will exceed a requested rainfall amount in the next 30 minutes.

**Read the [project report](report/project_report.pdf).** This is the single submission report, including the follow-up RF sampling and tuning study. Group names and student IDs are included on the report cover.

| Deliverable | Location |
|---|---|
| Report and generated LaTeX | [report/project_report.pdf](report/project_report.pdf), [report/project_report.tex](report/project_report.tex) |
| Final model A: recent rainfall | `outputs/steps/task2-dual-v2/models/short_term/` |
| Final model B: calendar risk | `outputs/steps/task2-dual-v2/models/calendar/` |
| Task 1 summaries and audits | `outputs/steps/task1-v5/` |
| Task 2 metrics and execution evidence | `outputs/steps/task2-dual-v2/` |
| RF follow-up: 2022 validation only | [results](outputs/steps/rf-sensitivity-20261010/analysis.md), [protocol](docs/RF_SENSITIVITY.md) |
| Supplementary figures | [Task 1 gallery](figures/task1-v5-report/index.html), [96-period station explorer](figures/task1-v5-report/spatial_explorer.html) |

Keep each model directory intact: prediction uses its pipeline, empirical rainfall distributions, station catalogue and metadata. The repository includes saved models and aggregate evidence; raw CSVs, full clean Parquet and large feature caches are reproduced through the cloud workflow.

## Quick start: query a saved model

Use Java 17 and Python 3.11 or 3.12. PySpark is pinned to 3.5.3. The requirements include `setuptools` for Python 3.12, where PySpark's `distutils` dependency is no longer in the standard library.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export PYTHONPATH="$PWD/src"
spark-submit --master 'local[2]' jobs/predict.py \
  --model outputs/steps/task2-dual-v2/models/calendar \
  --station S50 --time '2026-10-10T15:00:00+08:00' --threshold 1 \
  --output outputs/local-calendar-query
```

This queries B for the probability of **more than 1 mm** in the next 30 minutes. B estimates historical risk from station and calendar information. Station IDs must appear in its training catalogue; times must fall on a five-minute grid. Timestamps without an offset mean Singapore time. Add `--predictor binary_logistic` to query the saved logistic baseline. Use a fresh output path for another query.

A additionally requires recent clean observations:

```bash
spark-submit --master 'local[2]' jobs/predict.py \
  --model outputs/steps/task2-dual-v2/models/short_term \
  --clean /path/to/clean-parquet \
  --station S50 --time '2024-12-01T15:00:00+08:00' --threshold 2 \
  --output outputs/local-short-term-query
```

A requires 12 exact history endpoints from t−65 through t−10 minutes, with both publication timestamps no later than t. Missing history produces an explicit error. Queries after 2024 require observations beyond the archived study data; no live ingestion service is included. See [prediction semantics and evaluation](docs/TASK2_CALENDAR_RISK.md).

## Source and task map

| Work | Entry points |
|---|---|
| Cleaning, coverage and Task 1 | `src/rainfall/data.py`, `src/rainfall/exploration.py`; `jobs/clean.py`, `jobs/analyze.py` |
| Features, models and prediction | `src/rainfall/model.py`, `src/rainfall/probability.py`; `jobs/`, `cloud/08_task2.sh` |
| RF sampling and tuning follow-up | `cloud/09_rf_sensitivity.sh`, [RF guide](docs/RF_SENSITIVITY.md) |
| Report sources, figures and editing | [report/README.md](report/README.md), `figures/project-report/` |
| Data provenance and software checks | [data sources](docs/DATA_SOURCES.md), [validation evidence](docs/VALIDATION.md), `tests/` |

## Build the report

The checked-in summaries and figures are sufficient. Install the Python report dependencies and XeLaTeX, then run from the project root:

```bash
python -m pip install -r requirements-report.txt
bash report/build.sh
```

The build assembles the maintained sections, refreshes numerical tables from saved results, and runs XeLaTeX twice. It writes `report/project_report.tex` and `report/project_report.pdf`. Edit the sources listed in the [report guide](report/README.md), rather than the generated `.tex` file. Report compilation does not train models or require GCP.

## Regenerate summaries and inspect saved evidence

These optional commands use saved aggregate tables:

```bash
python scripts/validate_task1_results.py --results outputs/steps/task1-v5
python scripts/analyze_task2_report.py
python scripts/analyze_rf_sensitivity.py --results outputs/steps/rf-sensitivity-20261010
python scripts/redraw_report_figures.py
bash report/build.sh
```

The RF follow-up holds the 2022 validation sample fixed. Increasing training from 15% to 30% at the original settings changes mean Brier by a relative improvement of 0.012% for A and −0.003% for B. The best tested 15% configurations were depth 10 for A and a 0.5 feature-subset fraction for B. These are validation findings, not evidence of equivalence to full-data training or new final-test results. Original final models remain at the paths above.

Summary analysis does not modify model packages. To prepare downloaded RF candidates for queries, run the separate packaging step:

```bash
python scripts/prepare_rf_sensitivity_models.py \
  --results outputs/steps/rf-sensitivity-20261010 \
  --original-models outputs/steps/task2-dual-v2/models
```

## Optional: reproduce on GCP

The experiments used Dataproc 2.2.87 / Debian 12, Spark 3.5.3 on YARN, one master and two workers in `asia-southeast1-c`. Each VM was `e2-standard-4` (4 vCPUs, 16 GB RAM, 80 GB `pd-balanced` disk); Spark used 6 GB driver memory and 128 shuffle partitions. The experiment cluster has been deleted.

Follow the [complete GCP recipe](docs/GCP_GUIDE_ZH.md) to configure your project and bucket, download data, create the billed cluster, clean, analyse, prepare features, train and retrieve results. Use fresh run names. The original experiment reused `task2-dual-v1/data` and saved final models in `task2-dual-v2/models`; the execution JSON records those paths.

## Package for submission

Verify the group details in `report/project_report.template.tex`, rebuild the PDF, then run:

```bash
python scripts/build_submission.py
```

This creates `dist/rainfall-submission.zip` with the canonical report, source, saved models, figures and evidence, plus a SHA-256 manifest. Local cloud configuration, raw data and caches are excluded. The packager checks saved verification evidence; completed software/model checks and their scope are documented in [docs/VALIDATION.md](docs/VALIDATION.md).

OpenAI Codex assisted with implementation, diagnostics, cloud execution, analysis, figures, report editing and repository organisation. The report contains the AI declaration; group members must review the submitted work. Synthetic records are used only in software tests.

## Teammate GBT and full-training results

See [the integration guide](docs/TEAMMATE_EXPERIMENTS.md) for the imported 30%/100% GBT models, 100% RF/LR models, and 15% GBT summary. Original final models remain unchanged. These are supplementary experiments, including query thresholds 3, 7.5 and 15 mm.

```bash
python scripts/analyze_teammate_results.py
python scripts/build_project_report.py
```

To query an imported calendar GBT with the same station/time/threshold interface:

```bash
spark-submit --master 'local[2]' jobs/predict.py \
  --model outputs/steps/gbt-sampling-20261014-run01/calendar/sample100 \
  --predictor gbt --station S50 --time '2026-10-15T15:00:00+08:00' \
  --threshold 3 --output outputs/local-gbt-query
```

At 15%, A GBT is summary-only, while B has a supplied per-threshold text export. Neither 15% GBT pipeline was supplied.
