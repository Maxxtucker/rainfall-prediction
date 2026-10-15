"""Check threshold aggregation and read/write boundaries without Spark."""
import contextlib
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
