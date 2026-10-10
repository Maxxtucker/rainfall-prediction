#!/usr/bin/env python3
"""Controlled RF sample-size and one-factor hyperparameter sensitivity on 2022 only.

Checkpoint each candidate; never read calibration/test partitions. Original models
and their training-only empirical supports are reused without modification.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pyspark import StorageLevel
from pyspark.ml import PipelineModel
from pyspark.sql import SparkSession, functions as F
from rainfall.data import NUMERIC_FEATURES, HISTORY_NUMERIC_FEATURES
from rainfall.model import (amount_class, deterministic_sample, temporal_split,
    make_pipeline, read_json, write_json, write_csv, score_distribution,
    threshold_predictions)


def candidate_plan():
    base = dict(depth=8, trees=40, min_instances_per_node=25,
                feature_subset_strategy='sqrt', subsampling_rate=0.8)
    return [dict(name='original15', fraction=0.15, reuse=True, **base),
            dict(name='sample30', fraction=0.30, reuse=False, **base),
            dict(name='depth10', fraction=0.15, reuse=False, **{**base, 'depth': 10}),
            dict(name='trees80', fraction=0.15, reuse=False, **{**base, 'trees': 80}),
            dict(name='leaf50', fraction=0.15, reuse=False, **{**base, 'min_instances_per_node': 50}),
            dict(name='features_half', fraction=0.15, reuse=False,
                 **{**base, 'feature_subset_strategy': '0.5'})]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data', required=True)
    ap.add_argument('--models', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--modes', default='short_term,calendar')
    args = ap.parse_args()
    spark = (SparkSession.builder.appName('Rainfall RF sensitivity: validation only')
             .config('spark.sql.session.timeZone', 'Asia/Singapore')
             .config('spark.sql.shuffle.partitions', '128')
             .config('spark.sql.adaptive.enabled', 'true').getOrCreate())
    spark.sparkContext.setLogLevel('WARN')
    start = time.monotonic()
    def exists(path):
        p = spark._jvm.org.apache.hadoop.fs.Path(path)
        return p.getFileSystem(spark._jsc.hadoopConfiguration()).exists(p)
    summaries = []
    for mode in args.modes.split(','):
        original = args.models.rstrip('/') + '/' + mode
        out = args.output.rstrip('/') + '/' + mode
        metadata = read_json(spark, original + '/metadata')
        supports = read_json(spark, original + '/empirical_support')
        features = HISTORY_NUMERIC_FEATURES if mode == 'short_term' else NUMERIC_FEATURES
        seed = metadata['seed']
        thresholds = metadata['thresholds_evaluated']
        frame = (spark.read.parquet(args.data.rstrip('/') + '/' + mode + '/features')
                 .where((F.col('year') >= 2017) & (F.col('year') <= 2022))
                 .where(F.col('label_complete') & (F.col('y30') >= 0))
                 .withColumn('y30', F.round('y30', 3))
                 .withColumn('label_bin', amount_class()))
        if mode == 'short_term':
            frame = frame.where(F.col('history_complete'))
        if 'target_end' not in frame.columns:
            frame = frame.withColumn('target_end', F.col('timestamp') + F.expr('INTERVAL 30 MINUTES'))
        columns = list(dict.fromkeys(['station_id', 'timestamp', 'target_end', 'month', 'hour',
                                     'y30', 'label_bin'] + list(features)))
        full = temporal_split(frame, 2017, 2022).select(*columns)
        train30 = deterministic_sample(full, 0.30, seed).persist(StorageLevel.MEMORY_AND_DISK)
        train15 = deterministic_sample(train30, 0.15, seed).persist(StorageLevel.MEMORY_AND_DISK)
        validation = temporal_split(frame, 2022, 2023).select(*columns).persist(StorageLevel.MEMORY_AND_DISK)
        counts = {'train15': train15.count(), 'train30': train30.count(), 'validation': validation.count()}
        if counts['train15'] != metadata['counts']['train_sample'] or counts['validation'] != metadata['counts']['validation']:
            raise ValueError('Original sample/split counts do not match: ' + str(counts))
        write_json(spark, {'counts': counts, 'seed': seed, 'plan': candidate_plan(),
            'selection_year': 2022, 'read_years': [2017, 2022], 'test_accessed': False,
            'nested_sampling': True, 'original_model': original,
            'created_utc': datetime.now(timezone.utc).isoformat()}, out + '/protocol')
        plan = candidate_plan()
        for cfg in plan:
            dest = out + '/' + cfg['name']
            if exists(dest + '/result/_SUCCESS'):
                result = read_json(spark, dest + '/result')
                summaries.append(result)
                print('Checkpoint reused: ' + json.dumps(result), flush=True)
                if cfg['name'] == 'features_half':
                    winner = min((r for r in summaries if r['mode'] == mode and r['fraction'] == 0.15),
                                 key=lambda r: r['validation_macro_brier'])
                    if winner['name'] != 'original15':
                        matched = {k: winner[k] for k in ['depth', 'trees', 'min_instances_per_node',
                                   'feature_subset_strategy', 'subsampling_rate']}
                        plan.append(dict(name='selected30', fraction=0.30, reuse=False, **matched))
                continue
            begin = time.monotonic()
            print('Candidate start: ' + json.dumps({'mode': mode, **cfg}), flush=True)
            if cfg['reuse']:
                model = PipelineModel.load(original + '/pipeline')
                fit_seconds = 0.0
            else:
                model = make_pipeline(features, cfg['depth'], cfg['trees'], metadata['max_bins'], seed,
                    cfg['min_instances_per_node'], cfg['feature_subset_strategy'], cfg['subsampling_rate']).fit(
                        train30 if cfg['fraction'] == 0.30 else train15)
                fit_seconds = time.monotonic() - begin
                model.write().overwrite().save(dest + '/pipeline')
            scored = score_distribution(model, validation)
            predictions = threshold_predictions(scored, supports, thresholds, 1.0)
            daily = predictions.groupBy('threshold', F.to_date('timestamp').alias('date')).agg(
                F.count('*').alias('n'), F.sum(F.pow(F.col('probability') - F.col('label'), 2)).alias('sse'),
                F.sum('label').alias('events'), F.sum('probability').alias('sum_probability'))
            write_csv(daily, dest + '/validation_daily')
            by_threshold = (spark.read.option('header', True).option('inferSchema', True).csv(dest + '/validation_daily')
                .groupBy('threshold').agg((F.sum('sse') / F.sum('n')).alias('brier'),
                    F.sum('n').alias('n'), (F.sum('events') / F.sum('n')).alias('event_rate')))
            rows = [r.asDict() for r in by_threshold.orderBy('threshold').collect()]
            result = {'mode': mode, **cfg, 'seed': seed, 'counts': counts,
                'validation_macro_brier': sum(r['brier'] for r in rows) / len(rows),
                'threshold_metrics': rows, 'fit_seconds': round(fit_seconds, 2),
                'elapsed_seconds': round(time.monotonic() - begin, 2), 'test_accessed': False}
            write_json(spark, result, dest + '/result')
            summaries.append(result)
            write_json(spark, summaries, args.output.rstrip('/') + '/results')
            print('Candidate complete: ' + json.dumps(result), flush=True)
            if cfg['name'] == 'features_half':
                mode_rows = [r for r in summaries if r['mode'] == mode and r['fraction'] == 0.15]
                winner = min(mode_rows, key=lambda r: r['validation_macro_brier'])
                if winner['name'] != 'original15':
                    matched = {k: winner[k] for k in ['depth', 'trees', 'min_instances_per_node',
                               'feature_subset_strategy', 'subsampling_rate']}
                    plan.append(dict(name='selected30', fraction=0.30, reuse=False, **matched))
        for cached in [train15, train30, validation]:
            cached.unpersist()
    write_json(spark, {'complete': True, 'elapsed_seconds': round(time.monotonic() - start, 2),
        'candidates': len(summaries), 'test_accessed': False}, args.output.rstrip('/') + '/completion')
    spark.stop()


if __name__ == '__main__':
    main()
