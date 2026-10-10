# Report editorial review

Applied skill: `research-paper-writing`. This is a coursework report, not a claim of a novel research algorithm.

## Mini-outline and paragraph roles

1. Abstract and research questions: task, missing-data challenge, information settings and principal evidence.
2. Data exploration and cleaning: observation scale, source gaps, completeness and reproducible processing.
3. Weather results: seasonal, paired-year, annual, diurnal and spatial evidence, with support limits beside each finding.
4. Predictive methods: target, available information, chronological split and three model families.
5. Evaluation: shared-anchor A/B results, within-mode baselines, calibration and operational cutoffs.
6. Discussion and conclusion: supported findings, deployment conditions, limitations and unperformed extensions.

Opening paragraphs state the question or finding; method paragraphs explain the sample and design; evidence paragraphs refer to the corresponding figure/table; limitation paragraphs bound each interpretation. Terminology is consistent: rainfall threshold q is an amount, alarm cutoff c is a probability, and an anchor is one station/issue-time sample.

## Claim–evidence map

| Claim | Evidence | Status |
|---|---|---|
| Source gaps affect interpretation | Daily raw/clean audit, 2018 August example and monthly coverage tables | Supported |
| November has largest eligible-year mean monthly amount | Saved monthly qualified table; seasonal aggregation; Figure 4 | Supported for the qualified sample, not a climate normal |
| Wet-interval frequency peaks in the afternoon | Pooled eligible-hour counts; Figure 6 | Supported descriptively, not a causal storm explanation |
| Only 2017/2022/2024 support full-year summary | Annual and monthly coverage rules; Section 3.1 | Supported under declared thresholds |
| A beats B by 29.4% mean Brier on shared anchors | Comparison metrics reconciled with paired daily squared errors; Figure 9/Table 3 | Supported for fitted pipelines, not a controlled feature ablation |
| A beats both within-mode baselines in mean Brier | Final test metrics; Table 4 | Supported; LR has higher ROC-AUC at 1 mm |
| B forest does not overall beat historical frequency | Mean Brier 0.02274 versus 0.02252 on B's population; Table 4 | Supported; no claim that complexity necessarily improves risk estimation |
| A performs well in every future year | No rolling future-year experiment | Not claimed; requires new evidence |
| Impurity importance proves causal feature effects | Correlated rain features; no ablation | Not claimed |

## Five-dimension self-review and answers

- Contribution: Does this supply a clear insight? **Pass:** missingness-aware all-month exploration and an empirical comparison of two information settings. No algorithmic novelty is claimed.
- Clarity: Can a reader understand and reproduce the method? **Pass:** notation, windows, latency, splits, feature sets, thresholds, environment, saved artifacts and commands are documented. Names/IDs remain intentionally blank.
- Experimental strength: Are gains overstated? **Pass with stated bounds:** paired scores, baselines and subgroup diagnostics support A's advantage; rare-event difficulty and B's weak results are retained.
- Evaluation completeness: What has not been tested? **Needs new experiments for broader claims:** rolling-year tests, unseen stations, block-length sensitivity and a controlled ablation. These are explicitly future work, not implied completed validation.
- Design soundness: Can information leak across time? **Pass with a data-provenance caveat:** complete exact future labels, past-only published history, chronological splits, boundary purging and train-only preprocessing. An archived as-of feed is absent, so revision leakage cannot be ruled out completely.

## Layout corrections

Added a concise abstract and a combined conclusion; removed conversational/draft instructions from the narrative; shortened baseline column headings; separated timeline annotations from history/future points; removed colliding reliability labels; wrapped the diagnostic axis label; retained consistent external vector figures, captions and page styling. The final PDF is rendered and inspected after compilation. External-image support in the editor's single-file compiler remains a tool limitation, not a report-source error.

## Sampling and RF follow-up

The new validation-only section separates fixed-configuration sample-size comparisons from one-factor tuning. It reports all 14 candidates rather than only winners, preserves the original 2024-tested models, and explicitly limits conditional block intervals to one seed and fixed fitted models. Intervals for selected settings are not search-adjusted. Small improvements support a compute/accuracy compromise but do not prove equivalence or establish a universal optimum.

## Integrated revision (10 October 2026)

The earlier narrative rewrite and the new RF evidence now share one maintained report. Editable sections feed `project_report.template.tex`; one build command produces the canonical PDF used by the submission packager. Report generators obtain the sensitivity table and numerical claims from recorded results rather than duplicating manually entered scores.

The revision distinguishes three comparisons: changing only the sample size, changing one RF setting at 15%, and increasing the sample for the selected setting. It reports the small gains in their numerical scale and does not infer unchanged PR-AUC or calibration from Brier alone. The discussion acknowledges that this follow-up occurred after the original test results were available; it is not presented as a predeclared blind study.

The December maps use a common scale, and the reliability panel includes bin counts so sparse probability bins are visible. The report keeps its AI declaration and blank group details for the authors to complete. Verification for this revision is recorded separately in `VALIDATION.md`; no new training or final-test run was performed.

## Supplementary figures restored, 10 October 2026

Ten retained figures are assembled from `report/sections/appendix.tex` into five appendices: distribution/source gap, monthly/annual summaries, daily tails/coverage sensitivity, spatial views, and predictive diagnostics. Main-text cross-references point to these sections. Captions distinguish changing station sets, unsupported periods, gauge summaries, and conditional model diagnostics. The canonical template uses TeX Gyre file-based fallbacks if Liberation fonts are unavailable. The updated PDF was compiled locally and its appendix pages rendered for layout review.
