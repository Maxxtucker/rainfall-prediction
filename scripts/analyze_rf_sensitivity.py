#!/usr/bin/env python3
"""Summarise validation-only RF sampling/tuning experiments and paired uncertainty."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

MODES = ('short_term', 'calendar')
CANDIDATES = ('original15', 'sample30', 'depth10', 'trees80', 'leaf50', 'features_half', 'selected30')


def read_document(directory):
    parts = sorted(p for p in directory.glob('part-*') if p.is_file())
    if len(parts) != 1:
        raise ValueError(f'Expected one document in {directory}')
    return json.loads(parts[0].read_text())


def load_results(root):
    """Validate the completed experiment before writing derived summaries."""
    complete = read_document(root / 'completion')
    results = read_document(root / 'results')
    if complete.get('complete') is not True or complete.get('test_accessed') is not False:
        raise ValueError('Expected a complete validation-only experiment')
    if not isinstance(results, list) or not results or complete.get('candidates') != len(results):
        raise ValueError('Completion candidate count does not match results')
    seen = set()
    for result in results:
        key = (result['mode'], result['name'])
        if key in seen or key[0] not in MODES or key[1] not in CANDIDATES:
            raise ValueError(f'Duplicate or unsupported candidate: {key}')
        seen.add(key)
        fraction = .30 if key[1] in ('sample30', 'selected30') else .15
        if result['fraction'] != fraction or result['reuse'] is not (key[1] == 'original15'):
            raise ValueError(f'Incorrect sample/reuse configuration: {key}')
        counts = result['counts']
        if (any(type(counts.get(k)) is not int or counts[k] <= 0 for k in ('train15', 'train30', 'validation'))
                or counts['train15'] > counts['train30'] or result.get('test_accessed') is not False):
            raise ValueError(f'Invalid counts or test-access claim: {key}')
        metrics = result['threshold_metrics']
        if (not metrics or len({m['threshold'] for m in metrics}) != len(metrics)
                or any(not np.isfinite([m['threshold'], m['brier'], m['event_rate']]).all()
                       or m['threshold'] < 0 or not 0 <= m['brier'] <= 1
                       or not 0 <= m['event_rate'] <= 1 or m['n'] != counts['validation'] for m in metrics)
                or not np.isclose(result['validation_macro_brier'], np.mean([m['brier'] for m in metrics]), rtol=1e-10)):
            raise ValueError(f'Invalid threshold metrics or validation counts: {key}')
    results = sorted(results, key=lambda r: (MODES.index(r['mode']), CANDIDATES.index(r['name'])))
    for mode in MODES:
        candidates = [r for r in results if r['mode'] == mode]
        if not candidates:
            continue
        names = {r['name'] for r in candidates}
        if not set(CANDIDATES[:-1]).issubset(names):
            raise ValueError(f'Missing required candidates for {mode}')
        reference = candidates[0]
        for result in candidates:
            if (result['counts'] != reference['counts'] or result['seed'] != reference['seed']
                    or {m['threshold'] for m in result['threshold_metrics']} !=
                       {m['threshold'] for m in reference['threshold_metrics']}):
                raise ValueError(f'Inconsistent counts, seed or thresholds for {mode}')
        winner = min((r for r in candidates if r['fraction'] == .15), key=lambda r: r['validation_macro_brier'])
        if ('selected30' in names) != (winner['name'] != 'original15'):
            raise ValueError(f'Missing or unexpected selected30 candidate for {mode}')
    return results


def read_daily(root, mode, name):
    parts = sorted((root / mode / name / 'validation_daily').glob('part-*.csv'))
    if not parts:
        raise ValueError(f'Missing daily statistics for {mode}/{name}')
    frame = pd.concat([pd.read_csv(p) for p in parts], ignore_index=True)
    columns = ['threshold', 'n', 'sse', 'events', 'sum_probability']
    if not {'date', *columns}.issubset(frame.columns) or frame.empty:
        raise ValueError(f'Missing daily-statistic columns or rows for {mode}/{name}')
    dates = pd.to_datetime(frame['date'], format='%Y-%m-%d', errors='coerce')
    if dates.isna().any() or not (dates.dt.year == 2022).all():
        raise ValueError('Daily statistics must contain valid 2022 dates')
    if not (dates.dt.strftime('%Y-%m-%d') == frame['date']).all():
        raise ValueError('Daily dates must use YYYY-MM-DD format')
    if frame.duplicated(['threshold', 'date']).any():
        raise ValueError('Duplicate daily threshold/date records')
    values = frame[columns].apply(pd.to_numeric, errors='coerce')
    if (not np.isfinite(values.to_numpy()).all() or (values['threshold'] < 0).any()
            or (values['n'] <= 0).any() or (values['n'] % 1 != 0).any()
            or (values['events'] % 1 != 0).any()
            or (values[['sse', 'events', 'sum_probability']] < 0).any().any()
            or values[['sse', 'events', 'sum_probability']].gt(values['n'] + 1e-8, axis=0).any().any()):
        raise ValueError('Invalid daily counts, squared errors or probabilities')
    frame[columns] = values
    if not (frame.groupby('date')['threshold'].nunique() == frame['threshold'].nunique()).all():
        raise ValueError('Daily threshold coverage differs')
    return frame


def validate_daily_result(root, result):
    daily = read_daily(root, result['mode'], result['name'])
    totals = daily.groupby('threshold')[['n', 'sse', 'events']].sum()
    metrics = result['threshold_metrics']
    if set(totals.index) != {m['threshold'] for m in metrics}:
        raise ValueError('Daily thresholds do not match candidate result')
    for metric in metrics:
        total = totals.loc[metric['threshold']]
        if (total['n'] != metric['n']
                or not np.isclose(total['sse'] / total['n'], metric['brier'], rtol=1e-9, atol=1e-12)
                or not np.isclose(total['events'] / total['n'], metric['event_rate'], rtol=1e-9, atol=1e-12)):
            raise ValueError('Daily counts or scores do not match candidate result')


def paired_comparison(root, mode, reference, candidate, repetitions=2000):
    if type(repetitions) is not int or repetitions <= 0:
        raise ValueError('Bootstrap repetitions must be a positive integer')
    a, b = read_daily(root, mode, reference), read_daily(root, mode, candidate)
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
    if br <= 0:
        raise ValueError('Relative improvement requires a positive reference Brier score')
    rng = np.random.default_rng(2026)
    changes = []
    for _ in range(repetitions):
        starts = rng.integers(0, len(dates), size=(len(dates) + 6) // 7)
        indices = ((starts[:, None] + np.arange(7)) % len(dates)).ravel()[:len(dates)]
        den = n[indices].sum(axis=0)
        if (den <= 0).any():
            raise ValueError('Bootstrap replicate has no supported validation observations')
        ref = (sr[indices].sum(axis=0) / den).mean()
        other = (sc[indices].sum(axis=0) / den).mean()
        changes.append(100 * (ref - other) / ref)
    return {'mode': mode, 'reference': reference, 'candidate': candidate,
            'reference_brier': float(br), 'candidate_brier': float(bc),
            'relative_improvement_percent': float(100 * (br - bc) / br),
            'conditional_95_percent_interval': np.quantile(changes, [.025, .975]).tolist(),
            'bootstrap_repetitions': repetitions, 'calendar_block_days': 7,
            'seed': 2026, 'year': 2022}


def analyze_results(root):
    results = load_results(root)
    for result in results:
        validate_daily_result(root, result)
    rows = [{k: v for k, v in r.items() if k not in {'counts', 'threshold_metrics'}} for r in results]
    comparisons = []
    lines = ['# RF sensitivity results: 2022 validation only', '',
             'Original final models are preserved. Positive improvement means lower Brier error.', '']
    for mode in MODES:
        candidates = [r for r in results if r['mode'] == mode]
        if not candidates:
            continue
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
    pd.DataFrame(rows).to_csv(root / 'candidate_summary.csv', index=False)
    (root / 'analysis.md').write_text('\n'.join(lines) + '\n')
    (root / 'analysis.json').write_text(json.dumps({'comparisons': comparisons, 'test_accessed': False}, indent=2))
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--results', type=Path, required=True,
                    help='Downloaded experiment root; only three derived summary files are written')
    args = ap.parse_args()
    print(analyze_results(args.results))


if __name__ == '__main__':
    main()
