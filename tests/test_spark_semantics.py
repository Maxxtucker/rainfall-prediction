"""Semantic integration tests using fabricated records and a real Spark session.

Run on the Dataproc cluster before processing annual data. These tests are
purposefully about time, missingness and leakage; they do not validate real-world
forecast quality and do not replace the held-out 2024 evaluation.
"""
from datetime import datetime, timedelta, timezone
import os
import unittest
import uuid
from unittest.mock import patch

from pyspark.ml import PipelineModel

from pyspark.sql import SparkSession, functions as F, types as T

from rainfall.data import clean, explore, make_features, profile_rainfall, _matched_month_panel, HISTORY_NUMERIC_FEATURES as NUMERIC_FEATURES
from rainfall.model import make_pipeline, temporal_split, calibrated_array, survival_expression, deterministic_sample

SGT = timezone(timedelta(hours=8))
COLUMNS = [
    "timestamp", "update_timestamp", "reading_update_timestamp", "station_id",
    "station_name", "station_device_id", "station_location.latitude",
    "station_location.longitude", "reading_value", "reading_unit", "reading_type",
    "source_file", "_corrupt_record",
]
SCHEMA = T.StructType([T.StructField(name, T.StringType(), True) for name in COLUMNS])


def observation(timestamp, amount=0.0, station="FAKE_A001", **overrides):
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)
    item = {
        "timestamp": timestamp.isoformat(),
        "update_timestamp": (timestamp + timedelta(minutes=1)).isoformat(),
        "reading_update_timestamp": (timestamp + timedelta(seconds=30)).isoformat(),
        "station_id": station, "station_name": "SYNTHETIC TEST STATION",
        "station_device_id": "FAKE_DEVICE",
        "station_location.latitude": "1.35", "station_location.longitude": "103.85",
        "reading_value": str(amount), "reading_unit": "mm",
        "reading_type": "TB1 Rainfall 5 Minute Total F",
        "source_file": f"fixture/year={timestamp.year}/rainfall.csv",
    }
    item.update(overrides)
    return item


