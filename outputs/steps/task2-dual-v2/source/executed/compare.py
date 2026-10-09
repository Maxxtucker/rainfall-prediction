#!/usr/bin/env python3
"""Compare short-term and calendar RF probabilities on identical 2024 anchors."""
import argparse
from pyspark.sql import SparkSession, functions as F
from pyspark.ml import PipelineModel
from rainfall.model import (read_json, write_json, write_csv, temporal_split,
    deterministic_sample, score_distribution, threshold_predictions, evaluation_tables)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', required=True, help='Dual feature root containing calendar/ and short_term/')
    p.add_argument('--models', required=True, help='Root containing calendar/ and short_term/ trained models')
    p.add_argument('--output', required=True, help='Fresh comparison directory')
    args = p.parse_args()
    spark = (SparkSession.builder.appName('rainfall-dual-comparison')
        .config('spark.sql.session.timeZone', 'Asia/Singapore').getOrCreate())
    path = spark._jvm.org.apache.hadoop.fs.Path(args.output)
    if path.getFileSystem(spark._jsc.hadoopConfiguration()).exists(path):
        raise ValueError('Comparison output exists; choose a fresh run.')
    meta = {mode: read_json(spark, args.models.rstrip('/') + '/' + mode + '/metadata') for mode in ('calendar','short_term')}
    if not all(item.get('test_evaluation_completed') for item in meta.values()):
        raise ValueError('Both models must finish their individual test evaluations first.')
    if meta['calendar']['feature_mode'] != 'calendar_risk_v2' or meta['short_term']['feature_mode'] != 'short_term_v3':
        raise ValueError('Expected a calendar and short-term model pair.')
    for key in ('thresholds_evaluated', 'eval_fraction', 'seed', 'split_years'):
        if meta['calendar'][key] != meta['short_term'][key]:
            raise ValueError('Models must share ' + key)
    frames = {}
    for mode in meta:
        frame = (spark.read.parquet(args.data.rstrip('/') + '/' + mode + '/features')
                 .where(F.col('label_complete')).withColumn('y30',F.round('y30',3)))
        if mode == 'short_term':
            frame = frame.where(F.col('history_complete'))
        frames[mode] = deterministic_sample(temporal_split(frame,2024,2025), meta[mode]['eval_fraction'],meta[mode]['seed'])
    keys = ['station_id','timestamp']
    common = frames['calendar'].select(*keys).join(frames['short_term'].select(*keys),keys).persist()
    counts = {mode: frame.count() for mode,frame in frames.items()}
    counts['common'] = common.count()
    if not counts['common']:
        raise ValueError('No shared test anchors.')
    # Small real feature examples let users verify downloaded models locally.
    # They are audit artifacts only; evaluation below still uses every shared anchor.
    examples = frames['short_term'].join(common,keys,'inner').limit(20).persist()
    examples.write.mode('errorifexists').parquet(args.output + '/example_features')
    metrics, reliability, predictions = [], [], {}
    for mode in meta:
        root = args.models.rstrip('/') + '/' + mode
        frame = frames[mode].join(common,keys,'inner')
        scored = score_distribution(PipelineModel.load(root + '/pipeline'),frame)
        pred = threshold_predictions(scored,read_json(spark,root + '/empirical_support'),
            meta[mode]['thresholds_evaluated'],meta[mode]['temperature']).persist()
        predictions[mode] = pred
        m,r = evaluation_tables(pred,'test_common',mode)
        metrics.append(m); reliability.append(r)
    write_csv(metrics[0].unionByName(metrics[1]),args.output + '/metrics')
    write_csv(reliability[0].unionByName(reliability[1]),args.output + '/reliability')
    join = keys + ['threshold']
    paired = predictions['calendar'].select(*join,'label',F.col('probability').alias('p_calendar')).join(
        predictions['short_term'].select(*join,F.col('label').alias('label_short'),F.col('probability').alias('p_short')),join)
    if paired.where(F.col('label') != F.col('label_short')).limit(1).count():
        raise ValueError('Labels disagree: use the same cleaned source for both feature modes.')
    write_csv(paired.join(examples.select(*keys),keys,'inner'),args.output + '/example_predictions')
    write_csv(paired.groupBy('threshold',F.to_date('timestamp').alias('date')).agg(
        F.count('*').alias('n'),
        F.sum(F.pow(F.col('p_calendar')-F.col('label'),2)).alias('calendar_sum_squared_error'),
        F.sum(F.pow(F.col('p_short')-F.col('label'),2)).alias('short_term_sum_squared_error')),args.output + '/daily_scores')
    write_json(spark, {'counts':counts,'short_term_coverage_of_calendar_test':counts['short_term']/counts['calendar'],
        'comparison':'RF models on identical test anchors; trained on their respective eligible samples',
        'thresholds':meta['calendar']['thresholds_evaluated']},args.output + '/metadata')
    examples.unpersist()
    spark.stop()


if __name__ == '__main__':
    main()
