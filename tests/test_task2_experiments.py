"""Check threshold aggregation and read/write boundaries without Spark."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
try:
    import analyze_task2_experiments as analysis
finally:
    sys.path.pop(0)


def metric_grid():
    return pd.DataFrame({
        'model': ['gbt'] * len(analysis.Q),
        'threshold': analysis.Q,
        'brier': [.01 * (index + 1) for index in range(len(analysis.Q))],
        'log_loss': [.02 * (index + 1) for index in range(len(analysis.Q))],
        'pr_auc': [.1 * (index + 1) for index in range(len(analysis.Q))],
        'n': [100] * len(analysis.Q), 'prevalence': [.1] * len(analysis.Q),
    })


class ExperimentSummaryTests(unittest.TestCase):
    def test_means_exclude_interior_queries_and_one_mm_is_not_the_mean(self):
        primary = metric_grid()
        extra = primary.iloc[:3].copy()
        extra['threshold'] = [3., 7.5, 15.]
        extra[['brier', 'log_loss', 'pr_auc']] = [0.9, 9., 0.99]
        metrics = pd.concat([primary, extra], ignore_index=True)
        record = analysis.summary_record('calendar', 'gbt', .3, metrics)
        self.assertAlmostEqual(record['mean_brier'], .04)
        self.assertAlmostEqual(record['mean_log_loss'], .08)
        self.assertAlmostEqual(record['mean_pr_auc'], .4)
        self.assertAlmostEqual(record['log_loss_1mm'], .06)
        self.assertAlmostEqual(record['pr_auc_1mm'], .3)

    def test_missing_and_duplicate_primary_grid_fail(self):
        primary = metric_grid()
        cases = [
            (primary[primary.threshold != 2], 'Missing primary'),
            (pd.concat([primary, primary.iloc[[2]]]), 'Duplicate metric'),
        ]
        for metrics, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                analysis.summary_record('calendar', 'gbt', .15, metrics)
            with self.subTest(cohort=message), self.assertRaisesRegex(ValueError, message):
                analysis.compare_cohort(metrics, primary)

    def test_duplicate_interior_queries_and_pooled_models_fail(self):
        primary = metric_grid()
        extra = primary.iloc[[0, 1]].copy()
        extra['threshold'] = 3.
        with self.assertRaisesRegex(ValueError, 'Duplicate metric'):
            analysis.summary_record('calendar', 'gbt', .3, pd.concat([primary, extra]))
        primary.loc[0, 'model'] = 'random_forest'
        with self.assertRaisesRegex(ValueError, 'one model'):
            analysis.summary_record('calendar', 'gbt', .15, primary)

    def test_summary_only_evidence_leaves_unavailable_one_mm_metrics_null(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'teammate-summary.md').write_text(
                '| short_term | 15% | 0.016 | 0.07 | 0.31 | 5 | 0.75 |\n'
                '| calendar | 15% | 0.022 | 0.10 | 0.04 | 5 | 1.0 |\n')
            records = analysis.reported15(root)
            for record in records:
                self.assertIsNone(record['log_loss_1mm'])
                self.assertIsNone(record['pr_auc_1mm'])
                self.assertEqual(record['fraction'], .15)
                self.assertEqual(record['evidence'], 'teammate summary only')

    def test_historical_frequency_keeps_comparison_label_without_implying_sampling(self):
        record = analysis.summary_record('calendar', 'climatology', .15, metric_grid())
        self.assertEqual(record['fraction'], .15)
        self.assertEqual(record['fit_fraction'], 1.)

    def test_lr30_reconciles_daily_errors_and_rejects_corruption(self):
        reference = {'split_years': {}, 'numeric_features': ['latitude'],
                     'seed': 2026, 'eval_fraction': 1.,
                     'counts': {'train_full': 27434001}}
        meta = dict(reference, train_fraction=.3, test_evaluation_completed=True,
                    saved_pipeline_reload_verified=True, reg_param=.01, max_iter=100,
                    source_sha256=hashlib.sha256(b'test source').hexdigest(),
                    candidates=[{'reg_param': .01, 'iterations': 20, 'objective_history': [.2, .1]}],
                    counts={'train_sample': 8233882, 'train_full': 27434001})
        metrics = metric_grid()
        metrics['model'] = 'binary_logistic'
        metrics['cutoff_kind'] = 'default_0.5'
        daily = metrics[['threshold', 'n']].copy()
        daily['sum_squared_error'] = metrics.brier * metrics.n
        reliability = metrics[['threshold', 'n']].copy()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / 'calendar'
            source = Path(temporary) / 'source/train_lr_sampling.py'
            source.parent.mkdir()
            source.write_bytes(b'test source')
            for folder, frame in [('metrics/test_metrics', metrics),
                                  ('metrics/daily_scores', daily),
                                  ('metrics/reliability', reliability)]:
                path = base / folder
                path.mkdir(parents=True)
                frame.to_csv(path / 'part-00000.csv', index=False)
            with patch.object(analysis, 'document', return_value=meta):
                record = analysis.lr30_record(base, 'calendar', reference, metrics)
                self.assertEqual(record['fraction'], .3)
                self.assertEqual(record['train_anchors'], 8233882)
                daily.loc[0, 'sum_squared_error'] += 1
                daily.to_csv(base / 'metrics/daily_scores/part-00000.csv', index=False)
                with self.assertRaisesRegex(ValueError, 'Daily Brier'):
                    analysis.lr30_record(base, 'calendar', reference, metrics)

    def test_lr30_rejects_reference_models_mislabeled_as_30_percent(self):
        reference = {'split_years': {}, 'numeric_features': ['latitude'],
                     'seed': 2026, 'eval_fraction': 1.,
                     'counts': {'train_full': 27434001}}
        meta = dict(reference, train_fraction=.15, test_evaluation_completed=True,
                    saved_pipeline_reload_verified=True,
                    counts={'train_sample': 4115222, 'train_full': 27434001})
        with patch.object(analysis, 'document', return_value=meta):
            with self.assertRaisesRegex(ValueError, 'incorrect fitting fraction'):
                analysis.lr30_record(Path('/tmp/fake-lr'), 'calendar', reference, metric_grid())
        meta['train_fraction'] = .3
        with patch.object(analysis, 'document', return_value=meta):
            with self.assertRaisesRegex(ValueError, 'nested 30% sample'):
                analysis.lr30_record(Path('/tmp/fake-lr'), 'calendar', reference, metric_grid())

    def test_common_year_grid_rejects_missing_rf30_or_validation_scores(self):
        records = [dict(mode=mode,model=model,fraction=fraction,evaluation_year=2024)
                   for mode in ('short_term','calendar')
                   for model in ('random_forest','binary_logistic','gbt') for fraction in (.15,.3,1.)]
        analysis.require_complete_grid(records)
        missing = [r for r in records if not (r['model']=='random_forest' and r['fraction']==.3)]
        with self.assertRaisesRegex(ValueError, 'grid is incomplete'):
            analysis.require_complete_grid(missing)
        records[1]['evaluation_year'] = 2022
        with self.assertRaisesRegex(ValueError, 'must use 2024'):
            analysis.require_complete_grid(records)

    def test_copied_rf_pipeline_rejects_modified_weights(self):
        import importlib.util
        location = Path(__file__).resolve().parents[1] / 'scripts/verify_rf_sampling.py'
        spec = importlib.util.spec_from_file_location('verify_rf_sampling', location)
        verify = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verify)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, copied = root/'source', root/'copied'
            source.mkdir(); copied.mkdir()
            (source/'part-00000').write_bytes(b'original forest weights')
            (copied/'part-00000').write_bytes(b'original forest weights')
            self.assertEqual(verify.verify_exact_copy(source,copied),1)
            (copied/'part-00000').write_bytes(b'different forest weights')
            with self.assertRaisesRegex(ValueError, 'weights differ'):
                verify.verify_exact_copy(source,copied)

    def test_rf30_rejects_validation_only_metadata(self):
        reference = {'split_years': {}, 'numeric_features': ['latitude'],
                     'seed': 2026, 'eval_fraction': 1.}
        meta = dict(reference, test_evaluation_completed=False, calibration_completed=False,
                    train_fraction=.3, weights_retrained=False)
        with patch.object(analysis, 'document', return_value=meta):
            with self.assertRaisesRegex(ValueError, 'evaluation is incomplete'):
                analysis.rf30_record(Path('/tmp/no-eval'), 'calendar', reference,
                                     metric_grid(), Path('/tmp/original'))

    def test_rf30_rejects_temperature_not_selected_on_2023(self):
        reference = {'split_years': {}, 'numeric_features': ['latitude'],
                     'seed': 2026, 'eval_fraction': 1., 'depth':8,'num_trees':40,'max_bins':90,
                     'counts':{'train_full':27434001,'validation':100,'calibration':100,'test':100}}
        meta = dict(reference, test_evaluation_completed=True, calibration_completed=True,
                    train_fraction=.3, weights_retrained=False, temperature=.75,
                    counts={'train_sample':8233882,'train_full':27434001,'validation':100,'calibration':100,'test':100},
                    min_instances_per_node=25, feature_subset_strategy='sqrt', subsampling_rate=.8,
                    source_sha256=hashlib.sha256(b'RF evaluation source').hexdigest())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);base=root/'calendar'
            source=root/'source/evaluate_rf_sampling.py';source.parent.mkdir()
            source.write_bytes(b'RF evaluation source')
            path=base/'metrics/calibration_selection';path.mkdir(parents=True)
            pd.DataFrame({'temperature':[.5,.75,1.,1.25,1.5,2.],
                          'macro_brier':[.03,.025,.02,.025,.03,.04]}).to_csv(path/'part-0.csv',index=False)
            with patch.object(analysis,'document',side_effect=[meta,[],[]]):
                with self.assertRaisesRegex(ValueError,'selected temperature differs'):
                    analysis.rf30_record(base,'calendar',reference,metric_grid(),root/'original')

    def test_summary_rejects_different_test_denominators_between_queries(self):
        frame = metric_grid()
        frame.loc[0, 'n'] = 99
        with self.assertRaisesRegex(ValueError, 'denominators differ'):
            analysis.summary_record('calendar','gbt',.3,frame)

    def test_main_writes_only_four_canonical_report_artifacts(self):
        record = analysis.summary_record('calendar', 'gbt', .3, metric_grid())
        facts = {'summary': [record], 'interior_thresholds': [],
                 'validation': {'passed': True}}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            saved = root / 'outputs/recorded'
            saved.mkdir(parents=True)
            sentinel = saved / 'integration_validation.json'
            sentinel.write_text('historical evidence')
            report = root / 'report/task2'
            with patch.object(analysis, 'collect_facts', return_value=facts), \
                    patch.object(analysis, 'REPORT', report), \
                    contextlib.redirect_stdout(io.StringIO()):
                analysis.main()
            self.assertEqual({path.name for path in report.iterdir()}, {
                'experiments_facts.json', 'experiments_summary.csv',
                'interior_threshold_comparison.csv', 'experiments_validation.json',
            })
            self.assertEqual(json.loads((report / 'experiments_facts.json').read_text()), facts)
            self.assertEqual(sentinel.read_text(), 'historical evidence')
            self.assertEqual(list(saved.iterdir()), [sentinel])


if __name__ == '__main__':
    unittest.main()
