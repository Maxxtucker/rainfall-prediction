"""Paired sensitivity summaries must preserve sample alignment and score direction."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import pandas as pd

spec = importlib.util.spec_from_file_location('rf_sensitivity_analysis',
    Path(__file__).resolve().parents[1] / 'scripts/analyze_rf_sensitivity.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class SensitivityAnalysisTests(unittest.TestCase):
    def test_paired_improvement_and_sample_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [{'date': d.strftime('%Y-%m-%d'), 'threshold': q, 'n': 100,
                     'sse': 10., 'events': 5., 'sum_probability': 5.}
                    for d in pd.date_range('2022-01-01', '2022-12-31') for q in [0., 1.]]
            for name, factor in [('ref', 1.), ('candidate', .9)]:
                dest = root / 'short_term' / name / 'validation_daily'
                dest.mkdir(parents=True)
                frame = pd.DataFrame(rows)
                frame['sse'] *= factor
                frame.to_csv(dest / 'part-00000.csv', index=False)
            result = analysis.paired_comparison(root, 'short_term', 'ref', 'candidate', repetitions=20)
            self.assertAlmostEqual(result['relative_improvement_percent'], 10.)
            for bound in result['conditional_95_percent_interval']:
                self.assertAlmostEqual(bound, 10.)
            dest = root / 'short_term/candidate/validation_daily/part-00000.csv'
            frame = pd.read_csv(dest)
            frame.loc[0, 'n'] = 99
            frame.to_csv(dest, index=False)
            with self.assertRaisesRegex(ValueError, 'different validation anchors'):
                analysis.paired_comparison(root, 'short_term', 'ref', 'candidate', repetitions=20)


if __name__ == '__main__':
    unittest.main()
