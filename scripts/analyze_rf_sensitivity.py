#!/usr/bin/env python3
"""Summarise validation-only RF sampling/tuning experiments and paired uncertainty."""
import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd


def read_document(directory):
    parts = sorted(directory.glob('part-*'))
    if len(parts) != 1:
        raise ValueError(f'Expected one document in {directory}')
    return json.loads(parts[0].read_text())


def paired_comparison(root, mode, reference, candidate, repetitions=2000):
    def daily(name):
        parts = sorted((root / mode / name / 'validation_daily').glob('part-*.csv'))
        return pd.concat([pd.read_csv(p) for p in parts], ignore_index=True)
    a, b = daily(reference), daily(candidate)
    keys = ['threshold', 'date']
    joined = a.merge(b, on=keys, suffixes=('_ref', '_candidate'), validate='one_to_one', how='outer', indicator=True)
    if not (joined['_merge'] == 'both').all() or not (joined.n_ref == joined.n_candidate).all():
        raise ValueError('Candidates have different validation anchors')
    if not (joined.events_ref == joined.events_candidate).all():
        raise ValueError('Candidate labels differ')
    dates = pd.date_range('2022-01-01', '2022-12-31').strftime('%Y-%m-%d')
    thresholds = sorted(joined.threshold.unique())
    matrices = []
    for value in ['sse_ref', 'sse_candidate', 'n_ref']:
        matrices.append(joined.pivot(index='date', columns='threshold', values=value)
                        .reindex(index=dates, columns=thresholds).fillna(0).to_numpy())
    sr, sc, n = matrices
    br, bc = (sr.sum(axis=0) / n.sum(axis=0)).mean(), (sc.sum(axis=0) / n.sum(axis=0)).mean()
    rng = np.random.default_rng(2026)
    changes = []
    for _ in range(repetitions):
        starts = rng.integers(0, len(dates), size=(len(dates) + 6) // 7)
        indices = ((starts[:, None] + np.arange(7)) % len(dates)).ravel()[:len(dates)]
        den = n[indices].sum(axis=0)
        ref = (sr[indices].sum(axis=0) / den).mean()
        other = (sc[indices].sum(axis=0) / den).mean()
        changes.append(100 * (ref - other) / ref)
    return {'mode': mode, 'reference': reference, 'candidate': candidate,
            'reference_brier': float(br), 'candidate_brier': float(bc),
            'relative_improvement_percent': float(100 * (br - bc) / br),
            'conditional_95_percent_interval': np.quantile(changes, [.025, .975]).tolist(),
            'bootstrap_repetitions': repetitions, 'calendar_block_days': 7,
            'seed': 2026, 'year': 2022}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--results', type=Path, required=True)
    args = ap.parse_args()
    root = args.results
    complete = read_document(root / 'completion')
    if not complete.get('complete'):
        raise ValueError('Experiment is incomplete')
    results = read_document(root / 'results')
    rows = [{k: v for k, v in r.items() if k not in {'counts', 'threshold_metrics'}} for r in results]
    pd.DataFrame(rows).to_csv(root / 'candidate_summary.csv', index=False)
    comparisons = []
    lines = ['# RF sensitivity results: 2022 validation only', '',
             'Original final models are preserved. Positive improvement means lower Brier error.', '']
    for mode in ['short_term', 'calendar']:
        candidates = [r for r in results if r['mode'] == mode]
        ref = next(r for r in candidates if r['name'] == 'original15')
        lines += [f'## {mode}', '', '| Candidate | Sample | Depth | Trees | Min leaf | Features | Validation Brier | Fit minutes |',
                  '|---|---:|---:|---:|---:|---|---:|---:|']
        for r in candidates:
            fit_time = '--' if r['reuse'] else f"{r['fit_seconds']/60:.1f}"
            lines.append(f"| {r['name']} | {r['fraction']:.0%} | {r['depth']} | {r['trees']} | {r['min_instances_per_node']} | {r['feature_subset_strategy']} | {r['validation_macro_brier']:.8f} | {fit_time} |")
        pairs = [('original15', 'sample30')]
        winner = min((r for r in candidates if r['fraction'] == .15), key=lambda r: r['validation_macro_brier'])
        if winner['name'] != 'original15':
            pairs += [('original15', winner['name']), (winner['name'], 'selected30')]
        for before, after in pairs:
            comparison = paired_comparison(root, mode, before, after)
            comparisons.append(comparison)
            lo, hi = comparison['conditional_95_percent_interval']
            lines += ['', f"{before} → {after}: relative validation Brier improvement **{comparison['relative_improvement_percent']:.3f}%**; conditional 95% seven-day block interval [{lo:.3f}%, {hi:.3f}%]."]
        lines += ['', f"Best tested 15% configuration: **{winner['name']}**. This choice was made on 2022, not on the 2024 test set.", '']
    lines += ['## Limits', '', 'These intervals condition on fitted models and one sampling/RF seed. They do not include refitting variance. A confidence interval containing zero does not prove equivalence. The one-factor search is not exhaustive, and selecting the best candidate on 2022 can overfit that validation year. No new independent final-test claim is made.']
    # Make each new RF directly queryable with jobs/predict.py, without borrowing
    # an original model's calibration, binary baseline or test-evaluation claims.
    original_root = Path(__file__).resolve().parents[1] / 'outputs/steps/task2-dual-v2/models'
    for result in results:
        if result['reuse']:
            continue
        original = original_root / result['mode']
        dest = root / result['mode'] / result['name']
        if not (dest / 'pipeline').is_dir():
            raise FileNotFoundError(dest / 'pipeline')
        meta = read_document(original / 'metadata')
        for field in list(meta):
            if field.startswith('cutoffs_') or field in {'binary_baseline', 'elapsed_seconds'}:
                del meta[field]
        meta.update({'created_utc': datetime.now(timezone.utc).isoformat(),
            'depth': result['depth'], 'num_trees': result['trees'],
            'min_instances_per_node': result['min_instances_per_node'],
            'feature_subset_strategy': result['feature_subset_strategy'],
            'subsampling_rate': result['subsampling_rate'],
            'train_fraction': result['fraction'], 'temperature': 1.0,
            'test_evaluation_completed': False, 'calibration_completed': False,
            'split_years': {'train': [2017, 2021], 'validation': [2022, 2022]},
            'counts': {'train_sample': result['counts']['train30' if result['fraction'] == .30 else 'train15'],
                       'train_full': meta['counts']['train_full'], 'validation': result['counts']['validation']},
            'sensitivity_result': result, 'supported_predictors': ['random_forest'],
            'empirical_support_source': str(original / 'empirical_support'),
            'purpose': 'Validation-only RF sensitivity candidate; not a new final-tested model'})
        for directory in ['empirical_support', 'stations']:
            shutil.copytree(original / directory, dest / directory, dirs_exist_ok=True)
        (dest / 'metadata').mkdir(exist_ok=True)
        (dest / 'metadata/part-00000').write_text(json.dumps(meta))
        (dest / 'metadata/_SUCCESS').touch()
    (root / 'analysis.md').write_text('\n'.join(lines) + '\n')
    (root / 'analysis.json').write_text(json.dumps({'comparisons': comparisons, 'test_accessed': False}, indent=2))
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
