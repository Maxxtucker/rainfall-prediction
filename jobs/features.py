#!/usr/bin/env python3
"""Task 2 only: calendar features and exact 30-minute labels from saved clean data."""
import argparse
from pyspark.sql import SparkSession, functions as F
from rainfall.data import make_calendar_samples, make_features, NUMERIC_FEATURES, HISTORY_NUMERIC_FEATURES, FEATURE_MODE
from rainfall.model import write_json, write_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clean', required=True)
    parser.add_argument('--output', required=True, help='Fresh output root')
    parser.add_argument('--shuffle-partitions', type=int, default=128)
    parser.add_argument('--mode', choices=['calendar', 'short_term', 'both'], default='both')
    parser.add_argument('--latency-minutes', type=int, default=10)
    args = parser.parse_args()
    spark = (SparkSession.builder.appName('rainfall-calendar-features')
        .config('spark.sql.session.timeZone', 'Asia/Singapore')
        .config('spark.sql.shuffle.partitions', args.shuffle_partitions).getOrCreate())
    root = args.output.rstrip('/')
    fs = spark._jvm.org.apache.hadoop.fs.Path(root).getFileSystem(spark._jsc.hadoopConfiguration())
    if fs.exists(spark._jvm.org.apache.hadoop.fs.Path(root)):
        raise ValueError('Output exists; choose a fresh run name.')
    clean = spark.read.parquet(args.clean)
    modes = ['calendar', 'short_term'] if args.mode == 'both' else [args.mode]
    for mode in modes:
        target = root + '/' + mode
        history = mode == 'short_term'
        frame = make_features(clean, latency_minutes=args.latency_minutes) if history else make_calendar_samples(clean)
        names = HISTORY_NUMERIC_FEATURES if history else NUMERIC_FEATURES
        frame.repartition(args.shuffle_partitions, 'year', 'month').write.partitionBy('year', 'month').parquet(target + '/features')
        saved = spark.read.parquet(target + '/features')
        eligible = F.col('label_complete') & (F.col('history_complete') if history else F.lit(True))
        write_csv(saved.groupBy('year').agg(F.count('*').alias('candidate_predictions'),
            F.sum(F.col('label_complete').cast('long')).alias('complete_labels'),
            F.sum(eligible.cast('long')).alias('eligible_labeled_predictions')), target + '/audit/sample_counts')
        write_json(spark, {'feature_mode': 'short_term_v3' if history else FEATURE_MODE,
            'numeric_features': names, 'clean_path': args.clean,
            'target_offsets_minutes': [5,10,15,20,25,30],
            'latency_minutes': args.latency_minutes if history else None,
            'requires_recent_rainfall': history, 'spark_version': spark.version}, target + '/metadata')
    spark.stop()


if __name__ == '__main__':
    main()
