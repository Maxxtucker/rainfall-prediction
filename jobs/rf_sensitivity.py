#!/usr/bin/env python3
"""Controlled RF sample-size and one-factor hyperparameter sensitivity on 2022 only.

Persist each candidate for audit; never read calibration/test partitions. Every
invocation requires a fresh output path: checkpoint resume is not supported.
Original models and their training-only empirical supports are reused unchanged.
"""
import argparse
import json
import time
from datetime import datetime, timezone


def parse_modes(value):
    """Reject duplicate/unknown modes before any output can be written."""
    modes = tuple(item.strip() for item in value.split(','))
    if (not modes or len(set(modes)) != len(modes)
            or any(mode not in {'short_term', 'calendar'} for mode in modes)):
        raise argparse.ArgumentTypeError(
            'Use short_term, calendar, or short_term,calendar without duplicates.')
    return modes


def claim_new_output(output, exists, create_marker):
    """Fail closed on old runs and atomically reserve a new output path.

    Incomplete and legacy runs are deliberately not resumed: their checkpoints
    do not establish the identity of the current data, source and model inputs.
    create_marker must create without overwrite and propagate any access error.
    """
    if exists(output):
        raise FileExistsError(
            f'Output already exists: {output}. Resume is not supported; '
            'choose a new output path/run name and preserve the existing run.')
    create_marker(output.rstrip('/') + '/_RUN_CREATED')


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
    ap.add_argument('--output', required=True,
                    help='Fresh output path; existing or interrupted runs cannot be resumed.')
    ap.add_argument('--modes', type=parse_modes, default='short_term,calendar')
    args = ap.parse_args()
    # Keep command-line validation and safety helpers usable without Spark.
    from pyspark import StorageLevel
    from pyspark.ml import PipelineModel
    from pyspark.sql import SparkSession, functions as F
    from rainfall.data import NUMERIC_FEATURES, HISTORY_NUMERIC_FEATURES
    from rainfall.model import (amount_class, deterministic_sample, temporal_split,
        make_pipeline, read_json, write_json, write_csv, score_distribution,
        threshold_predictions)

    spark = (SparkSession.builder.appName('Rainfall RF sensitivity: validation only')
             .config('spark.sql.session.timeZone', 'Asia/Singapore')
             .config('spark.sql.shuffle.partitions', '128')
             .config('spark.sql.adaptive.enabled', 'true').getOrCreate())
    spark.sparkContext.setLogLevel('WARN')
    start = time.monotonic()
    def exists(path):
        p = spark._jvm.org.apache.hadoop.fs.Path(path)
        return p.getFileSystem(spark._jsc.hadoopConfiguration()).exists(p)

    def create_marker(path):
        p = spark._jvm.org.apache.hadoop.fs.Path(path)
        # overwrite=False also rejects a competing invocation of this new run.
        stream = p.getFileSystem(spark._jsc.hadoopConfiguration()).create(p, False)
        stream.close()

    claim_new_output(args.output, exists, create_marker)
    summaries = []
    for mode in args.modes:
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
            'data_path': args.data.rstrip('/') + '/' + mode + '/features',
            'resume_supported': False,
            'created_utc': datetime.now(timezone.utc).isoformat()}, out + '/protocol')
        plan = candidate_plan()
        for cfg in plan:
            dest = out + '/' + cfg['name']
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
                model.write().save(dest + '/pipeline')
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
    # Completion always follows a freshly assembled aggregate, never a stale
    # document left behind by an earlier invocation.
    write_json(spark, summaries, args.output.rstrip('/') + '/results')
    write_json(spark, {'complete': True, 'elapsed_seconds': round(time.monotonic() - start, 2),
        'candidates': len(summaries), 'test_accessed': False}, args.output.rstrip('/') + '/completion')
    spark.stop()


if __name__ == '__main__':
    main()
