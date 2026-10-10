#!/usr/bin/env python3
"""Generate the follow-up validation section from completed sensitivity evidence."""
import json
from pathlib import Path
from analyze_rf_sensitivity import read_document

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'outputs/steps/rf-sensitivity-20261010'


def main():
    results = read_document(RUN / 'results')
    facts = json.loads((RUN / 'analysis.json').read_text())
    labels = {'original15': 'Reference, 15\\%', 'sample30': 'Reference, 30\\%',
              'depth10': 'Depth 10, 15\\%', 'trees80': '80 trees, 15\\%',
              'leaf50': 'Min. leaf 50, 15\\%', 'features_half': 'Half features, 15\\%',
              'selected30': 'Selected setting, 30\\%'}
    rows = []
    for mode, label in [('short_term', 'A'), ('calendar', 'B')]:
        records = [r for r in results if r['mode'] == mode]
        reference = next(r for r in records if r['name'] == 'original15')['validation_macro_brier']
        for r in records:
            change = 100 * (reference - r['validation_macro_brier']) / reference
            elapsed = '--' if r['reuse'] else f"{r['fit_seconds']/60:.2f}"
            rows.append(f"{label} & {labels[r['name']]} & {r['validation_macro_brier']:.8f} & {change:+.3f} & {elapsed}" + r' \\')
        if mode == 'short_term':
            rows.append(r'\midrule')
    comparisons = []
    for item in facts['comparisons']:
        label = 'A' if item['mode'] == 'short_term' else 'B'
        if item['candidate'] not in {'sample30', 'selected30'}:
            continue
        kind = 'reference setting' if item['candidate'] == 'sample30' else 'selected setting'
        lo, hi = item['conditional_95_percent_interval']
        comparisons.append(f"For {label} at the {kind}, increasing the sample from 15\\% to 30\\% changes mean validation Brier by {item['relative_improvement_percent']:+.3f}\\% relative improvement (conditional 95\\% interval [{lo:+.3f}\\%, {hi:+.3f}\\%]).")
    winners = []
    for mode, label in [('short_term', 'A'), ('calendar', 'B')]:
        winner = min((r for r in results if r['mode'] == mode and r['fraction'] == .15), key=lambda r: r['validation_macro_brier'])
        winners.append(f"{label}: depth {winner['depth']}, {winner['trees']} trees, minimum leaf {winner['min_instances_per_node']}, feature subset {winner['feature_subset_strategy']}")
    text = r'''\clearpage
\section{Sampling and RF sensitivity on 2022 validation}
The original 15\% fitting sample was a computational choice, not an empirically established optimum. We subsequently compare 15\% and 30\% at identical RF settings, then broaden the search. The station/time hash and seed 2026 are unchanged, so the 30\% sample contains the original 15\%. Both use the same full 2022 validation anchors and training-only empirical supports; temperature is fixed at 1. No 2023 or 2024 partitions are read in this follow-up.

At 15\%, the one-factor search changes depth 8 to 10, trees 40 to 80, minimum leaf size 25 to 50, or sqrt feature selection to half the features; subsampling remains 0.8. The best 15\% setting is additionally fitted at 30\%. This extends the earlier depth-5/8 search without claiming an exhaustive grid.
\begin{table}[H]\centering\small
\caption{Mean validation Brier across seven thresholds (lower is better). Improvement is relative to each mode's original 15\% forest; positive is better. Fit time excludes validation scoring. The original models are reused, so their fit times are not remeasured.}
\begin{tabular}{llrrr}\toprule Mode & Candidate & Validation Brier & Improvement (\%) & Fit (min)\\\midrule
''' + '\n'.join(rows) + r'''
\bottomrule\end{tabular}\label{tab:rfsensitivity}\end{table}
''' + '\n\n'.join(comparisons) + '\n\n' + r'\textbf{Selected 15\% settings.} ' + '; '.join(winners) + '.\n\n' + r'''\textbf{Interpretation and limits.} These paired intervals use 2,000 circular seven-day calendar blocks, preserving stations and thresholds together. They condition on one sampling/RF seed and the fitted models, not refitting uncertainty. A small improvement supports a computational compromise for this experiment; an interval spanning zero does not prove equivalence. Selecting on 2022 can overfit that year; intervals for selected settings are not adjusted for this search. The original calibrated forests and all reported 2024 test results remain unchanged; the new models are validation-only sensitivity candidates.

\textbf{Overlapping examples.} Consecutive five-minute prediction anchors share 25 minutes of target rainfall. They remain distinct training examples within a chronological split, rather than being reduced to one example every 30 minutes. Training and evaluation are separated by year with target-boundary purging. Counts therefore describe anchors, not independent storms.
'''
    target = ROOT / 'report/task2/rf_sensitivity.tex'
    target.write_text(text)
    print(target)


if __name__ == '__main__':
    main()
