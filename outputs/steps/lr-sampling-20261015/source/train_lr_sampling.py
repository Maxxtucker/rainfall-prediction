#!/usr/bin/env python3
"""Fit supplementary 30% LR models separately from existing RF/GBT fits."""
import argparse
import hashlib
import math
import time
from pathlib import Path
from datetime import datetime, timezone
from pyspark import StorageLevel
from pyspark.ml import PipelineModel
from pyspark.sql import SparkSession, functions as F
from rainfall.model import (binary_pipeline, choose_cutoffs, deterministic_sample,
    evaluation_tables, expand_thresholds, macro_brier, read_json, score_binary,
    temporal_split, threshold_order_diagnostics, write_csv, write_json)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference-root', required=True)
    p.add_argument('--data-root', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--modes', default='short_term,calendar')
    p.add_argument('--train-fraction', type=float, default=.3)
    args = p.parse_args()
    if not 0 < args.train_fraction <= 1:
        raise ValueError('Training fraction must be in (0,1]')
    modes = args.modes.split(',')
    if len(set(modes)) != len(modes) or any(m not in ('short_term', 'calendar') for m in modes):
        raise ValueError('Use distinct short_term/calendar modes')
    spark = (SparkSession.builder.appName('rainfall-lr-sampling')
        .config('spark.sql.session.timeZone', 'Asia/Singapore')
        .config('spark.sql.shuffle.partitions', 128)
        .config('spark.sql.adaptive.enabled', 'true').getOrCreate())
    spark.sparkContext.setLogLevel('WARN')
    output = args.output.rstrip('/')
    path = spark._jvm.org.apache.hadoop.fs.Path(output)
    if path.getFileSystem(spark._jsc.hadoopConfiguration()).exists(path):
        raise ValueError('Choose a fresh output root')
    for mode in modes:
        started = time.monotonic()
        root = output + '/' + mode
        reference = args.reference_root.rstrip('/') + '/' + mode
        data = args.data_root.rstrip('/') + '/' + mode
        meta = read_json(spark, reference + '/metadata')
        prepared = read_json(spark, data + '/metadata')
        expected = {'train': [2017,2021], 'validation': [2022,2022],
                    'calibration': [2023,2023], 'test': [2024,2024]}
        if not meta['test_evaluation_completed'] or meta['split_years'] != expected or meta['eval_fraction'] != 1:
            raise ValueError('Expected completed full-evaluation reference protocol')
        if prepared['numeric_features'] != meta['numeric_features'] or prepared['feature_mode'] != meta['feature_mode'] or prepared.get('limit_smoke_test_only'):
            raise ValueError('Prepared feature protocol differs')
        q = meta['thresholds_evaluated']
        all_q = sorted(set(q + [3., 7.5, 15.]))
        frame = (spark.read.parquet(data + '/features')
            .where(F.col('label_complete') & (F.col('y30') >= 0))
            .withColumn('y30', F.round('y30', 3)))
        if meta['requires_recent_rainfall']:
            frame = frame.where(F.col('history_complete'))
        if 'target_end' not in frame.columns:
            frame = frame.withColumn('target_end', F.col('timestamp') + F.expr('INTERVAL 30 MINUTES'))
        full = temporal_split(frame, 2017, 2022)
        if full.count() != meta['counts']['train_full']:
            raise ValueError('Full training population differs')
        train = deterministic_sample(full, args.train_fraction, meta['seed']).persist(StorageLevel.MEMORY_AND_DISK)
        counts = {'train_full': meta['counts']['train_full'], 'train_sample': train.count()}
        reference_n = deterministic_sample(full, meta['train_fraction'], meta['seed']).count()
        if reference_n != meta['counts']['train_sample']:
            raise ValueError('Reference training sample differs')
        def cohort(year, name):
            result = temporal_split(frame, year, year + 1)
            counts[name] = result.count()
            if counts[name] != meta['counts'][name]:
                raise ValueError(name + ' population differs')
            return result
        validation = expand_thresholds(cohort(2022, 'validation'), q).persist(StorageLevel.MEMORY_AND_DISK)
        expanded = expand_thresholds(train, q).persist(StorageLevel.MEMORY_AND_DISK)
        print({'mode': mode, 'counts': counts}, flush=True)
        candidates, best, best_score, selected_reg = [], None, float('inf'), None
        for reg in (.01, .1):
            model = binary_pipeline(meta['numeric_features'], reg).fit(expanded)
            score = float(macro_brier(score_binary(model, validation)))
            if not math.isfinite(score):
                raise ValueError('Nonfinite validation score')
            lr = model.stages[-1]
            record = {'reg_param': reg, 'validation_macro_brier': score,
                      'iterations': int(lr.summary.totalIterations),
                      'objective_history': [float(x) for x in lr.summary.objectiveHistory]}
            candidates.append(record)
            model.write().save(root + '/candidates/reg_' + str(reg) + '/binary_pipeline')
            write_json(spark, record, root + '/candidates/reg_' + str(reg) + '/result')
            print({'mode': mode, **record}, flush=True)
            if score < best_score:
                best, best_score, selected_reg = model, score, reg
        best.write().save(root + '/binary_pipeline')
        expanded.unpersist(); train.unpersist()
        validation_predictions = score_binary(best, validation).persist(StorageLevel.MEMORY_AND_DISK)
        cutoffs = choose_cutoffs(validation_predictions)
        vm, vr = evaluation_tables(validation_predictions, 'validation', 'binary_logistic', cutoffs)
        write_csv(vm, root + '/metrics/validation_metrics')
        write_csv(vr, root + '/metrics/validation_reliability')
        validation_predictions.unpersist(); validation.unpersist()
        spark.read.parquet(reference + '/stations').write.parquet(root + '/stations')
        metadata = {**{k: meta[k] for k in ('feature_mode','numeric_features','seed','eval_fraction',
                      'requires_recent_rainfall','latency_minutes','split_years')},
            'model': 'LogisticRegression; threshold feature; uncalibrated',
            'supported_predictors': ['binary_logistic'], 'train_fraction': args.train_fraction,
            'source_data_root': data, 'reference_model': reference, 'thresholds_evaluated': q,
            'diagnostic_thresholds': [3.,7.5,15.], 'reg_param': selected_reg,
            'max_iter': 100, 'temperature': 1., 'counts': counts,
            'cutoffs_binary': cutoffs, 'candidates': candidates,
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'test_evaluation_completed': False,
            'experiment_role': 'Separate LR-only 30% follow-up after original 2024 evaluation; no new independent holdout'}
        write_json(spark, metadata, root + '/metadata_in_progress')
        test = cohort(2024, 'test')
        predictions = score_binary(best, expand_thresholds(test, all_q)).persist(StorageLevel.MEMORY_AND_DISK)
        metrics, reliability = evaluation_tables(predictions, 'test', 'binary_logistic', cutoffs)
        write_csv(metrics, root + '/metrics/test_metrics')
        write_csv(reliability, root + '/metrics/reliability')
        daily = predictions.groupBy('threshold', F.to_date('timestamp').alias('date')).agg(
            F.count('*').alias('n'), F.sum(F.pow(F.col('probability')-F.col('label'),2)).alias('sum_squared_error'))
        write_csv(daily, root + '/metrics/daily_scores')
        write_csv(threshold_order_diagnostics(predictions), root + '/metrics/threshold_order')
        predictions.unpersist()
        # Reopen the saved artifact and verify its numeric outputs on test rows.
        loaded = PipelineModel.load(root + '/binary_pipeline')
        probe = score_binary(loaded, expand_thresholds(test.limit(100), q))
        invalid = probe.where(F.col('probability').isNull() | F.isnan('probability') |
            (F.col('probability') < 0) | (F.col('probability') > 1)).count()
        if invalid:
            raise ValueError('Reloaded pipeline produced invalid probabilities')
        metadata.update(test_evaluation_completed=True, elapsed_seconds=round(time.monotonic()-started,2),
                        saved_pipeline_reload_verified=True)
        write_json(spark, metadata, root + '/metadata')
        print({'mode': mode, 'completed': True, 'elapsed_seconds': metadata['elapsed_seconds']}, flush=True)
        spark.catalog.clearCache()
    spark.stop()

if __name__ == '__main__':
    main()
