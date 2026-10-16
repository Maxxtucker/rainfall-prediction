#!/usr/bin/env python3
"""Reload only the new LR30 pipelines and check query compatibility locally."""
import json
import math
from pathlib import Path
from pyspark.ml import PipelineModel
from pyspark.ml.functions import vector_to_array
from pyspark.sql import SparkSession
from rainfall.model import read_json

ROOT = Path(__file__).resolve().parents[1]


def main():
    base = ROOT / 'outputs/steps/lr-sampling-20261015'
    spark = (SparkSession.builder.master('local[2]').appName('verify-lr30')
             .config('spark.sql.shuffle.partitions', 2).getOrCreate())
    spark.sparkContext.setLogLevel('ERROR')
    checks = []
    for mode in ('short_term', 'calendar'):
        root = base / mode
        meta = read_json(spark, str(root / 'metadata'))
        if not meta['test_evaluation_completed'] or meta['train_fraction'] != .3:
            raise ValueError('Expected completed independent LR30 fit')
        model = PipelineModel.load(str(root / 'binary_pipeline'))
        lr = model.stages[-1]
        if lr.getRegParam() != meta['reg_param'] or lr.getMaxIter() != meta['max_iter']:
            raise ValueError('Saved LR parameters differ from metadata')
        if not all(math.isfinite(float(x)) for x in lr.coefficients.toArray()) or not math.isfinite(lr.intercept):
            raise ValueError('Nonfinite coefficients')
        stations = spark.read.parquet(str(root / 'stations')).orderBy('station_id').limit(3).collect()
        records = []
        for station in stations:
            location = station.asDict()
            for q in (0., 1., 3., 20.):
                record = {name: float(location.get(name, 0.)) for name in meta['numeric_features']}
                for name in meta['numeric_features']:
                    if name.endswith('_cos') or name == 'dry_fraction_60':
                        record[name] = 1.
                record.update(station_id=station.station_id, threshold=q)
                records.append(record)
        probabilities = [row.p for row in model.transform(spark.createDataFrame(records))
                         .select(vector_to_array('probability').alias('p')).collect()]
        if any(abs(sum(p)-1)>1e-10 or any(not 0<=x<=1 for x in p) for p in probabilities):
            raise ValueError('Invalid probability from reloaded pipeline')
        mlmeta = json.loads(next((root / 'binary_pipeline/metadata').glob('part-*')).read_text())
        checks.append({'mode': mode, 'reloaded': True, 'spark_version_trained': mlmeta['sparkVersion'],
                       'reg_param': lr.getRegParam(),
                       'num_features': lr.numFeatures, 'query_checks': len(probabilities),
                       'coefficient_and_probability_checks': 'passed'})
    result = {'passed': True, 'scope': 'Local saved-pipeline reload and fabricated-feature query checks; not predictive evaluation.',
              'models': checks}
    (base / 'local_model_verification.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    spark.stop()

if __name__ == '__main__':
    main()
