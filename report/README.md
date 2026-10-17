# Project report

[project_report.pdf](project_report.pdf) is the submission report. Part 1 describes rainfall patterns; Part 2 develops and compares next-30-minute exceedance-probability models. The appendices retain supplementary weather figures, RF validation experiments, and the comparison audit.

## Build the report

Run these commands from the root of this repository. Use Python 3, XeLaTeX, and either Liberation fonts (`fonts-liberation` on Debian/Ubuntu) or the Times New Roman / Arial / Courier New or Latin Modern fallbacks:

```bash
python -m pip install -r requirements-report.txt
bash report/build.sh
```

The existing build refreshes the saved experiment summaries and figures, assembles the maintained LaTeX sections, and runs XeLaTeX twice. It produces `report/project_report.tex` and `report/project_report.pdf`. Keep the repository directory structure so figure paths resolve.

For prose-only edits, assemble the source with `python scripts/build_project_report.py`, then compile `report/project_report.tex` twice with XeLaTeX from the `report/` directory. XeLaTeX needs the standard document packages listed in `project_report.template.tex`, including `titlesec` and `placeins`.

The additional comparison tables are recorded directly in the report templates from the checked saved results. They need no separate audit folders or review dependencies. If the model results change, review these recorded tables before rebuilding.

## Where to edit

| Content | Maintained source |
|---|---|
| Layout, cover, group details and assembly | `project_report.template.tex` |
| Abstract and introduction | `sections/introduction.tex` |
| Data preparation and computing environment | `sections/data.tex` |
| Part 1 findings | `sections/weather.tex` |
| Part 2 methods, model comparisons, sample sizes and diagnostics | `task2/section_template.tex` |
| Detailed RF validation study | `task2/rf_sensitivity.template.tex` |
| Supplementary figures and additional comparison evidence | `sections/appendix.tex` |
| Discussion, conclusion and AI declaration | `sections/discussion.tex` |
| Original model/fraction numerical tables | `../scripts/build_task2_experiments.py` |
| Other numerical substitutions and report assembly | `../scripts/build_project_report.py` |

`project_report.tex`, `task2/section.tex` and `task2/rf_sensitivity.tex` are generated outputs. Edit their templates or source sections, then rebuild.

The Part 2 experiment grid is documented in [TASK2_EXPERIMENTS.md](../docs/TASK2_EXPERIMENTS.md), including model availability and the evaluation years behind each table.

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
| Unified model/fraction summaries | `report/task2/experiments_facts.json`, `report/task2/experiments_summary.csv`, `report/task2/interior_threshold_comparison.csv`, `report/task2/experiments_validation.json` |

Main report comparison figures live in `figures/project-report/`. The full weather gallery remains in `figures/task1-v5-report/`, and other prediction panels in `figures/task2-report/`. The report uses selected panels; the appendices and galleries preserve additional views.

The report includes model comparisons, uncertainty intervals, an archived worked query and fixed-station seasonal summaries. The model checks preserve distinctions between evidence types: 15% A GBT has a rounded aggregate summary, whereas 15% B GBT has per-threshold text exports. Neither has a retained fitted pipeline. Standard RF30 weights were reused from the 2022 sensitivity study and calibrated/tested in a separate package; other RF tuning candidates remain validation-only. LR30 was fitted separately. Later full-training and GBT runs reused the previously examined 2024 evaluation year.

## Refresh the original statistical summaries and figures

The report uses retained summaries and figures. If intentionally regenerating the original analyses from saved exports, install the broader `requirements-report.txt` dependencies. The existing workflow remains available:

```bash
python scripts/validate_task1_results.py --results outputs/steps/task1-v5
python scripts/analyze_task2_report.py
python scripts/analyze_rf_sensitivity.py --results outputs/steps/rf-sensitivity-20261010
python scripts/analyze_task2_experiments.py
python scripts/redraw_report_figures.py
bash report/build.sh
```

These commands read recorded statistical exports. The experiment directories remain evidence sources; the analysers write derived summaries and figures. `redraw_report_figures.py` invokes `plot_task2_experiments.py` for the training-fraction and threshold-risk panels. To regenerate the full Part 1 gallery separately, run `python scripts/plot_task1_report.py --results outputs/steps/task1-v5 --output figures/task1-regenerated`. The original `report/build.sh` also remains available for its broader summary/figure-refresh workflow.
