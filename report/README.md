# Project report

[project_report.pdf](project_report.pdf) is the single report for submission. It combines the rainfall analysis, original 2024 model evaluation, and the follow-up sampling/tuning study evaluated on 2022. `project_report.tex` is generated; make edits in the maintained sources below. The cover lists Ma Xiaoxiao (A0259173X), Ye Sifan (A0262394Y), and Chen Yuda (A0353182H).

## Build

From the project root, with XeLaTeX and either Liberation fonts (`fonts-liberation` on Debian/Ubuntu) or the TeX Gyre fallback fonts installed:

```bash
python -m pip install -r requirements-report.txt
bash report/build.sh
```

`build.sh` runs `scripts/build_project_report.py`, then XeLaTeX twice to resolve references. The output is always `report/project_report.pdf`. It uses saved evidence and figure files, with no cloud access or model fitting. Keep the repository directory structure so relative figure paths resolve. To regenerate the LaTeX source alone, run `python scripts/build_project_report.py`.

## Where to edit

| Content | Maintained source |
|---|---|
| Layout, title, group details and assembly | `project_report.template.tex` |
| Abstract and introduction | `sections/introduction.tex` |
| Data preparation and computing environment | `sections/data.tex` |
| Task 1 findings | `sections/weather.tex` |
| Supplementary figures and captions | `sections/appendix.tex` |
| Task 2 methods and original evaluation | `task2/section_template.tex` |
| RF follow-up methods and findings | `task2/rf_sensitivity.template.tex` |
| Discussion, conclusion and AI declaration | `sections/discussion.tex` |
| Numerical substitutions and generated tables | `../scripts/build_project_report.py` |

The builder inserts saved numerical results into the templates. Editing `project_report.tex` directly will lose those edits at the next build. `task2/section.tex` and `task2/rf_sensitivity.tex` are also generated outputs. Historical Task 1 templates and summary facts remain for provenance; they are not a second submission report.

## Figures and evidence

Redrawn report panels live in `../figures/project-report/`; other panels retain the original figure sources. The complete Task 1 gallery remains in `../figures/task1-v5-report/`, and the original Task 2 exports remain in `../figures/task2-report/`. The report selects figures from these directories rather than reproducing every gallery view.

| Evidence | Location from project root |
|---|---|
| Task 1 summary tables and audits | `outputs/steps/task1-v5/` |
| Task 1 report facts | `report/task1/report_facts.json` |
| Original models, metrics and paired test statistics | `outputs/steps/task2-dual-v2/` |
| Derived Task 2 report facts | `report/task2/analysis_facts.json` |
| RF candidates and validation summaries | `outputs/steps/rf-sensitivity-20261010/` |

To refresh saved summaries and report figures from the project root:

```bash
python scripts/validate_task1_results.py --results outputs/steps/task1-v5
python scripts/analyze_task2_report.py
python scripts/analyze_rf_sensitivity.py --results outputs/steps/rf-sensitivity-20261010
python scripts/redraw_report_figures.py
bash report/build.sh
```

These commands analyse recorded results. The original Task 2 analyser writes to `figures/task2-report/`; `redraw_report_figures.py` separately produces the enhanced panels in `figures/project-report/`. RF model packaging is a separate operation; see [the RF guide](../docs/RF_SENSITIVITY.md). To regenerate the full Task 1 gallery separately, use `python scripts/plot_task1_report.py --results outputs/steps/task1-v5 --output figures/task1-regenerated`.

The original final-model results use a 2024 test set. The RF follow-up compares candidates on 2022 validation and does not replace those final models. Preserve that distinction when editing claims or captions; a small 15%–30% difference does not prove equivalence to full-data training.

## Before submission

Verify the group details in `project_report.template.tex`, review the AI declaration, rebuild, and inspect the PDF. Run `python scripts/build_submission.py` from the project root to package this same report with the code, models and evidence. The recorded experiment and software checks are documented in [docs/VALIDATION.md](../docs/VALIDATION.md).
