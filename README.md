# Singapore rainfall: exploration and probability prediction

DSA5208 group project using Singapore's official 2017–2024 five-minute rainfall records and Apache Spark. Task 1 explores seasonal, annual, daily and spatial patterns; Task 2 estimates the probability that a station will exceed a requested rainfall amount in the next 30 minutes.

**Read the [project report](report/project_report.pdf).** This is the single submission report, covering rainfall patterns, RF/LR/GBT prediction, training-sample comparisons and probability diagnostics. Group names and student IDs are included on the report cover.

| Deliverable | Location |
|---|---|
| Report and generated LaTeX | [report/project_report.pdf](report/project_report.pdf), [report/project_report.tex](report/project_report.tex) |
| RF/LR models at 15% and 100% | `outputs/steps/task2-dual-v2/models/`, `outputs/steps/task2-full-20261012/models/` |
| GBT models at 30% and 100% | `outputs/steps/gbt-sampling-20261014-run01/{short_term,calendar}/{sample30,sample100}/` |
| Task 1 summaries and audits | `outputs/steps/task1-v5/` |
| Task 2 experiment and artifact map | [models, fractions, evidence and commands](docs/TASK2_EXPERIMENTS.md) |
| RF tuning and 15%/30% validation comparison | [results](outputs/steps/rf-sensitivity-20261010/analysis.md), [protocol](docs/RF_SENSITIVITY.md) |
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
  --station S50 --time '2026-10-15T15:00:00+08:00' --threshold 1 \
  --output outputs/local-calendar-query
```

This queries B for the probability of **more than 1 mm** in the next 30 minutes. B estimates historical risk from station and calendar information. Station IDs must appear in its training catalogue; times must fall on a five-minute grid. Timestamps without an offset mean Singapore time. Add `--predictor binary_logistic` to query LR from the same package. For full-training RF/LR, use `outputs/steps/task2-full-20261012/models/calendar`. Use a fresh output path for each query.

A additionally requires recent clean observations:

```bash
spark-submit --master 'local[2]' jobs/predict.py \
  --model outputs/steps/task2-dual-v2/models/short_term \
  --clean /path/to/clean-parquet \
  --station S50 --time '2024-12-01T15:00:00+08:00' --threshold 2 \
  --output outputs/local-short-term-query
```

A requires 12 exact history endpoints from t−65 through t−10 minutes, with both publication timestamps no later than t. Missing history produces an explicit error. Queries after 2024 require observations beyond the archived study data; no live ingestion service is included. See [prediction semantics and evaluation](docs/TASK2_CALENDAR_RISK.md).

To query GBT, select its package and predictor explicitly:

```bash
spark-submit --master 'local[2]' jobs/predict.py \
  --model outputs/steps/gbt-sampling-20261014-run01/calendar/sample100 \
  --predictor gbt --station S50 --time '2026-10-15T15:00:00+08:00' \
  --threshold 3 --output outputs/local-gbt-query
```

The [Task 2 guide](docs/TASK2_EXPERIMENTS.md) maps every model and sampling fraction. RF has 2024 results at 15% and 100%, plus 2022-only tuning/sampling results at 15% and 30%; LR has 15% and 100% results. GBT has saved pipelines at 30% and 100%; its 15% evidence consists of an A summary and B per-threshold metrics. Historical frequency uses all eligible training data.

## Source and task map

| Work | Entry points |
|---|---|
| Cleaning, coverage and Task 1 | `src/rainfall/data.py`, `src/rainfall/exploration.py`; `jobs/clean.py`, `jobs/analyze.py` |
| Features and RF/LR training | `jobs/features.py`, `jobs/train.py`; `src/rainfall/model.py`, `src/rainfall/probability.py` |
| GBT training | `jobs/train_gbt_sampling.py`, `src/rainfall/boosted.py`, `cloud/10_gbt_sampling.sh` |
| Prediction and experiment workflow | `jobs/predict.py`, [Task 2 guide](docs/TASK2_EXPERIMENTS.md) |
| Report sources, figures and editing | [report/README.md](report/README.md), `figures/project-report/` |
| Data provenance and software checks | [data sources](docs/DATA_SOURCES.md), [validation evidence](docs/VALIDATION.md), `tests/` |

## Build the report

The checked-in summaries and figures are sufficient. Install the Python report dependencies and XeLaTeX, then run from the project root:

```bash
python -m pip install -r requirements-report.txt
bash report/build.sh
```

The build reconciles saved Part 2 results, refreshes its experiment figures and tables, assembles the maintained sections, and runs XeLaTeX twice. It writes `report/project_report.tex` and `report/project_report.pdf`. Edit the sources listed in the [report guide](report/README.md), rather than the generated `.tex` file. Report compilation uses the saved exports and runs without Spark or GCP.

## Regenerate summaries and inspect saved evidence

These optional commands use saved aggregate tables:

```bash
python scripts/validate_task1_results.py --results outputs/steps/task1-v5
python scripts/analyze_task2_report.py
python scripts/analyze_rf_sensitivity.py --results outputs/steps/rf-sensitivity-20261010
python scripts/analyze_task2_experiments.py
python scripts/redraw_report_figures.py
bash report/build.sh
```

These scripts read saved statistics and regenerate report inputs. The [Task 2 guide](docs/TASK2_EXPERIMENTS.md) explains which tables use 2022 validation, 2024 test results or summary-only evidence, and how to prepare newly downloaded RF candidates for queries.

## Optional: reproduce on GCP

The experiments used Dataproc 2.2.87 / Debian 12, Spark 3.5.3 on YARN, one master and two workers in `asia-southeast1-c`. Each VM was `e2-standard-4` (4 vCPUs, 16 GB RAM, 80 GB `pd-balanced` disk); Spark used 6 GB driver memory and 128 shuffle partitions. The experiment cluster has been deleted.

Follow the [complete GCP recipe](docs/GCP_GUIDE_ZH.md) for data preparation and the [Task 2 workflow](docs/TASK2_EXPERIMENTS.md#reproduce-fitting) for RF/LR, GBT and RF sensitivity runs. Use fresh run names. The original experiment reused `task2-dual-v1/data` and saved final models in `task2-dual-v2/models`; the execution JSON records those paths.

## Package for submission

Verify the group details in `report/project_report.template.tex`, rebuild the PDF, then run:

```bash
python scripts/build_submission.py
```

This creates `dist/rainfall-submission.zip` with the canonical report, source, saved models, figures and evidence, plus a SHA-256 manifest. Local cloud configuration, raw data and caches are excluded. The packager checks saved verification evidence; completed software/model checks and their scope are documented in [docs/VALIDATION.md](docs/VALIDATION.md).

OpenAI Codex assisted with implementation, diagnostics, cloud execution, analysis, figures, report editing and repository organisation. The report contains the AI declaration; group members must review the submitted work. Synthetic records are used only in software tests.
