# Project report

[project_report.pdf](project_report.pdf) is the submission report. Part 1 describes rainfall patterns; Part 2 presents the prediction task as one sequence of model design, model comparison, training-sample experiments and probability diagnostics. The appendices retain supplementary weather figures and the detailed RF validation study. The cover lists Ma Xiaoxiao (A0259173X), Ye Sifan (A0262394Y), and Chen Yuda (A0353182H).

## Build

From the project root, with XeLaTeX and either Liberation fonts (`fonts-liberation` on Debian/Ubuntu) or the TeX Gyre fallback installed:

```bash
python -m pip install -r requirements-report.txt
bash report/build.sh
```

The build first reconciles the saved Part 2 experiment exports and refreshes the model/fraction and threshold-risk figures. It then assembles the source sections and numerical tables and runs XeLaTeX twice. It produces `report/project_report.tex` and `report/project_report.pdf`. Keep the repository structure so relative figure paths resolve. To assemble only the LaTeX source from the current summaries, run `python scripts/build_project_report.py`.

## Where to edit

| Content | Maintained source |
|---|---|
| Layout, cover, group details and assembly | `project_report.template.tex` |
| Abstract and introduction | `sections/introduction.tex` |
| Data preparation and computing environment | `sections/data.tex` |
| Part 1 findings | `sections/weather.tex` |
| Part 2 methods, model comparison, sample sizes and diagnostics | `task2/section_template.tex` |
| Detailed RF validation study in the appendix | `task2/rf_sensitivity.template.tex` |
| Supplementary weather figures and captions | `sections/appendix.tex` |
| Discussion, conclusion and AI declaration | `sections/discussion.tex` |
| Model/fraction numerical tables | `../scripts/build_task2_experiments.py` |
| Other numerical substitutions and report assembly | `../scripts/build_project_report.py` |

`project_report.tex`, `task2/section.tex` and `task2/rf_sensitivity.tex` are generated outputs. Edit the templates or source sections instead. The Part 2 experiment grid is documented in [TASK2_EXPERIMENTS.md](../docs/TASK2_EXPERIMENTS.md), including model availability and the evaluation years behind each table.

## Evidence and figures

| Evidence | Location from project root |
|---|---|
| Part 1 summary tables and audits | `outputs/steps/task1-v5/`, `report/task1/report_facts.json` |
| RF/LR 15% metrics and shared A/B test comparison | `outputs/steps/task2-dual-v2/`, `report/task2/analysis_facts.json` |
| RF/LR 100% models and metrics | `outputs/steps/task2-full-20261012/` |
| RF 30% calibration/test package | `outputs/steps/rf30-evaluation-20261016/` |
| LR 30% independent fits and metrics | `outputs/steps/lr-sampling-20261015/` |
| GBT sampling experiments and threshold diagnostics | `outputs/steps/gbt-sampling-20261014-run01/` |
| RF 15%/30% validation and tuning | `outputs/steps/rf-sensitivity-20261010/` |
| Unified model/fraction summaries | `report/task2/experiments_facts.json`, `experiments_summary.csv`, `interior_threshold_comparison.csv`, `experiments_validation.json` |

Main report comparison figures live in `figures/project-report/`. The full weather gallery remains in `figures/task1-v5-report/`, and other prediction panels in `figures/task2-report/`. The report uses selected panels; the appendix and galleries preserve additional views.

To refresh the statistical summaries and figures, run from the project root:

```bash
python scripts/validate_task1_results.py --results outputs/steps/task1-v5
python scripts/analyze_task2_report.py
python scripts/analyze_rf_sensitivity.py --results outputs/steps/rf-sensitivity-20261010
python scripts/analyze_task2_experiments.py
python scripts/redraw_report_figures.py
bash report/build.sh
```

These commands read saved statistical exports. The Task 2 experiment analyser writes derived report files, while the experiment directories remain the evidence sources. `redraw_report_figures.py` creates the enhanced panels and invokes `plot_task2_experiments.py` for `22_training_fraction` and `23_threshold_risk`. To regenerate the full Part 1 gallery separately, run `python scripts/plot_task1_report.py --results outputs/steps/task1-v5 --output figures/task1-regenerated`.

The RF/LR/GBT × 15%/30%/100% comparison now contains 2024 scores in both settings. Standard RF30 weights were reused from the 2022 sensitivity study and calibrated/tested in a separate package; the other RF tuning candidates remain validation-only. LR30 was fitted separately. At 15%, GBT A has a rounded summary and B has per-threshold text metrics. These distinctions determine which comparisons and plots can be supported. The later full-training and GBT runs reuse the previously examined test year. See the experiment guide for the complete source and evidence map.

## Before submission

Verify the cover details and AI declaration, rebuild, and inspect the PDF. Run `python scripts/build_submission.py` from the project root to package this report with the code, saved models, figures and evidence. Recorded software and model checks are listed in [docs/VALIDATION.md](../docs/VALIDATION.md).
