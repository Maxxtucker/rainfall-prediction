# Revised rainfall report

This standalone report rewrites the existing English report using the recorded 2017–2024 analyses. It does not contain new model training or new evaluation experiments.

## Files

- `rainfall_report_revised.pdf`: final PDF.
- `report.tex`: main document, group member fields, references and page styling.
- `sections/`: editable English report sections.
- `figures/`: the ten PDF figures used by the report.
- `scripts/`: plotting scripts for the two redrawn figures.
- `figure-data/` and `assets/`: saved summary data and boundary needed for those redraws, including boundary source/licence metadata.

Fill in group member names and student IDs in `report.tex` before submission. The original repository remains at https://github.com/Maxxtucker/rainfall-prediction and contains the source code, saved models, result tables and complete supplementary figure gallery. This report bundle does not replace those required submission materials.

## Compile

Use XeLaTeX with the Liberation Serif, Liberation Sans and Liberation Mono fonts and the LaTeX packages referenced in `report.tex` (a normal TeX Live installation with recommended/extra LaTeX and fonts provides these).

```bash
bash build.sh
```

Run the command from an extracted copy; it compiles twice to resolve figure, table and bibliography references. Existing figure PDFs are sufficient, so Python is not needed to compile the report.

## Redraw the two updated figures (optional)

Use the original project's Python plotting dependencies (`numpy`, `pandas`, `matplotlib`). From this directory:

```bash
python scripts/redraw_reliability.py \
  --input figure-data/reliability \
  --output figures/20_reliability
python scripts/redraw_december_map.py \
  --input figure-data/spatial-month \
  --boundary assets/singapore.geojson \
  --output figures/13_spatial_month_12
```

The calibration figure retains the saved shared-test statistics and adds sample counts for each probability bin. The December map uses a common 0–600 mm range across the eight December panels, covering all displayed values; it is deliberately distinct from the repository gallery's scale across all 96 year-months. Other figures retain the original saved results.

## Editorial changes

The original 18-page report was reorganised into a 12-page narrative with ten figures. Repeated callouts and overlapping caveats were removed. The text explains feature choices, the two prediction settings, different eligible sample sizes, 15% training and rare-event counts, probability versus alarm thresholds, and the limits of retrospective evaluation. AI assistance remains disclosed.

Numerical claims were checked against saved result tables and model metadata. The final PDF was compiled with resolved references and inspected for layout. No model retraining or application test run was performed for this revision.
