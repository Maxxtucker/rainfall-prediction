#!/usr/bin/env python3
"""Reload downloaded real models and reconcile their predictions with cloud audit examples."""
import argparse
import json
from pathlib import Path
from pyspark.ml import PipelineModel
from pyspark.sql import SparkSession, functions as F
from rainfall.model import (read_json, score_distribution, threshold_predictions,
                            expand_thresholds, score_binary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', required=True, type=Path)
    args = parser.parse_args()
    root = args.results.resolve()
    spark = (SparkSession.builder.master('local[2]').appName('verify-downloaded-task2-models')
             .config('spark.sql.session.timeZone', 'Asia/Singapore')
             .config('spark.sql.shuffle.partitions', '2').getOrCreate())
    spark.sparkContext.setLogLevel('WARN')
    examples = spark.read.parquet(str(root/'comparison'/'example_features'))
    expected = (spark.read.option('header', True).option('inferSchema', True)
                .csv(str(root/'comparison'/'example_predictions')))
    keys = ['station_id', 'timestamp', 'threshold']
    report = {}
    for mode, column in [('calendar', 'p_calendar'), ('short_term', 'p_short')]:
        model = str(root/'models'/mode)
        meta = read_json(spark, model+'/metadata')
        if not meta.get('test_evaluation_completed'):
            raise ValueError(mode+' did not complete evaluation')
        probabilities = threshold_predictions(
            score_distribution(PipelineModel.load(model+'/pipeline'), examples),
            read_json(spark, model+'/empirical_support'),
            meta['thresholds_evaluated'], meta['temperature'])
        joined = probabilities.join(expected.select(*keys, column), keys)
        check = joined.agg(F.count('*').alias('n'),
            F.max(F.abs(F.col('probability')-F.col(column))).alias('max_absolute_error')).first()
        wanted = examples.count()*len(meta['thresholds_evaluated'])
        if check.n != wanted or check.max_absolute_error is None or check.max_absolute_error > 1e-9:
            raise AssertionError((mode, check, wanted))
        baseline = score_binary(PipelineModel.load(model+'/binary_pipeline'),
                                expand_thresholds(examples, meta['thresholds_evaluated']))
        invalid = baseline.where(F.col('probability').isNull() | F.isnan('probability') |
            (F.col('probability') < 0) | (F.col('probability') > 1)).count()
        if invalid:
            raise AssertionError(mode+' binary model produced invalid probabilities')
        report[mode] = {'matched_rf_predictions': check.n,
                        'max_absolute_error': check.max_absolute_error,
                        'binary_pipeline_reloaded': True}
    report['passed'] = True
    (root/'local_model_verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    spark.stop()


if __name__ == '__main__':
    main()
