#!/usr/bin/env python3
"""Reload imported selected pipelines and smoke-score fabricated feature rows.

Checks compatibility and finite probabilities, not new predictive performance.
"""
import json
from pathlib import Path
from pyspark.ml import PipelineModel
from pyspark.ml.functions import vector_to_array
from pyspark.sql import SparkSession,functions as F
from rainfall.model import read_json,calibrated_survival
ROOT=Path(__file__).resolve().parents[1]


def main():
    spark=(SparkSession.builder.master('local[2]').appName('verify-teammate-models')
           .config('spark.sql.shuffle.partitions','2').getOrCreate())
    spark.sparkContext.setLogLevel('ERROR');checks=[]
    gbt=ROOT/'outputs/steps/gbt-sampling-20261014-run01'
    full=ROOT/'outputs/steps/task2-full-20261012'
    for mode in ('short_term','calendar'):
        for root,kind in [(gbt/mode/'sample30','gbt'),(gbt/mode/'sample100','gbt'),
                          (full/'models'/mode,'rf'),(full/'models'/mode,'lr')]:
            meta=read_json(spark,str(root/'metadata'))
            catalogue=spark.read.parquet(str(root/'stations')).orderBy('station_id').first().asDict()
            values={name:float(catalogue.get(name,0.0)) for name in meta['numeric_features']}
            values.update(station_id=catalogue['station_id'],threshold=3.0)
            frame=spark.createDataFrame([values])
            model=PipelineModel.load(str(root/('binary_pipeline' if kind=='lr' else 'pipeline')))
            stage=model.stages[-1]
            expected_features=len(meta['numeric_features'])+(2 if kind=='gbt' else 1)
            if kind!='lr' and stage.numFeatures!=expected_features:raise ValueError('Feature dimension mismatch')
            scored=model.transform(frame).select(vector_to_array('probability').alias('p'))
            probabilities=scored.first().p
            if abs(sum(probabilities)-1)>1e-10 or any(not 0<=p<=1 for p in probabilities):raise ValueError('Invalid probability')
            if kind=='gbt':
                if int(stage.getNumTrees)!=meta['iterations'] or stage.getMaxDepth()!=meta['depth']:raise ValueError('GBT parameters differ')
                if stage.numClasses!=2:raise ValueError('GBT must be binary')
                value=scored.select(calibrated_survival(F.col('p'),[0.,1.],meta['temperature']).alias('p')).first().p
                if not 0<=value<=1:raise ValueError('Calibration probability invalid')
            checks.append(dict(mode=mode,kind=kind,path=str(root.relative_to(ROOT)),reloaded=True,smoke_probability=probabilities))
    result={'passed':True,'scope':'Pipeline reload and fabricated-feature smoke predictions; no training or test re-evaluation.', 'models':checks}
    (gbt/'local_model_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    (full/'local_model_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));spark.stop()


if __name__=='__main__':main()
