#!/usr/bin/env python3
"""Render the validation-only follow-up from its saved results and paired summaries."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / 'outputs/steps/rf-sensitivity-20261010'


def read_document(directory):
    parts = sorted(directory.glob('part-*'))
    if len(parts) != 1:
        raise ValueError(f'Expected one JSON document in {directory}')
    return json.loads(parts[0].read_text())


def build_section(results=DEFAULT_RUN):
    """Return LaTeX without changing experiment outputs or fitting any models."""
    if not read_document(results / 'completion').get('complete'):
        raise ValueError('RF sensitivity experiment is incomplete')
    records = read_document(results / 'results')
    facts = json.loads((results / 'analysis.json').read_text())
    by_name = {(r['mode'], r['name']): r for r in records}
    if len(by_name) != len(records):
        raise ValueError('Duplicate RF sensitivity candidates')
    comparisons = {(r['mode'], r['reference'], r['candidate']): r for r in facts['comparisons']}
    labels = [
        ('original15', r'Reference', '15'), ('sample30', r'Reference', '30'),
        ('depth10', r'Depth 10', '15'), ('trees80', r'80 trees', '15'),
        ('leaf50', r'Minimum leaf size 50', '15'),
        ('features_half', r'Half-feature selection', '15'),
        ('selected30', r'Selected setting', '30'),
    ]
    rows = []
    for name, label, fraction in labels:
        a, b = [by_name[mode, name] for mode in ('short_term', 'calendar')]
        rows.append(f"{label} & {fraction}\\% & {a['validation_macro_brier']:.8f} & {b['validation_macro_brier']:.8f}" + r' \\')
    table = r'''\par
\begin{table}[htbp]\centering\small
\begin{tabular}{lrrr}\toprule
Configuration & Fitting sample & A mean Brier & B mean Brier\\\midrule
''' + '\n'.join(rows) + r'''
\bottomrule\end{tabular}
\caption{Mean Brier on the full 2022 validation set, averaged over seven rainfall thresholds. Lower is better. Changes at 15\% vary one setting from the reference. The selected 30\% row uses depth 10 for A and half-feature selection for B; it is not the same configuration for both modes.}
\label{tab:rfsensitivity}\end{table}\par
'''
    values = {'RF_SENSITIVITY_TABLE': table}
    for mode, prefix in [('short_term', 'A'), ('calendar', 'B')]:
        for name, key in [('original15', 'REFERENCE'), ('sample30', 'SAMPLE'), ('selected30', 'SELECTED')]:
            values[f'{prefix}_{key}_BRIER'] = f"{by_name[mode,name]['validation_macro_brier']:.8f}"
        values[f'{prefix}_TRAIN30'] = f"{by_name[mode,'sample30']['counts']['train30']:,}"
        change = comparisons[mode, 'original15', 'sample30']
        values[f'{prefix}_SAMPLE_GAIN'] = f"{change['relative_improvement_percent']:.3f}"
        values[f'{prefix}_SAMPLE_LOSS'] = f"{-change['relative_improvement_percent']:.3f}"
        for suffix, value in zip(['LOW', 'HIGH'], change['conditional_95_percent_interval']):
            values[f'{prefix}_SAMPLE_{suffix}'] = f'{value:.3f}'
    for reference, candidate, label in [('original15', 'depth10', 'DEPTH'), ('depth10', 'selected30', 'SELECTED')]:
        change = comparisons['short_term', reference, candidate]
        values[f'A_{label}_GAIN'] = f"{change['relative_improvement_percent']:.3f}"
        for suffix, value in zip(['LOW', 'HIGH'], change['conditional_95_percent_interval']):
            values[f'A_{label}_{suffix}'] = f'{value:.3f}'
    for threshold in (10, 20):
        scores = []
        for name in ('original15', 'sample30'):
            metrics = by_name['short_term', name]['threshold_metrics']
            scores.append(next(r['brier'] for r in metrics if r['threshold'] == threshold))
        values[f'A_Q{threshold}_GAIN'] = f'{100 * (1 - scores[1] / scores[0]):.3f}'
    text = (ROOT / 'report/task2/rf_sensitivity.template.tex').read_text()
    for key, value in values.items():
        text = text.replace('@@' + key + '@@', value)
    if '@@' in text:
        raise ValueError('Unfilled RF sensitivity report field')
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=DEFAULT_RUN)
    parser.add_argument('--output', type=Path, default=ROOT / 'report/task2/rf_sensitivity.tex')
    args = parser.parse_args()
    args.output.write_text(build_section(args.results.resolve()))
    print(args.output)


if __name__ == '__main__':
    main()
