#!/usr/bin/env python3
"""Calibrate and evaluate existing reference-configuration 30% forests; never fit."""
import argparse
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from pyspark import StorageLevel
from pyspark.ml import PipelineModel
from pyspark.sql import SparkSession, functions as F
from rainfall.model import (choose_cutoffs, evaluation_tables, read_json,
    score_distribution, select_temperature, temporal_split, threshold_predictions,
    write_csv, write_json)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference-root', required=True)
    p.add_argument('--sensitivity-root', required=True)
    p.add_argument('--data-root', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    spark = (SparkSession.builder.appName('rainfall-rf30-calibrate-test')
        .config('spark.sql.session.timeZone', 'Asia/Singapore')
        .config('spark.sql.shuffle.partitions', 128)
        .config('spark.sql.adaptive.enabled', 'true').getOrCreate())
    spark.sparkContext.setLogLevel('WARN')
    conf = spark._jsc.hadoopConfiguration()
    def path(value):
        return spark._jvm.org.apache.hadoop.fs.Path(value)
    def copy_directory(source, dest):
        src, dst = path(source), path(dest)
        if not spark._jvm.org.apache.hadoop.fs.FileUtil.copy(
                src.getFileSystem(conf), src, dst.getFileSystem(conf), dst, False, False, conf):
            raise RuntimeError('Copy failed: ' + source)
    output = args.output.rstrip('/')
    dst = path(output)
    if dst.getFileSystem(conf).exists(dst):
        raise ValueError('Choose a fresh output root')
    for mode in ('short_term', 'calendar'):
        started = time.monotonic()
        root = output + '/' + mode
        reference = args.reference_root.rstrip('/') + '/' + mode
        saved = args.sensitivity_root.rstrip('/') + '/' + mode + '/sample30'
        data = args.data_root.rstrip('/') + '/' + mode
        ref = read_json(spark, reference + '/metadata')
        result = read_json(spark, saved + '/result')
        prepared = read_json(spark, data + '/metadata')
        expected_years = {'train':[2017,2021], 'validation':[2022,2022],
                          'calibration':[2023,2023], 'test':[2024,2024]}
        if (not ref['test_evaluation_completed'] or ref['split_years'] != expected_years
                or ref['eval_fraction'] != 1 or ref['source_data_root'].rstrip('/') != data):
            raise ValueError('Reference evaluation/data protocol differs')
        if (prepared['numeric_features'] != ref['numeric_features']
                or prepared['feature_mode'] != ref['feature_mode'] or prepared.get('limit_smoke_test_only')):
            raise ValueError('Prepared feature protocol differs')
        if (result['fraction'] != .3 or result['name'] != 'sample30' or result['mode'] != mode
                or result['seed'] != ref['seed'] or result['reuse']
                or result['counts']['train15'] != ref['counts']['train_sample']
                or result['counts']['validation'] != ref['counts']['validation']):
            raise ValueError('Not the matching reference-configuration 30% forest')
        pipeline = PipelineModel.load(saved + '/pipeline')
        stage = pipeline.stages[-1]
        if (stage.__class__.__name__ != 'RandomForestClassificationModel'
                or stage.numClasses != 7 or stage.numFeatures != len(ref['numeric_features']) + 1):
            raise ValueError('Not the matching seven-class RF feature pipeline')
        actual = {'depth':stage.getMaxDepth(), 'trees':int(stage.getNumTrees),
                  'max_bins':stage.getMaxBins(), 'min_instances_per_node':stage.getMinInstancesPerNode(),
                  'feature_subset_strategy':stage.getFeatureSubsetStrategy(),
                  'subsampling_rate':stage.getSubsamplingRate(), 'seed':stage.getSeed()}
        expected = {'depth':ref['depth'], 'trees':ref['num_trees'], 'max_bins':ref['max_bins'],
                    'min_instances_per_node':25, 'feature_subset_strategy':'sqrt',
                    'subsampling_rate':.8, 'seed':ref['seed']}
        if actual != expected:
            raise ValueError('30% settings differ from reference: ' + str(actual))
        if any(result[key] != actual[key] for key in actual if key != 'max_bins'):
            raise ValueError('Saved pipeline differs from historical training record')
        supports = read_json(spark, reference + '/empirical_support')
        if sum(item['n'] for item in supports) != ref['counts']['train_full']:
            raise ValueError('Empirical support is not from full original training population')
        # Copy exact saved bytes; no model fit or model reserialization is used.
        copy_directory(saved + '/pipeline', root + '/pipeline')
        copy_directory(reference + '/empirical_support', root + '/empirical_support')
        copy_directory(reference + '/stations', root + '/stations')
        copy_directory(saved + '/result', root + '/training_result')
        frame = (spark.read.parquet(data + '/features')
                 .where(F.col('label_complete') & (F.col('y30') >= 0))
                 .withColumn('y30', F.round('y30', 3)))
        if ref['requires_recent_rainfall']:
            frame = frame.where(F.col('history_complete'))
        if 'target_end' not in frame.columns:
            frame = frame.withColumn('target_end', F.col('timestamp') + F.expr('INTERVAL 30 MINUTES'))
        counts = {'train_full':ref['counts']['train_full'], 'train_sample':result['counts']['train30']}
        def cohort(year, name):
            data_frame = temporal_split(frame, year, year + 1)
            counts[name] = data_frame.count()
            if counts[name] != ref['counts'][name]:
                raise ValueError(name + ' population differs from reference')
            print({'mode':mode, 'phase':name, 'n':counts[name]}, flush=True)
            return data_frame
        thresholds = ref['thresholds_evaluated']
        all_thresholds = sorted(set(thresholds + [3.,7.5,15.]))
        calibration = score_distribution(pipeline, cohort(2023, 'calibration')).persist(StorageLevel.MEMORY_AND_DISK)
        temperature, calibration_rows = select_temperature(calibration, supports, thresholds)
        write_csv(spark.createDataFrame(calibration_rows), root + '/metrics/calibration_selection')
        calibration.unpersist()
        print({'mode':mode, 'phase':'temperature_selected', 'temperature':temperature}, flush=True)
        validation = threshold_predictions(score_distribution(pipeline, cohort(2022, 'validation')),
                                           supports, thresholds, temperature).persist(StorageLevel.MEMORY_AND_DISK)
        cutoffs = choose_cutoffs(validation)
        val_metrics = validation.groupBy('threshold').agg(
            F.count('*').alias('n'), F.avg('label').alias('prevalence'),
            F.avg(F.pow(F.col('probability')-F.col('label'),2)).alias('brier'))
        write_csv(val_metrics, root + '/metrics/validation_probability_metrics')
        validation.unpersist()
        metadata = {**{k:ref[k] for k in ('feature_mode','numeric_features','seed','eval_fraction',
                    'requires_recent_rainfall','latency_minutes','split_years','amount_edges',
                    'rainfall_rounding_mm','train_max_y30','categorical_features')},
            **{k:v for k,v in actual.items() if k not in ('trees','seed')}, 'num_trees':actual['trees'],
            'model':'RandomForestClassifier + training empirical within-bin survival + temperature calibration',
            'train_fraction':.3, 'temperature':temperature, 'counts':counts,
            'thresholds_evaluated':thresholds, 'diagnostic_thresholds':[3.,7.5,15.],
            'source_data_root':data, 'source_forest':saved, 'reference_model':reference,
            'supported_predictors':['random_forest'], 'cutoffs_random_forest':cutoffs,
            'weights_retrained':False, 'calibration_completed':True, 'test_evaluation_completed':False,
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'created_utc':datetime.now(timezone.utc).isoformat(), 'spark_version':spark.version,
            'experiment_role':'Completes RF 30% in common 2024 model/fraction grid; existing weights are unchanged; 2024 is reused.'}
        write_json(spark, metadata, root + '/metadata_in_progress')
        test = cohort(2024, 'test')
        scored = score_distribution(pipeline, test).persist(StorageLevel.MEMORY_AND_DISK)
        predictions = threshold_predictions(scored, supports, all_thresholds, temperature).persist(StorageLevel.MEMORY_AND_DISK)
        metrics, reliability = evaluation_tables(predictions, 'test', 'random_forest', cutoffs)
        write_csv(metrics, root + '/metrics/test_metrics')
        write_csv(reliability, root + '/metrics/reliability')
        daily = predictions.groupBy('threshold', F.to_date('timestamp').alias('date')).agg(
            F.count('*').alias('n'), F.sum(F.pow(F.col('probability')-F.col('label'),2)).alias('sum_squared_error'))
        write_csv(daily, root + '/metrics/daily_scores')
        predictions.unpersist(); scored.unpersist()
        metadata.update(test_evaluation_completed=True, elapsed_seconds=round(time.monotonic()-started,2))
        write_json(spark, metadata, root + '/metadata')
        print({'mode':mode, 'completed':True, 'elapsed_seconds':metadata['elapsed_seconds']}, flush=True)
        spark.catalog.clearCache()
    write_json(spark, {'complete':True, 'weights_retrained':False}, output + '/completion')
    spark.stop()

if __name__ == '__main__':
    main()
