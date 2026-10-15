#!/usr/bin/env python3
"""Reconcile recorded Task 2 experiments without changing experiment outputs.

Every mean uses the original seven thresholds. Interior-threshold queries are
separate diagnostics; RF/LR scores in GBT exports still use 15% reference models.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
Q = [0.0, 0.2, 1.0, 2.0, 5.0, 10.0, 20.0]
GBT = ROOT / 'outputs/steps/gbt-sampling-20261014-run01'
FULL = ROOT / 'outputs/steps/task2-full-20261012'
ORIGINAL = ROOT / 'outputs/steps/task2-dual-v2/models'
REPORT = ROOT / 'report/task2'
REFERENCE_MODELS = ('random_forest', 'binary_logistic', 'climatology')

def document(path):
    files = sorted(path.glob('part-*'))
    if len(files) != 1:
        raise ValueError(f'Expected one document: {path}')
    return json.loads(files[0].read_text())

def csv(path):
    files = sorted(path.glob('part-*.csv'))
    if not files:
        raise ValueError(f'Missing table: {path}')
    return pd.concat([pd.read_csv(p) for p in files], ignore_index=True)

def default_metrics(path):
    frame = csv(path)
    frame = frame[frame.cutoff_kind == 'default_0.5'].copy()
    if frame.duplicated(['model', 'threshold']).any():
        raise ValueError('Duplicate metric rows')
    return frame

def primary_metrics(metrics):
    """Select one complete, unique primary threshold grid for a single model."""
    if 'model' in metrics and metrics['model'].nunique() != 1:
        raise ValueError('Expected metrics for one model')
    if metrics['threshold'].duplicated().any():
        raise ValueError('Duplicate metric thresholds')
    primary = metrics[metrics.threshold.isin(Q)]
    if set(primary.threshold) != set(Q):
        raise ValueError('Missing primary thresholds')
    return primary

def reconcile_daily(metrics, daily):
    if metrics['threshold'].duplicated().any():
        raise ValueError('Duplicate metric thresholds')
    totals = daily.groupby('threshold').agg(n=('n', 'sum'), sse=('sum_squared_error', 'sum'))
    expected = metrics.set_index('threshold')
    if set(totals.index) != set(expected.index):
        raise ValueError('Daily thresholds differ')
    totals = totals.loc[expected.index]
    if not np.array_equal(totals.n.to_numpy(), expected.n.to_numpy()):
        raise ValueError('Daily counts differ')
    if not np.allclose(totals.sse / totals.n, expected.brier, rtol=0, atol=1e-12):
        raise ValueError('Daily Brier does not reconcile')

def compare_cohort(left, right):
    left = primary_metrics(left).set_index('threshold').loc[Q]
    right = primary_metrics(right).set_index('threshold').loc[Q]
    if not np.array_equal(left.n.to_numpy(), right.n.to_numpy()):
        raise ValueError('Evaluation counts differ')
    if not np.allclose(left.prevalence, right.prevalence, rtol=0, atol=1e-14):
        raise ValueError('Event prevalence differs')

def source_path(path):
    """Use portable repository-relative paths when reporting provenance."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)

def summary_record(mode, model, fraction, metrics, evidence='raw export', *, source=None):
    primary = primary_metrics(metrics)
    if not np.isfinite(primary[['brier', 'log_loss', 'pr_auc']].to_numpy()).all():
        raise ValueError('Primary metrics must contain finite scores')
    at_one = primary.loc[primary.threshold == 1].iloc[0]
    record = dict(
        mode=mode, model=model, fraction=fraction,
        mean_brier=float(primary.brier.mean()),
        mean_log_loss=float(primary.log_loss.mean()),
        mean_pr_auc=float(primary.pr_auc.mean()),
        pr_auc_1mm=float(at_one.pr_auc), log_loss_1mm=float(at_one.log_loss),
        evidence=evidence, evaluation_year=2024,
        fit_fraction=1.0 if model == 'climatology' else fraction,
        fraction_role=('comparison group; historical frequency uses full training data'
                       if model == 'climatology' else 'model fitting fraction'),
    )
    if source is not None:
        record['source_path'] = source_path(source)
    return record

