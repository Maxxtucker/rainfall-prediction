"""Fabricated semantic fixtures for calendar-only labels, splits and binary scoring."""
import unittest
from datetime import datetime, timedelta
from pyspark.sql import SparkSession, functions as F
from rainfall.data import make_calendar_samples, make_features, calendar_features, NUMERIC_FEATURES
from rainfall.model import expand_thresholds, binary_pipeline, score_binary, temporal_split


class CalendarRiskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (SparkSession.builder.master('local[2]').appName('calendar-risk-tests')
            .config('spark.ui.enabled', 'false').config('spark.sql.shuffle.partitions', '2')
            .config('spark.sql.session.timeZone', 'Asia/Singapore').getOrCreate())
        cls.spark.sparkContext.setLogLevel('ERROR')

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def observations(self, missing=None):
        start = datetime(2024, 5, 1)
        rows = [('S77', (start + timedelta(minutes=5*i)).strftime('%Y-%m-%d %H:%M:%S'),
                 1.35, 103.85, float(i)) for i in range(9) if i != missing]
        return self.spark.createDataFrame(rows, 'station_id string,time_text string,latitude double,longitude double,rainfall double').withColumn('timestamp', F.to_timestamp('time_text'))

    def test_first_anchor_needs_no_history_and_exact_future_sum(self):
        row = make_calendar_samples(self.observations()).orderBy('timestamp').first()
        self.assertTrue(row.label_complete)
        self.assertEqual(row.y30, 21.0)
        self.assertFalse(any(name.startswith('rain_') for name in NUMERIC_FEATURES))

    def test_missing_future_does_not_use_next_six_rows(self):
        row = make_calendar_samples(self.observations(missing=3)).orderBy('timestamp').first()
        self.assertFalse(row.label_complete)
        self.assertIsNone(row.y30)

    def test_calendar_can_score_when_short_term_history_unavailable(self):
        frame = (self.observations().withColumn('station_name', F.lit('TEST'))
            .withColumn('update_timestamp', F.lit(None).cast('timestamp'))
            .withColumn('reading_update_timestamp', F.lit(None).cast('timestamp'))
            .withColumn('availability_missing', F.lit(True)))
        calendar = make_calendar_samples(frame).orderBy('timestamp').first()
        short = make_features(frame).orderBy('timestamp').first()
        self.assertTrue(calendar.label_complete)
        self.assertTrue(short.label_complete)
        self.assertFalse(short.history_complete)
        self.assertEqual(calendar.y30, short.y30)

    def test_future_query_and_strict_threshold_labels(self):
        future = self.spark.createDataFrame([('S77', '2026-12-01 15:00:00', 1.35, 103.85)],
            'station_id string,time_text string,latitude double,longitude double').withColumn('timestamp', F.to_timestamp('time_text'))
        self.assertEqual(calendar_features(future).first().year, 2026)
        frame = calendar_features(future).withColumn('y30', F.lit(3.0))
        labels = {r.threshold: r.label for r in expand_thresholds(frame, [1,3,5]).collect()}
        self.assertEqual(labels, {1.0: 1.0, 3.0: 0.0, 5.0: 0.0})

    def test_boundary_purge(self):
        frame = self.spark.createDataFrame([('2021-12-31 23:45:00',), ('2021-12-31 23:00:00',)], ['time_text']).withColumn('timestamp', F.to_timestamp('time_text'))
        self.assertEqual(temporal_split(calendar_features(frame), 2017, 2022).count(), 1)

    def test_shared_auc_matches_spark_evaluators(self):
        from pyspark.ml.evaluation import BinaryClassificationEvaluator
        from rainfall.model import roc_pr_auc
        frame = self.spark.createDataFrame([(i / 23.0, float(i % 3 == 0)) for i in range(24)],
                                           'probability double,label double')
        actual = roc_pr_auc(frame)
        for value, name in zip(actual, ['areaUnderROC', 'areaUnderPR']):
            expected = BinaryClassificationEvaluator(rawPredictionCol='probability',
                labelCol='label', metricName=name, numBins=1000).evaluate(frame)
            self.assertAlmostEqual(value, expected, places=12)

    def test_calibrated_survival_matches_python_reference(self):
        from rainfall.model import calibrated_survival
        weights = [0., .2, .7, 1., 1., 1., 1.]
        vectors = [[.7,.2,.1], [.2,.3,.1,.1,.1,.1,.1]]
        frame = self.spark.createDataFrame([(v,) for v in vectors], 'p array<double>')
        for temperature in (.5,.75,1.,1.25,1.5,2.):
            rows = frame.select('p',calibrated_survival(F.col('p'),weights,temperature).alias('result')).collect()
            for row in rows:
                powers = [p ** (1 / temperature) for p in row.p]
                expected = sum(p*w for p,w in zip(powers,weights)) / sum(powers)
                self.assertAlmostEqual(row.result, expected, places=12)

    def test_binary_fit_save_load_probability(self):
        import tempfile
        from pyspark.ml import PipelineModel
        rows = [('S77' if i % 2 else 'S78', f'2021-05-{1+i%20:02d} {i%24:02d}:00:00',
                 1.35, 103.85, float(i%6)) for i in range(80)]
        frame = self.spark.createDataFrame(rows, 'station_id string,time_text string,latitude double,longitude double,y30 double').withColumn('timestamp', F.to_timestamp('time_text'))
        expanded = expand_thresholds(calendar_features(frame), [0,1,5])
        model = binary_pipeline(NUMERIC_FEATURES, .1).fit(expanded)
        with tempfile.TemporaryDirectory() as directory:
            model.write().save(directory + '/pipeline')
            loaded = PipelineModel.load(directory + '/pipeline')
            probabilities = [r.probability for r in score_binary(loaded, expanded).collect()]
        self.assertEqual(len(probabilities), 240)
        self.assertTrue(all(0 <= p <= 1 for p in probabilities))


if __name__ == '__main__':
    unittest.main()
