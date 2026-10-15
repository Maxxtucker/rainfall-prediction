# Report editorial review — 15 October 2026

Part 2 is organised around the prediction question, with RF, logistic regression, GBT and historical frequency introduced together. Results proceed from the value of recent observations to model choice, fitting fraction, calibration and additional rainfall thresholds. The RF tuning study is retained in Appendix G; weather and predictive-diagnostic figures remain in their existing appendices.

## Presentation decisions

- Methods state the available features, timing convention, chronological split, fitting fractions and selection settings once. Table captions identify the evaluation population and metric definition.
- The model overview shows the training fraction explicitly. The sample-size table gives the recorded 15%/30%/100% results, leaving RF/LR 30% test cells empty. Their occurrence as reference scores inside GBT result folders does not represent new fits.
- RF/LR models, GBT models and historical frequencies answer the same probability query using different estimators. Historical frequency always uses the full training population.
- The interpretation leads with measured differences: recent-rainfall RF has the lowest mean Brier; GBT ranks 1 mm events competitively; its high-threshold mean probabilities exceed the observed rates; larger fitting fractions change the reported scores only slightly.
- Repeated statements about unchanged original models, unavailable guarantees and hypothetical claims have been removed from the narrative. Experiment coverage is recorded once in the appendix and the source guide. The chronology of the additional experiments appears once in the design section.
- The introduction, discussion and conclusion use the integrated results. Group names and IDs from main are retained, along with the AI declaration.

## Claim and evidence map

| Report claim | Saved evidence |
|---|---|
| Recent-rainfall RF improves mean Brier by 29.4% on shared 2024 examples | `report/task2/analysis_facts.json`, original comparison daily scores and metrics |
| RF has lower mean Brier than LR and GBT at both 15% and 100% | `report/task2/experiments_facts.json`, seven-threshold means |
| Historical frequency is the strongest calendar-risk baseline by mean Brier | Full-training baseline metrics, identical in substance to the initial full-data frequency estimates |
| GBT100 has higher 1 mm PR-AUC than RF15 | Per-threshold metric exports, with fractions shown in the model overview |
| Fitting-fraction score changes are small | Six model/mode rows in the sampling table; Figure `22_training_fraction` |
| GBT overpredicts average risk at large thresholds | Count-weighted saved reliability bins; `report/task2/threshold_risk.csv` and Figure `23_threshold_risk` |
| RF has lower Brier at 3, 7.5 and 15 mm than GBT100 | Shared-frame reference rescoring in the GBT100 exports |
| GBT sometimes reverses threshold order | Ten-query adjacent-pair diagnostic exports; denominator is query pairs |
| Increasing RF depth is more useful than increasing the reference sample | 2022 validation-only candidate scores and paired block intervals |

The sampling table and figure both use positive percentages for Brier improvement. Probability plots distinguish the mean across all examples from calibration within probability bins. Figures retain their evaluation year, information setting and fitting fraction in the captions.

## Reproduction

`bash report/build.sh` reconciles the saved model exports, regenerates the two experiment figures and assembles the canonical PDF. The analyzer writes derived report files; the source metrics and pipelines remain in `outputs/steps/`. The full workflow and experiment inventory are documented in [TASK2_EXPERIMENTS.md](TASK2_EXPERIMENTS.md). Checks for this revision are recorded in [VALIDATION.md](VALIDATION.md).