def reported15(gbt_root=GBT):
    """Preserve reported summaries without inferring missing per-threshold scores."""
    records = []
    for line in (gbt_root / 'teammate-summary.md').read_text().splitlines():
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if len(cells) == 7 and cells[0] in ('short_term', 'calendar') and cells[1] == '15%':
            records.append(dict(
                mode=cells[0], model='gbt', fraction=0.15,
                mean_brier=float(cells[2]), mean_log_loss=float(cells[3]),
                mean_pr_auc=float(cells[4]), depth=int(cells[5]), temperature=float(cells[6]),
                evidence='teammate summary only', pr_auc_1mm=None, log_loss_1mm=None,
                evaluation_year=2024, fit_fraction=0.15, fraction_role='model fitting fraction',
                source_path=source_path(gbt_root / 'teammate-summary.md'),
            ))
    if len(records) != 2 or {r['mode'] for r in records} != {'short_term', 'calendar'}:
        raise ValueError('Expected one reported 15% GBT row for each mode')
    return records


def compare_protocol(metadata, reference, description):
    for key in ('split_years', 'numeric_features', 'seed', 'eval_fraction'):
        if metadata[key] != reference[key]:
            raise ValueError(f'{description} protocol differs: {key}')


def calendar15_record(gbt_root, original_root, reported):
    """Use B's metric export when available; A remains summary-only."""
    base = gbt_root / 'calendar/sample15'
    if not base.exists():
        return reported, False
    metadata = document(base / 'metadata')
    reference_metadata = document(original_root / 'calendar/metadata')
    compare_protocol(metadata, reference_metadata, 'Calendar 15%')
    if metadata['train_fraction'] != 0.15 or not metadata['test_evaluation_completed']:
        raise ValueError('Calendar 15% fraction/completion differs')
    metrics = default_metrics(base / 'metrics/gbt')
    reference = default_metrics(original_root / 'calendar/metrics/test_metrics')
    compare_cohort(metrics, reference[reference.model == 'random_forest'])
    if not np.array_equal(
            (metrics.tp + metrics.fn).to_numpy(),
            np.rint(metrics.prevalence * metrics.n).astype('int64').to_numpy()):
        raise ValueError('Calendar 15% prevalence/confusion counts differ')
    measured = summary_record('calendar', 'gbt', 0.15, metrics,
                              evidence='per-threshold text export', source=base / 'metrics/gbt')
    if abs(measured['mean_brier'] - reported['mean_brier']) > 5e-9:
        raise ValueError('Calendar 15% summary differs')
    measured.update(depth=metadata['depth'], temperature=metadata['temperature'])
    return measured, True


