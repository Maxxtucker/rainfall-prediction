#!/usr/bin/env python3
"""Reload every new sensitivity forest and verify its recorded configuration."""
import argparse
import json
from pathlib import Path
from pyspark.ml import PipelineModel
from pyspark.sql import SparkSession
from rainfall.model import read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    args = parser.parse_args()
    root = args.results.resolve()
    spark = SparkSession.builder.master('local[2]').appName('verify-rf-sensitivity').getOrCreate()
    spark.sparkContext.setLogLevel('WARN')
    records = read_json(spark, str(root / 'results'))
    checks = []
    for result in records:
        if result['reuse']:
            continue
        model_root = root / result['mode'] / result['name']
        metadata = read_json(spark, str(model_root / 'metadata'))
        forest = PipelineModel.load(str(model_root / 'pipeline')).stages[-1]
        actual = dict(trees=int(forest.getNumTrees), depth=forest.getMaxDepth(),
                      min_instances_per_node=forest.getMinInstancesPerNode(),
                      feature_subset_strategy=forest.getFeatureSubsetStrategy(),
                      subsampling_rate=forest.getSubsamplingRate(), seed=forest.getSeed())
        expected = {key: result[key] for key in actual}
        if actual != expected:
            raise ValueError((model_root, actual, expected))
        if forest.numClasses != 7 or forest.numFeatures != len(metadata['numeric_features']) + 1:
            raise ValueError('Wrong class/feature schema: ' + str(model_root))
        if metadata['test_evaluation_completed'] or metadata['temperature'] != 1:
            raise ValueError('Incorrect calibration/test claims')
        supports = read_json(spark, str(model_root / 'empirical_support'))
        if sum(item['n'] for item in supports) != metadata['counts']['train_full']:
            raise ValueError('Empirical supports do not reconcile with full training population')
        checks.append({'mode': result['mode'], 'candidate': result['name'], 'pipeline_reloaded': True,
                       'parameters': actual, 'train_sample': metadata['counts']['train_sample']})
    report = {'passed': True, 'models': checks, 'test_accessed': False}
    (root / 'local_model_verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    spark.stop()


if __name__ == '__main__':
    main()
