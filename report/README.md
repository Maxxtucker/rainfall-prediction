# Combined coursework report

The latest editorial revision is [revised/rainfall_report_revised.pdf](revised/rainfall_report_revised.pdf). Its [source and build instructions](revised/README.md) are self-contained; run `bash report/revised/build.sh` from the project root. It uses the existing recorded experiments and retains the AI declaration and blank group-member fields.

The workflow below reproduces the original report. Its numerical templates and packaging command have not been migrated to the revised document.

`project_report.pdf` combines the preserved Task 1 analysis with Task 2 model evaluation. `project_report.tex` is the generated English LaTeX source. Fill in group names and student IDs and review the interpretation before submission.

From the project root:

```bash
python3 -m pip install -r requirements-report.txt
MPLCONFIGDIR=/tmp/rainfall-matplotlib python3 scripts/analyze_task2_report.py
python3 scripts/build_project_report.py
```

Compile `report/project_report.tex` with a LaTeX engine (XeLaTeX or Tectonic), keeping the project directory structure so the figures resolve. Run XeLaTeX twice for references. Task 2 wording is maintained in `report/task2/section_template.tex`; numeric tables are populated from saved evaluation outputs. The complete narrative/layout is maintained in `project_report.template.tex`. The superseded standalone Task 1 PDF was removed; its numerical facts and original template remain for provenance.

Task 2 evidence: `report/task2/analysis_facts.json`, `figures/task2-report/`, and `outputs/steps/task2-dual-v2/`. Analysis uses saved predictions/metrics and does not retrain models or create cloud resources.
