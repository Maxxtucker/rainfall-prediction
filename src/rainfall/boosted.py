"""Threshold-conditioned binary gradient boosting and probability calibration.

Unlike the distributional RF, q is an input feature. Monotonicity in q is not imposed.
"""
from pyspark.ml import Pipeline
from pyspark.ml.classification import GBTClassifier
from pyspark.ml.feature import Imputer, StringIndexer, VectorAssembler
from pyspark.sql import functions as F
from rainfall.model import calibrated_survival


def gbt_pipeline(features, depth, iterations, max_bins, seed):
    imputed = [name + "_imputed" for name in features]
    return Pipeline(stages=[
        StringIndexer(inputCol="station_id", outputCol="station_index",
                      handleInvalid="keep", stringOrderType="alphabetAsc"),
        Imputer(inputCols=features, outputCols=imputed, strategy="median"),
        VectorAssembler(inputCols=imputed + ["station_index", "threshold"],
                        outputCol="features"),
        GBTClassifier(labelCol="label", featuresCol="features", maxDepth=depth,
                      maxIter=iterations, stepSize=0.1, maxBins=max_bins,
                      minInstancesPerNode=25, subsamplingRate=0.8, seed=seed),
    ])


def temperature_predictions(predictions, temperature):
    p = F.col("probability")
    return predictions.withColumn("probability", calibrated_survival(
        F.array(1.0 - p, p), [0.0, 1.0], temperature))
