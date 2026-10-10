"""Local summaries must be reproducible and must not rewrite saved models."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
try:
    import analyze_rf_sensitivity as analysis
    import prepare_rf_sensitivity_models as prepare
finally:
    sys.path.pop(0)


def write_document(path, value, part='part-00000'):
    path.mkdir(parents=True, exist_ok=True)
    (path / part).write_text(json.dumps(value))
    (path / '_SUCCESS').touch()


def experiment(root):
    records = []
    for index, name in enumerate(analysis.CANDIDATES[:-1]):
        brier = .1 + index * .001
        record = {'mode': 'calendar', 'name': name, 'fraction': .3 if name == 'sample30' else .15,
                  'reuse': name == 'original15', 'depth': 10 if name == 'depth10' else 8,
                  'trees': 80 if name == 'trees80' else 40,
                  'min_instances_per_node': 50 if name == 'leaf50' else 25,
                  'feature_subset_strategy': '0.5' if name == 'features_half' else 'sqrt',
                  'subsampling_rate': .8, 'seed': 2026,
                  'counts': {'train15': 150, 'train30': 300, 'validation': 36500},
                  'validation_macro_brier': brier,
                  'threshold_metrics': [{'threshold': q, 'n': 36500, 'brier': brier, 'event_rate': .05}
                                        for q in [0., 1.]],
                  'fit_seconds': 0. if name == 'original15' else 60.,
                  'elapsed_seconds': 70., 'test_accessed': False}
        records.append(record)
        dest = root / 'calendar' / name
        daily = dest / 'validation_daily'
        daily.mkdir(parents=True)
        rows = [{'date': day.strftime('%Y-%m-%d'), 'threshold': q, 'n': 100,
                 'sse': brier * 100, 'events': 5, 'sum_probability': 5.}
                for day in pd.date_range('2022-01-01', '2022-12-31') for q in [0., 1.]]
        pd.DataFrame(rows).to_csv(daily / 'part-00000.csv', index=False)
        (dest / 'pipeline').mkdir()
        (dest / 'pipeline' / 'saved-model').write_text('forest is not loaded by these tests')
        write_document(dest / 'metadata', {'preserve': name})
    write_document(root / 'results', records)
    write_document(root / 'completion', {'complete': True, 'candidates': len(records), 'test_accessed': False})
    return records


class SensitivitySummaryTests(unittest.TestCase):
    def test_stats_only_single_mode_and_repeatable_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = experiment(root)
            metadata = root / 'calendar/sample30/metadata/part-00000'
            before = metadata.read_bytes()
            text = analysis.analyze_results(root)
            self.assertIn('## calendar', text)
            self.assertNotIn('## short_term', text)
            outputs = {name: (root / name).read_bytes()
                       for name in ('analysis.md', 'analysis.json', 'candidate_summary.csv')}
            write_document(root / 'results', list(reversed(records)))
            analysis.analyze_results(root)
            self.assertEqual(before, metadata.read_bytes())
            self.assertEqual(outputs, {name: (root / name).read_bytes() for name in outputs})

    def test_invalid_candidate_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = experiment(root)
            cases = []
            duplicate = copy.deepcopy(records)
            duplicate[-1] = duplicate[0]
            cases.append((duplicate, len(records), 'Duplicate'))
            cases.append((records, 99, 'candidate count'))
            cases.append((records[:-1], len(records) - 1, 'Missing required'))
            counts = copy.deepcopy(records)
            counts[1]['counts']['validation'] -= 1
            cases.append((counts, len(records), 'validation counts'))
            for changed, count, message in cases:
                with self.subTest(message=message):
                    write_document(root / 'results', changed)
                    write_document(root / 'completion', {'complete': True, 'candidates': count, 'test_accessed': False})
                    with self.assertRaisesRegex(ValueError, message):
                        analysis.analyze_results(root)
                    self.assertFalse((root / 'candidate_summary.csv').exists())

    def test_daily_dates_counts_and_reconciliation_are_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = experiment(root)
            path = root / 'calendar/sample30/validation_daily/part-00000.csv'
            original = pd.read_csv(path)
            for column, value, message in [('date', '2024-01-01', '2022 dates'),
                                            ('date', 'not-a-date', '2022 dates'),
                                            ('n', -1, 'Invalid daily counts'),
                                            ('events', 101, 'Invalid daily counts'),
                                            ('sse', float('inf'), 'Invalid daily counts')]:
                with self.subTest(column=column, value=value):
                    changed = original.copy()
                    changed.loc[0, column] = value
                    changed.to_csv(path, index=False)
                    with self.assertRaisesRegex(ValueError, message):
                        analysis.paired_comparison(root, 'calendar', 'original15', 'sample30', repetitions=2)
            changed = original.copy()
            changed['sse'] *= .9
            changed.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'do not match candidate result'):
                analysis.validate_daily_result(root, records[1])

    def test_explicit_model_preparation_is_repeatable_and_removes_stale_parts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'experiment'
            records = experiment(root)
            source = Path(temporary) / 'original/calendar'
            original = {'schema_version': 2, 'feature_mode': 'calendar_v2', 'seed': 2026,
                        'counts': {'train_sample': 150, 'train_full': 1000, 'validation': 36500},
                        'thresholds_evaluated': [0., 1.], 'numeric_features': ['latitude'],
                        'model': 'old forest + temperature calibration', 'temperature': 1.5,
                        'test_evaluation_completed': True, 'cutoffs_binary': {'1': .2},
                        'binary_baseline': 'LogisticRegression', 'created_utc': 'old-runtime-time',
                        'limitations': ['Binary logistic claim'], 'train_max_y30': 21.}
            write_document(source / 'metadata', original)
            write_document(source / 'empirical_support', [{'n': 1000}], 'part-original.txt')
            (source / 'stations').mkdir()
            (source / 'stations/part-current.parquet').write_bytes(b'saved station table')
            candidate = root / 'calendar/sample30'
            write_document(candidate / 'metadata', {'stale': True}, 'part-stale.txt')
            (candidate / 'stations').mkdir()
            (candidate / 'stations/part-old.parquet').write_bytes(b'stale')
            forest = (candidate / 'pipeline/saved-model').read_bytes()
            self.assertEqual(prepare.prepare_models(root, source.parent), 5)
            metadata = analysis.read_document(candidate / 'metadata')
            self.assertEqual(metadata['supported_predictors'], ['random_forest'])
            self.assertEqual(metadata['temperature'], 1.)
            self.assertFalse(metadata['calibration_completed'])
            self.assertFalse(metadata['test_evaluation_completed'])
            self.assertEqual(metadata['counts']['train_sample'], 300)
            self.assertNotIn('created_utc', metadata)
            self.assertNotIn('binary_baseline', metadata)
            self.assertNotIn('cutoffs_binary', metadata)
            self.assertNotIn('Binary logistic', json.dumps(metadata))
            self.assertNotIn(str(Path(temporary)), json.dumps(metadata))
            self.assertFalse((candidate / 'metadata/part-stale.txt').exists())
            self.assertFalse((candidate / 'stations/part-old.parquet').exists())
            first = (candidate / 'metadata/part-00000').read_bytes()
            prepare.prepare_models(root, source.parent)
            self.assertEqual(first, (candidate / 'metadata/part-00000').read_bytes())
            self.assertEqual(original, analysis.read_document(source / 'metadata'))
            self.assertEqual(forest, (candidate / 'pipeline/saved-model').read_bytes())
            self.assertEqual({'preserve': 'original15'}, analysis.read_document(root / 'calendar/original15/metadata'))


if __name__ == '__main__':
    unittest.main()
