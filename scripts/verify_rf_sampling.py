#!/usr/bin/env python3
"""Verify RF30 evaluation copies preserve the original forest bytes and can score."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def file_hashes(directory):
    hashes = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError('Model artifact must not be a symlink')
        if path.is_file() and not path.name.startswith('.'):
            hashes[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not hashes:
        raise ValueError('Empty model directory: ' + str(directory))
    return hashes


def verify_exact_copy(original, copied):
    before, after = file_hashes(original), file_hashes(copied)
    if before != after:
        raise ValueError('Copied RF weights differ from the saved standard 30% forest')
    return len(before)


def main():
    from pyspark.ml import PipelineModel
    from pyspark.ml.functions import vector_to_array
    from pyspark.sql import SparkSession, functions as F
    from rainfall.model import read_json, calibrated_survival
    from rainfall.probability import survival_weights
    root = ROOT / 'outputs/steps/rf30-evaluation-20261016'
    original = ROOT / 'outputs/steps/rf-sensitivity-20261010'
    reference = ROOT / 'outputs/steps/task2-dual-v2/models'
    spark = (SparkSession.builder.master('local[2]').appName('verify-rf30-evaluation')
             .config('spark.sql.shuffle.partitions', 2).getOrCreate())
    spark.sparkContext.setLogLevel('ERROR')
    checks = []
    thresholds = [0., .2, 1., 2., 3., 5., 7.5, 10., 15., 20.]
    for mode in ('short_term','calendar'):
        base = root / mode
        n = verify_exact_copy(original / mode / 'sample30/pipeline', base / 'pipeline')
        verify_exact_copy(reference / mode / 'stations', base / 'stations')
        verify_exact_copy(reference / mode / 'empirical_support', base / 'empirical_support')
        meta = read_json(spark, str(base / 'metadata'))
        if not meta['test_evaluation_completed'] or meta['weights_retrained']:
            raise ValueError('Expected completed evaluation of unchanged weights')
        pipeline = PipelineModel.load(str(base / 'pipeline'))
        forest = pipeline.stages[-1]
        if int(forest.getNumTrees) != 40 or forest.getMaxDepth() != 8:
            raise ValueError('Wrong reference configuration')
        rows = []
        for station in spark.read.parquet(str(base / 'stations')).orderBy('station_id').limit(3).collect():
            location = station.asDict()
            values = {name:float(location.get(name,0.)) for name in meta['numeric_features']}
            for name in meta['numeric_features']:
                if name.endswith('_cos') or name == 'dry_fraction_60':
                    values[name] = 1.
            values['station_id'] = station.station_id
            rows.append(values)
        scored = pipeline.transform(spark.createDataFrame(rows)).select(vector_to_array('probability').alias('p'))
        supports = read_json(spark, str(base / 'empirical_support'))
        columns = [calibrated_survival(F.col('p'), survival_weights(supports,q), meta['temperature']).alias('q'+str(i))
                   for i,q in enumerate(thresholds)]
        predictions = scored.select('p', *columns).collect()
        for row in predictions:
            if abs(sum(row.p)-1)>1e-10 or any(not 0<=p<=1 for p in row.p):
                raise ValueError('Invalid class probabilities')
            values = [row['q'+str(i)] for i in range(len(thresholds))]
            if any(not 0<=p<=1 for p in values) or any(b>a+1e-12 for a,b in zip(values,values[1:])):
                raise ValueError('Invalid or nonmonotone exceedance probabilities')
        checks.append({'mode':mode, 'pipeline_bytes_unchanged':True, 'pipeline_files_verified':n,
                       'reloaded':True, 'temperature':meta['temperature'],
                       'finite_monotone_query_checks':len(predictions)*len(thresholds)})
    result = {'passed':True, 'scope':'Exact original forest/support/catalogue byte checks and fabricated-feature query checks; not performance estimation.',
              'models':checks}
    (root / 'local_model_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    spark.stop()

if __name__ == '__main__':
    main()