def collect_facts(*, gbt_root=GBT, full_root=FULL, original_root=ORIGINAL):
    """Read and reconcile recorded evidence; return facts without writing files."""
    records = reported15(gbt_root)
    calendar_index = next(i for i, row in enumerate(records) if row['mode'] == 'calendar')
    records[calendar_index], calendar15_verified = calendar15_record(
        gbt_root, original_root, records[calendar_index])
    interior = []
    violations = []
    checks = []
    source = gbt_root / 'source/train_gbt_sampling.py'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    for mode in ('short_term', 'calendar'):
        # Original 15% models and separate full-training experiments.
        ref_meta = document(original_root / mode / 'metadata')
        if (ref_meta['split_years']['test'] != [2024, 2024] or ref_meta['train_fraction'] != 0.15
                or not ref_meta['test_evaluation_completed']):
            raise ValueError('Expected completed original 15% models evaluated in 2024')
        ref = default_metrics(original_root / mode / 'metrics/test_metrics')
        for model in REFERENCE_MODELS:
            records.append(summary_record(
                mode, model, 0.15, ref[ref.model == model],
                source=original_root / mode / 'metrics/test_metrics'))
        full_meta = document(full_root / 'models' / mode / 'metadata')
        compare_protocol(full_meta, ref_meta, 'Full-training')
        if (full_meta['train_fraction'] != 1
                or full_meta['counts']['train_sample'] != ref_meta['counts']['train_full']):
            raise ValueError('Not full training')
        if (document(full_root / 'models' / mode / 'empirical_support')
                != document(original_root / mode / 'empirical_support')):
            raise ValueError('Full-training amount support differs')
        full_metrics = default_metrics(full_root / 'models' / mode / 'metrics/test_metrics')
        for model in REFERENCE_MODELS:
            metrics = full_metrics[full_metrics.model == model]
            compare_cohort(metrics, ref[ref.model == model])
            records.append(summary_record(mode, model, 1.0, metrics,
                                          source=full_root / 'models' / mode / 'metrics/test_metrics'))
        full_daily = csv(full_root / 'models' / mode / 'metrics/daily_scores')
        daily_check = full_daily.rename(columns={'sum_sq_error_rf': 'sum_squared_error'})
        reconcile_daily(full_metrics[full_metrics.model == 'random_forest'], daily_check)

        # These GBT exports also evaluate unchanged 15% RF/LR references.
        for sample, fraction in (('sample30', 0.3), ('sample100', 1.0)):
            base = gbt_root / mode / sample
            meta = document(base / 'metadata')
            if not meta['test_evaluation_completed'] or meta['source_sha256'] != source_hash:
                raise ValueError('GBT source/completion differs')
            compare_protocol(meta, ref_meta, 'GBT')
            if meta['counts']['test'] != ref_meta['counts']['test']:
                raise ValueError('Test count differs')
            if meta['train_fraction'] != fraction or meta['reference_train_fraction'] != 0.15:
                raise ValueError('GBT or RF/LR reference training fraction differs')
            all_metrics = {
                model: default_metrics(base / 'metrics' / model)
                for model in ('gbt', *REFERENCE_MODELS)
            }
            for model, metrics in all_metrics.items():
                reference_model = 'random_forest' if model == 'gbt' else model
                compare_cohort(metrics, ref[ref.model == reference_model])
                reconcile_daily(metrics, csv(base / 'daily_scores' / model))
                reliability = csv(base / 'reliability' / model).groupby('threshold').agg(n=('n', 'sum'))
                if not np.array_equal(reliability.loc[metrics.threshold, 'n'], metrics.n):
                    raise ValueError('Reliability counts differ')
            record = summary_record(mode, 'gbt', fraction, all_metrics['gbt'], source=base / 'metrics/gbt')
            record.update(depth=meta['depth'], temperature=meta['temperature'],
                          train_anchors=meta['counts']['train_sample'])
            records.append(record)
            order = csv(base / 'threshold_order/gbt').iloc[0]
            violations.append(dict(mode=mode, fraction=fraction, **order.to_dict()))
            for q in (3.0, 7.5, 15.0):
                row = dict(
                    mode=mode, fraction=fraction, threshold=q, gbt_train_fraction=fraction,
                    random_forest_train_fraction=0.15, binary_logistic_train_fraction=0.15,
                    evaluation_year=2024, source_path=source_path(base / 'metrics'),
                )
                for model in ('gbt', 'random_forest', 'binary_logistic'):
                    metrics = all_metrics[model]
                    selected = metrics[metrics.threshold == q]
                    if len(selected) != 1:
                        raise ValueError(f'Missing or duplicate interior threshold: {model}, {q}')
                    metric = selected.iloc[0]
                    row[model + '_brier'] = float(metric.brier)
                    row[model + '_pr_auc'] = float(metric.pr_auc)
                interior.append(row)
            checks.append(dict(
                mode=mode, fraction=fraction, daily_brier_reconciled=True,
                cohort_counts_and_prevalence_match=True, source_hash_matches=True,
                reference_train_fraction=0.15, evaluation_year=2024,
            ))
    result = {
        'summary': records, 'interior_thresholds': interior,
        'threshold_order': violations, 'checks': checks,
        'primary_thresholds': Q, 'evaluation_year': 2024,
        'provenance': {
            'original_models': source_path(original_root),
            'full_training_experiment': source_path(full_root),
            'gbt_experiment': source_path(gbt_root),
            'gbt_executed_source': source_path(source), 'gbt_source_sha256': source_hash,
            'gbt_export_rf_lr_reference_fraction': 0.15,
        },
        'validation': {
            'passed': True, 'checks': checks, 'full_training_daily_brier_reconciled': True,
            'source_sha256': source_hash, 'gbt15_raw_verified': False,
            'calendar15_metric_export_verified': calendar15_verified,
        },
        'limitations': [
            'A 15% GBT is summary-only; B 15% has per-threshold text metrics. Neither 15% pipeline is supplied.',
            'Counts and prevalence agree; row-level input identity is not independently proven.',
            'Imported 2024 results are supplementary follow-ups; original models remain unchanged.',
            'RF/LR scores inside GBT exports use 15% reference models; no 30% RF/LR test scores are inferred.',
            'Climatology fraction identifies its comparison group; frequencies use full training data.',
        ],
    }
    return result

def main():
    facts = collect_facts()
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / 'experiments_facts.json').write_text(
        json.dumps(facts, indent=2, allow_nan=False) + '\n')
    pd.DataFrame(facts['summary']).to_csv(REPORT / 'experiments_summary.csv', index=False)
    pd.DataFrame(facts['interior_thresholds']).to_csv(
        REPORT / 'interior_threshold_comparison.csv', index=False)
    (REPORT / 'experiments_validation.json').write_text(
        json.dumps(facts['validation'], indent=2, allow_nan=False) + '\n')
    print(pd.DataFrame(facts['summary'])[
        ['mode', 'model', 'fraction', 'mean_brier', 'evidence']].to_string(index=False))


if __name__ == '__main__':
    main()