class SparkSemanticsTests(unittest.TestCase):
    def test_sample_size_comparison_preserves_nested_anchors(self):
        start = datetime(2020, 1, 1, tzinfo=SGT)
        frame = self.spark.createDataFrame(
            [("FAKE_A001", start + timedelta(minutes=5 * i)) for i in range(1000)],
            "station_id string, timestamp timestamp")
        small = deterministic_sample(frame, .15, 2026)
        large = deterministic_sample(frame, .30, 2026)
        self.assertGreater(large.count(), small.count())
        self.assertEqual(small.exceptAll(large).count(), 0)
        self.assertEqual(small.exceptAll(deterministic_sample(large, .15, 2026)).count(), 0)

    def test_rf_search_preserves_defaults_and_applies_overrides(self):
        default = make_pipeline(["latitude"], 8).getStages()[-1]
        self.assertEqual(default.getMinInstancesPerNode(), 25)
        self.assertEqual(default.getFeatureSubsetStrategy(), "sqrt")
        self.assertEqual(default.getSubsamplingRate(), .8)
        changed = make_pipeline(["latitude"], 10, 80, 128, 2026,
                                min_instances_per_node=50,
                                feature_subset_strategy="0.5").getStages()[-1]
        self.assertEqual(changed.getNumTrees(), 80)
        self.assertEqual(changed.getMaxDepth(), 10)
        self.assertEqual(changed.getMinInstancesPerNode(), 50)
        self.assertEqual(changed.getFeatureSubsetStrategy(), "0.5")

    @classmethod
    def setUpClass(cls):
        builder = (SparkSession.builder.appName("rainfall-semantic-smoke-test")
                   .config("spark.sql.shuffle.partitions", "4")
                   .config("spark.sql.session.timeZone", "Asia/Singapore")
                   .config("spark.sql.ansi.enabled", "false"))
        if os.environ.get("SPARK_LOCAL_MASTER"):
            builder = builder.master(os.environ["SPARK_LOCAL_MASTER"])
        cls.spark = builder.getOrCreate()
        cls.spark.sparkContext.setLogLevel("WARN")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def tearDown(self):
        self.spark.catalog.clearCache()

    def raw(self, rows):
        return self.spark.createDataFrame([tuple(row.get(name) for name in COLUMNS) for row in rows], SCHEMA)

    def timeline(self, count=60, start=None):
        start = start or datetime(2019, 7, 1, tzinfo=SGT)
        return [observation(start + timedelta(minutes=5 * i), float(i)) for i in range(count)]

    def at(self, features, timestamp="2019-07-01T02:00:00+08:00"):
        return features.where(F.col("timestamp") == F.to_timestamp(F.lit(timestamp))).first()

    def test_parser_corruption_marker_is_preserved_and_quarantined(self):
        valid = observation("2019-07-01T00:00:00+08:00", 0.2)
        malformed = observation("2019-07-01T00:05:00+08:00", 0.4,
                                _corrupt_record="broken,csv,row,with,extra,columns")
        cleaned, quarantine, _ = clean(self.raw([valid, malformed]))
        self.assertEqual(cleaned.count(), 1)
        rejected = quarantine.first()
        self.assertIn("malformed_csv", rejected.rejection_reasons)
        self.assertEqual(rejected["_corrupt_record"], malformed["_corrupt_record"])

    def test_invalid_rainfall_quarantined_large_positive_retained(self):
        start = datetime(2019, 7, 1, tzinfo=SGT)
        values = ["-1", "NaN", "Infinity", "-Infinity", "not_a_number", "0", "100"]
        rows = [observation(start + timedelta(minutes=5 * i), value) for i, value in enumerate(values)]
        cleaned, quarantine, _ = clean(self.raw(rows))
        self.assertEqual(sorted(row.rainfall for row in cleaned.collect()), [0.0, 100.0])
        rejected = quarantine.select("rejection_reasons").collect()
        self.assertEqual(len(rejected), 5)
        self.assertTrue(all("invalid_rainfall" in row.rejection_reasons for row in rejected))
        self.assertNotIn("extreme_positive_flag", cleaned.columns)

    def test_distribution_keeps_large_values_and_separates_zeros(self):
        start = datetime(2019, 7, 1, tzinfo=SGT)
        rows = [observation(start + timedelta(minutes=5 * i), value)
                for i, value in enumerate([0, 0, 1, 2, 100])]
        cleaned, _, _ = clean(self.raw(rows))
        root = "/tmp/rainfall-profile-smoke-" + uuid.uuid4().hex
        hadoop_path = self.spark._jvm.org.apache.hadoop.fs.Path(root)
        fs = hadoop_path.getFileSystem(self.spark._jsc.hadoopConfiguration())
        try:
            profile_rainfall(cleaned, root)
            summary = self.spark.read.option("header", True).option("inferSchema", True).csv(root + "/rainfall_distribution").first()
            self.assertEqual(summary.observations, 5)
            self.assertEqual(summary.positive_observations, 3)
            self.assertAlmostEqual(summary.zero_fraction, 0.4)
            self.assertEqual(summary.positive_p50_mm, 2)
            self.assertEqual(summary.max_mm, 100)
            review = self.spark.read.option("header", True).option("inferSchema", True).csv(root + "/rainfall_top100_review")
            largest = review.where(F.col("rainfall") == 100).first()
            self.assertEqual(largest.previous_5min_mm, 2)
            self.assertIsNone(largest.next_5min_mm)
            hist = self.spark.read.option("header", True).option("inferSchema", True).csv(root + "/rainfall_positive_histogram")
            self.assertEqual(hist.agg(F.sum("count")).first()[0], 3)
        finally:
            fs.delete(hadoop_path, True)

    def test_matched_panel_excludes_network_gap_without_inventing_rain(self):
        rows = [(station, year, month,
                 .075 if month == 8 and year == 2018 else
                 .50 if station == "B" and month == 9 and year == 2020 else .99)
                for station in ("A", "B", "MOVED") for year in range(2017, 2025)
                for month in (5, 8, 9)]
        monthly = self.spark.createDataFrame(rows, "station_id string, year int, month int, coverage double")
        stable = self.spark.createDataFrame([("A",), ("B",)], "station_id string")
        pairs, months, panel = _matched_month_panel(monthly, stable, .90)
        self.assertEqual(months, [5, 9])
        self.assertEqual([r.station_id for r in panel.collect()], ["A"])
        self.assertEqual({(r.station_id, r.month) for r in pairs.collect()},
                         {("A", 5), ("A", 9), ("B", 5)})

    def test_exploration_output_schemas_are_unambiguous(self):
        rows = [observation(datetime(year, 1, 1, tzinfo=SGT), 0.2)
                for year in range(2017, 2025)]
        cleaned, _, _ = clean(self.raw(rows))
        schemas = {}

        def inspect_csv(writer, path, *args, **kwargs):
            columns = writer._df.columns
            self.assertEqual(len(columns), len(set(column.casefold() for column in columns)))
            schemas[path.rsplit("/", 1)[-1]] = columns

        # Spark resolves the actual EDA plans; skip file writes for this schema test.
        with patch("pyspark.sql.readwriter.DataFrameWriter.csv", inspect_csv):
            explore(cleaned, "/tmp/rainfall-eda-schema-test")
        for name in ("spatial_month_common", "spatial_year_common"):
            for column in ("station_id", "station_name", "latitude", "longitude"):
                self.assertEqual(schemas[name].count(column), 1)

    def test_near_grid_timestamp_normalizes_and_off_grid_is_rejected(self):
        rows = [observation("2019-07-01T00:04:59+08:00", 0.2),
                observation("2019-07-01T00:06:00+08:00", 0.4)]
        cleaned, quarantine, _ = clean(self.raw(rows))
        result = cleaned.select(F.date_format("timestamp", "yyyy-MM-dd HH:mm:ss").alias("time"), "max_grid_shift_seconds").first()
        self.assertEqual(cleaned.count(), 1)
        self.assertEqual(result.time, "2019-07-01 00:05:00")
        self.assertEqual(result.max_grid_shift_seconds, 1)
        self.assertIn("off_five_minute_grid", quarantine.first().rejection_reasons)

    def test_duplicate_collapse_and_conflicting_key_quarantine(self):
        exact = observation("2019-07-01T00:00:00+08:00", 0.2)
        conflict = observation("2019-07-01T00:05:00+08:00", 0.4)
        rows = [exact, dict(exact), conflict, dict(conflict, reading_value="0.6")]
        cleaned, quarantine, quality = clean(self.raw(rows))
        self.assertEqual(cleaned.count(), 1)
        self.assertAlmostEqual(cleaned.first().rainfall, 0.2)
        self.assertEqual(quarantine.count(), 2)
        self.assertTrue(all("conflicting_station_time_measurement" in row.rejection_reasons
                            for row in quarantine.collect()))
        metrics = {row.metric: row.value for row in quality.collect()}
        self.assertEqual(metrics["raw_rows"], 4)
        self.assertEqual(metrics["valid_rows_after_exact_deduplication"], 3)
        self.assertEqual(metrics["conflicting_station_time_keys"], 1)

    def test_valid_value_with_invalid_sibling_is_quarantined(self):
        valid = observation("2019-07-01T00:00:00+08:00", 0.2)
        cleaned, quarantine, _ = clean(self.raw([valid, dict(valid, reading_value="-1")]))
        self.assertEqual(cleaned.count(), 0)
        reasons = [reason for row in quarantine.select("rejection_reasons").collect()
                   for reason in row.rejection_reasons]
        self.assertIn("invalid_rainfall", reasons)
        self.assertIn("key_has_invalid_source_record", reasons)

    def test_future_sum_is_six_exact_intervals_and_excludes_current(self):
        cleaned, _, _ = clean(self.raw(self.timeline()))
        result = self.at(make_features(cleaned))
        self.assertTrue(result.history_complete)
        self.assertTrue(result.label_complete)
        self.assertEqual(result.y30, sum(range(25, 31)))
        self.assertEqual(result.rain_lag_1, 22.0)  # t-10 minutes, not t.
        self.assertEqual(result.rain_sum_30, sum(range(17, 23)))

    def test_missing_future_interval_never_becomes_zero_label(self):
        rows = self.timeline()
        del rows[27]  # Missing t+15; later measurements must not shift into it.
        cleaned, _, _ = clean(self.raw(rows))
        result = self.at(make_features(cleaned))
        self.assertTrue(result.history_complete)
        self.assertFalse(result.label_complete)
        self.assertIsNone(result.y30)

    def test_delayed_publication_is_not_usable_history(self):
        for metadata_column in ("update_timestamp", "reading_update_timestamp"):
            with self.subTest(metadata_column=metadata_column):
                rows = self.timeline()
                rows[22][metadata_column] = "2019-07-01T02:00:01+08:00"
                cleaned, _, _ = clean(self.raw(rows))
                result = self.at(make_features(cleaned))
                self.assertFalse(result.history_complete)
                self.assertEqual(result.history_n, 11)
                self.assertIsNone(result.rain_lag_1)
                self.assertIsNone(result.rain_sum_30)
                self.spark.catalog.clearCache()

    def test_missing_publication_metadata_is_not_usable_history(self):
        rows = self.timeline()
        rows[22]["reading_update_timestamp"] = None
        cleaned, _, _ = clean(self.raw(rows))
        result = self.at(make_features(cleaned))
        self.assertFalse(result.history_complete)
        self.assertIsNone(result.rain_lag_1)

    def test_future_and_current_changes_cannot_change_features(self):
        rows = self.timeline()
        cleaned, _, _ = clean(self.raw(rows))
        original = self.at(make_features(cleaned))
        for row in rows[24:]:
            row["reading_value"] = "999"
            row["station_location.latitude"] = "1.5"
        cleaned_changed, _, _ = clean(self.raw(rows))
        changed = self.at(make_features(cleaned_changed))
        for feature in NUMERIC_FEATURES:
            with self.subTest(feature=feature):
                self.assertEqual(original[feature], changed[feature])
        self.assertNotEqual(original.y30, changed.y30)

    def test_unused_recent_missing_observation_does_not_hide_valid_history(self):
        rows = self.timeline()
        del rows[23]  # t-5 is outside history; lag_1 begins at t-10.
        cleaned, _, _ = clean(self.raw(rows))
        result = self.at(make_features(cleaned))
        self.assertTrue(result.history_complete)
        self.assertEqual(result.rain_lag_1, 22.0)

    def test_inference_anchor_requires_no_current_or_future_observation(self):
        # At prediction t=02:00 only records through t-10 exist in this fixture.
        cleaned, _, _ = clean(self.raw(self.timeline()[:23]))
        anchors = self.spark.createDataFrame([("FAKE_A001", "2019-07-01T02:00:00+08:00")],
                                              ["station_id", "timestamp"])
        anchors = anchors.withColumn("timestamp", F.to_timestamp("timestamp"))
        features = make_features(cleaned, with_labels=False, anchors=anchors)
        result = features.first()
        self.assertEqual(features.count(), 1)
        self.assertTrue(result.history_complete)
        self.assertEqual(result.rain_lag_1, 22.0)
        self.assertNotIn("y30", features.columns)

    def test_summed_target_rounds_before_strict_threshold_comparison(self):
        rows = self.timeline()
        for row in rows:
            row["reading_value"] = "0.2"
        cleaned, _, _ = clean(self.raw(rows))
        result = self.at(make_features(cleaned))
        self.assertEqual(result.y30, 1.2)
        self.assertFalse(result.y30 > 1.2)

    def test_temporal_split_purges_labels_reaching_next_year(self):
        timestamps = ["2021-12-31 23:25:00", "2021-12-31 23:30:00",
                      "2021-12-31 23:55:00", "2022-01-01 00:00:00"]
        frame = self.spark.createDataFrame([(value,) for value in timestamps], ["timestamp"])
        frame = (frame.withColumn("timestamp", F.to_timestamp("timestamp"))
                 .withColumn("target_end", F.col("timestamp") + F.expr("INTERVAL 30 MINUTES")))
        selected = temporal_split(frame, 2017, 2022).select(F.date_format("timestamp", "HH:mm:ss").alias("time")).collect()
        self.assertEqual([row.time for row in selected], ["23:25:00"])
        self.assertEqual(temporal_split(frame, 2022, 2023).count(), 1)

    def test_spark_survival_handles_absent_tail_classes(self):
        frame = self.spark.createDataFrame([([0.75, 0.25],)], "p array<double>")
        # Forests trained without high classes may produce a shorter vector.
        result = frame.select(survival_expression(calibrated_array(F.col("p"), 1.0),
                              [0., 1., 1., 1., 1., 1., 1.]).alias("probability")).first()
        self.assertAlmostEqual(result.probability, 0.25)

    def test_spark_pipeline_save_reload_preserves_predictions(self):
        training = self.spark.createDataFrame([
            (f"FAKE_{i % 2}", float(i % 7), float(i % 7) + (i % 3) * 0.01,
             float((i % 7) * 2)) for i in range(560)
        ], "station_id string, label_bin double, x double, rain_sum_30 double")
        model = make_pipeline(["x", "rain_sum_30"], depth=2, trees=2,
                              max_bins=32, seed=2026).fit(training)
        # A UUID avoids collisions; Hadoop resolves this on the same filesystem
        # used by Spark (HDFS on Dataproc, local filesystem for local tests).
        root = "/tmp/rainfall-semantic-smoke-" + uuid.uuid4().hex
        path = root + "/pipeline"
        hadoop_path = self.spark._jvm.org.apache.hadoop.fs.Path(root)
        fs = hadoop_path.getFileSystem(self.spark._jsc.hadoopConfiguration())
        try:
            model.write().overwrite().save(path)
            restored = PipelineModel.load(path)
            sample = training.limit(8)
            expected = [row.probability.toArray().tolist()
                        for row in model.transform(sample).select("probability").collect()]
            actual = [row.probability.toArray().tolist()
                      for row in restored.transform(sample).select("probability").collect()]
            self.assertEqual(expected, actual)
            self.assertTrue(all(abs(sum(p) - 1.0) < 1e-10 for p in actual))
        finally:
            fs.delete(hadoop_path, True)

    def test_local_calendar_uses_singapore_day(self):
        # UTC 2019-06-30 16:00 is local 2019-07-01 00:00.
        rows = [observation("2019-06-30T16:00:00+00:00", 0.2)]
        cleaned, _, _ = clean(self.raw(rows))
        result = cleaned.select("year", "month", F.hour("timestamp").alias("hour")).first()
        self.assertEqual((result.year, result.month, result.hour), (2019, 7, 0))


if __name__ == "__main__":
    unittest.main()
