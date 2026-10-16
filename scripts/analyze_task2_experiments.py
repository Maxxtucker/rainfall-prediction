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
LR30 = ROOT / 'outputs/steps/lr-sampling-20261015'
RF30 = ROOT / 'outputs/steps/rf30-evaluation-20261016'
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
    if primary.n.nunique() != 1:
        raise ValueError('Threshold evaluation denominators differ')
    at_one = primary.loc[primary.threshold == 1].iloc[0]
    record = dict(
        mode=mode, model=model, fraction=fraction,
        mean_brier=float(primary.brier.mean()),
        mean_log_loss=float(primary.log_loss.mean()),
        mean_pr_auc=float(primary.pr_auc.mean()),
        pr_auc_1mm=float(at_one.pr_auc), log_loss_1mm=float(at_one.log_loss),
        roc_auc_1mm=float(at_one.roc_auc) if 'roc_auc' in primary else None,
        evidence=evidence, evaluation_year=2024, test_anchors=int(primary.n.iloc[0]),
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


def lr30_record(base, mode, ref_meta, reference_metrics):
    """Verify an independently fitted LR model before exposing its 30% scores."""
    meta = document(base / 'metadata')
    compare_protocol(meta, ref_meta, 'LR30')
    if (not meta['test_evaluation_completed'] or meta['train_fraction'] != .3
            or not meta.get('saved_pipeline_reload_verified')):
        raise ValueError('LR30 is incomplete or has an incorrect fitting fraction')
    expected = {'short_term': 5608769, 'calendar': 8233882}[mode]
    if meta['counts']['train_sample'] != expected:
        raise ValueError('LR30 training sample differs from the nested 30% sample')
    if meta['counts']['train_full'] != ref_meta['counts']['train_full']:
        raise ValueError('LR30 full training count differs')
    source = base.parent / 'source/train_lr_sampling.py'
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != meta.get('source_sha256'):
        raise ValueError('LR30 executed-source hash differs')
    metrics = default_metrics(base / 'metrics/test_metrics')
    if set(metrics.model) != {'binary_logistic'}:
        raise ValueError('LR30 contains unexpected model metrics')
    compare_cohort(metrics, reference_metrics)
    reconcile_daily(metrics, csv(base / 'metrics/daily_scores'))
    bins = csv(base / 'metrics/reliability').groupby('threshold').n.sum()
    if not np.array_equal(bins.loc[metrics.threshold].to_numpy(), metrics.n.to_numpy()):
        raise ValueError('LR30 reliability counts differ')
    record = summary_record(mode, 'binary_logistic', .3, metrics,
                            source=base / 'metrics/test_metrics')
    selected = next(c for c in meta.get('candidates', []) if c['reg_param'] == meta['reg_param'])
    history = selected['objective_history']
    if not history or not np.isfinite(history).all():
        raise ValueError('LR30 objective history is missing or nonfinite')
    record.update(train_anchors=expected, reg_param=meta['reg_param'],
                  iterations=selected['iterations'], max_iter=meta['max_iter'],
                  objective_initial=history[0], objective_final=history[-1])
    return record


def rf30_record(base, mode, ref_meta, reference_metrics, original_root):
    """Admit existing RF30 weights only after full calibration/test completion."""
    meta = document(base / 'metadata')
    compare_protocol(meta, ref_meta, 'RF30')
    if (not meta['test_evaluation_completed'] or not meta['calibration_completed']
            or meta['train_fraction'] != .3 or meta['weights_retrained']):
        raise ValueError('RF30 evaluation is incomplete or is not the saved 30% forest')
    if meta['counts']['train_sample'] != {'short_term':5608769, 'calendar':8233882}[mode]:
        raise ValueError('RF30 training sample differs')
    if meta['counts']['train_full'] != ref_meta['counts']['train_full']:
        raise ValueError('RF30 full training population differs')
    for split in ('validation','calibration','test'):
        if meta['counts'][split] != ref_meta['counts'][split]:
            raise ValueError('RF30 ' + split + ' population differs from reference')
    expected = {'depth':ref_meta['depth'], 'num_trees':ref_meta['num_trees'],
                'max_bins':ref_meta['max_bins'], 'min_instances_per_node':25,
                'feature_subset_strategy':'sqrt', 'subsampling_rate':.8}
    if any(meta[key] != value for key, value in expected.items()):
        raise ValueError('RF30 settings differ from the reference forest')
    source = base.parent / 'source/evaluate_rf_sampling.py'
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != meta['source_sha256']:
        raise ValueError('RF30 evaluation source hash differs')
    if document(base / 'empirical_support') != document(original_root / mode / 'empirical_support'):
        raise ValueError('RF30 full-training empirical support differs')
    selection = csv(base / 'metrics/calibration_selection')
    if selection.temperature.duplicated().any() or set(selection.temperature) != {.5,.75,1.,1.25,1.5,2.}:
        raise ValueError('RF30 temperature grid differs')
    best = min(selection.to_dict('records'), key=lambda r:(r['macro_brier'], abs(r['temperature']-1)))
    if best['temperature'] != meta['temperature']:
        raise ValueError('RF30 selected temperature differs from 2023 scores')
    metrics = default_metrics(base / 'metrics/test_metrics')
    if set(metrics.model) != {'random_forest'}:
        raise ValueError('RF30 contains unexpected model scores')
    compare_cohort(metrics, reference_metrics)
    reconcile_daily(metrics, csv(base / 'metrics/daily_scores'))
    bins = csv(base / 'metrics/reliability').groupby('threshold').n.sum()
    if not np.array_equal(bins.loc[metrics.threshold].to_numpy(), metrics.n.to_numpy()):
        raise ValueError('RF30 reliability counts differ')
    record = summary_record(mode, 'random_forest', .3, metrics, source=base / 'metrics/test_metrics')
    record.update(temperature=meta['temperature'], depth=meta['depth'],
                  train_anchors=meta['counts']['train_sample'], weights_retrained=False)
    return record


def matched30_diagnostics(rf_root, lr_root, gbt_root):
    """Compare extra thresholds and mean risks at one matched fitting fraction."""
    interior, risks = [], []
    for mode in ('short_term','calendar'):
        locations = {
            'random_forest': (rf_root / mode / 'metrics/test_metrics', rf_root / mode / 'metrics/reliability'),
            'binary_logistic': (lr_root / mode / 'metrics/test_metrics', lr_root / mode / 'metrics/reliability'),
            'gbt': (gbt_root / mode / 'sample30/metrics/gbt', gbt_root / mode / 'sample30/reliability/gbt'),
        }
        metrics = {name:default_metrics(paths[0]) for name,paths in locations.items()}
        for q in (3.,7.5,15.):
            selected = {name:frame[frame.threshold == q].iloc[0] for name,frame in metrics.items()}
            reference = selected['random_forest']
            if any(row.n != reference.n or abs(row.prevalence-reference.prevalence)>1e-14
                   for row in selected.values()):
                raise ValueError('Matched 30% interior-query cohorts differ')
            row = dict(mode=mode,fraction=.3,threshold=q,evaluation_year=2024,
                       random_forest_train_fraction=.3,binary_logistic_train_fraction=.3,gbt_train_fraction=.3,
                       source_paths={name:source_path(paths[0]) for name,paths in locations.items()})
            for name,value in selected.items():
                row[name+'_brier'], row[name+'_pr_auc'] = float(value.brier), float(value.pr_auc)
            interior.append(row)
        for name,(metric_path,bin_path) in locations.items():
            bins = csv(bin_path)
            if bins.duplicated(['threshold','bin']).any():
                raise ValueError('Duplicate matched-risk probability bins')
            for q in Q:
                part = bins[bins.threshold == q]
                metric = metrics[name][metrics[name].threshold == q].iloc[0]
                n = int(part.n.sum())
                if n != int(metric.n) or n == 0:
                    raise ValueError('Matched-risk bin counts differ from test metrics')
                predicted = float((part.n*part.mean_probability).sum()/n)
                observed = float((part.n*part.event_rate).sum()/n)
                if not 0 <= predicted <= 1 or abs(observed-metric.prevalence)>1e-12:
                    raise ValueError('Matched-risk event prevalence differs')
                risks.append(dict(mode=mode,model=name,fraction=.3,threshold=q,n=n,
                                  mean_probability=predicted,event_rate=float(metric.prevalence),
                                  source_path=source_path(bin_path)))
    return interior, risks


def require_complete_grid(records):
    """A common-year comparison must contain all 18 classifier cells once."""
    required = {(mode, model, fraction) for mode in ('short_term','calendar')
                for model in ('random_forest','binary_logistic','gbt') for fraction in (.15,.3,1.)}
    classifier_rows = [r for r in records if r['model'] != 'climatology']
    keys = [(r['mode'], r['model'], r['fraction']) for r in classifier_rows]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate classifier cells in comparison grid')
    if any(r['evaluation_year'] != 2024 for r in classifier_rows):
        raise ValueError('All comparison scores must use 2024')
    missing = required - set(keys)
    if missing:
        raise ValueError('Unified 2024 model/fraction grid is incomplete: ' + str(sorted(missing)))


def collect_facts(*, gbt_root=GBT, full_root=FULL, original_root=ORIGINAL, lr30_root=LR30, rf30_root=RF30):
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
        reference_rf = primary_metrics(ref[ref.model == 'random_forest'])
        if set(reference_rf.n) != {ref_meta['counts']['test']}:
            raise ValueError('Reference test count differs from its metadata')
        for name in REFERENCE_MODELS:
            compare_cohort(ref[ref.model == name], reference_rf)

        for model in REFERENCE_MODELS:
            row = summary_record(mode, model, 0.15, ref[ref.model == model],
                                 source=original_root / mode / 'metrics/test_metrics')
            if model == 'random_forest':
                row.update(depth=ref_meta['depth'], temperature=ref_meta['temperature'])
            records.append(row)
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
            row = summary_record(mode, model, 1.0, metrics,
                                 source=full_root / 'models' / mode / 'metrics/test_metrics')
            if model == 'random_forest':
                row.update(depth=full_meta['depth'], temperature=full_meta['temperature'])
            records.append(row)
        full_daily = csv(full_root / 'models' / mode / 'metrics/daily_scores')
        daily_check = full_daily.rename(columns={'sum_sq_error_rf': 'sum_squared_error'})
        reconcile_daily(full_metrics[full_metrics.model == 'random_forest'], daily_check)

        # Dedicated LR-only follow-up; do not infer fractions from GBT folders.
        if lr30_root.exists():
            records.append(lr30_record(lr30_root / mode, mode, ref_meta,
                                      ref[ref.model == 'binary_logistic']))
            checks.append(dict(mode=mode, model='binary_logistic', fraction=.3,
                               daily_brier_reconciled=True, cohort_counts_and_prevalence_match=True,
                               saved_pipeline_reload_verified=True, source_hash_matches=True, evaluation_year=2024))

        if rf30_root.exists():
            records.append(rf30_record(rf30_root / mode, mode, ref_meta,
                                       ref[ref.model == 'random_forest'], original_root))
            checks.append(dict(mode=mode, model='random_forest', fraction=.3,
                               daily_brier_reconciled=True, cohort_counts_and_prevalence_match=True,
                               calibration_2023_verified=True, source_hash_matches=True,
                               weights_retrained=False, evaluation_year=2024))

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
    require_complete_grid(records)
    matched_interior, matched_risk = matched30_diagnostics(rf30_root, lr30_root, gbt_root)
    result = {
        'summary': records, 'interior_thresholds': matched_interior,
        'reference_export_interior_thresholds': interior, 'matched_threshold_risk': matched_risk,
        'threshold_order': violations, 'checks': checks,
        'primary_thresholds': Q, 'evaluation_year': 2024,
        'provenance': {
            'original_models': source_path(original_root),
            'full_training_experiment': source_path(full_root),
            'gbt_experiment': source_path(gbt_root),
            'lr30_experiment': source_path(lr30_root) if lr30_root.exists() else None,
            'rf30_evaluation': source_path(rf30_root),
            'gbt_executed_source': source_path(source), 'gbt_source_sha256': source_hash,
            'gbt_export_rf_lr_reference_fraction': 0.15,
        },
        'validation': {
            'passed': True, 'unified_2024_grid_complete': True, 'checks': checks, 'full_training_daily_brier_reconciled': True,
            'source_sha256': source_hash, 'gbt15_raw_verified': False,
            'calendar15_metric_export_verified': calendar15_verified,
        },
        'limitations': [
            'A 15% GBT is summary-only; B 15% has per-threshold text metrics. Neither 15% pipeline is supplied.',
            'Available per-threshold exports agree in counts/prevalence; A15 GBT is aggregate-only and row-level identity is not independently proven.',
            'Imported 2024 results are supplementary follow-ups; original models remain unchanged.',
            'RF/LR scores inside GBT exports use 15% reference models; separate LR30 evidence is used only when present. RF30 is calibrated/tested separately using the saved standard-configuration weights.',
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
