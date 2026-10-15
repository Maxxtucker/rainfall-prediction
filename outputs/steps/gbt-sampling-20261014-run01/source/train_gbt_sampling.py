#!/usr/bin/env python3
"""Supplementary threshold-conditioned Spark GBT, compared on identical anchors.

2017--2021: fit; 2022: select depth; 2023: select probability temperature;
2024: evaluate once. Reference models and their results are never overwritten.
"""
import argparse
import math
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone

from pyspark import StorageLevel
from pyspark.ml import Pipeline, PipelineModel
from pyspark.ml.classification import GBTClassifier
from pyspark.ml.feature import Imputer, StringIndexer, VectorAssembler
from pyspark.sql import SparkSession, functions as F

from rainfall.model import (
    TEMPERATURES, calibrated_survival, deterministic_sample, evaluation_tables,
    expand_thresholds, macro_brier, predict_climatology, read_json, score_binary,
    score_distribution, temporal_split, threshold_order_diagnostics,
    threshold_predictions, write_csv, write_json,
)


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


def arguments():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference-model", required=True,
                   help="Existing per-mode RF/LR model root; supplies split and feature protocol")
    p.add_argument("--output", required=True, help="Fresh experiment directory")
    p.add_argument("--data", help="Override reference feature root; must be the same dataset")
    p.add_argument("--depths", default="3,5")
    p.add_argument("--iterations", type=int, default=40)
    p.add_argument("--train-fraction", type=float,
                   help="Training fraction; defaults to the reference fraction")
    p.add_argument("--extra-thresholds", default="3,7.5,15")
    p.add_argument("--shuffle-partitions", type=int, default=128)
    return p.parse_args()


def main():
    args = arguments()
    started = time.monotonic()
    if args.train_fraction is not None and not 0 < args.train_fraction <= 1:
        raise ValueError("Training fraction must be in (0, 1]")
    depths = sorted(set(int(x) for x in args.depths.split(",")))
    extras = sorted(set(float(x) for x in args.extra_thresholds.split(",") if x))
    if not depths or any(d < 1 or d > 30 for d in depths) or args.iterations < 1:
        raise ValueError("Use depths 1--30 and positive iterations")
    if any(not math.isfinite(q) or q < 0 for q in extras):
        raise ValueError("Thresholds must be finite and nonnegative")
    spark = (SparkSession.builder.appName("rainfall-supplementary-gbt")
             .config("spark.sql.session.timeZone", "Asia/Singapore")
             .config("spark.sql.shuffle.partitions", args.shuffle_partitions).getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    output, reference = args.output.rstrip("/"), args.reference_model.rstrip("/")
    path = spark._jvm.org.apache.hadoop.fs.Path(output)
    if path.getFileSystem(spark._jsc.hadoopConfiguration()).exists(path):
        raise ValueError("Output exists; choose a fresh experiment directory")
    meta = read_json(spark, reference + "/metadata")
    expected_split = {"train": [2017, 2021], "validation": [2022, 2022],
                      "calibration": [2023, 2023], "test": [2024, 2024]}
    if not meta.get("test_evaluation_completed") or meta["split_years"] != expected_split:
        raise ValueError("Reference must be a completed model with the original year splits")
    data = (args.data or meta["source_data_root"]).rstrip("/")
    prepared = read_json(spark, data + "/metadata")
    features = meta["numeric_features"]
    if (prepared["feature_mode"] != meta["feature_mode"] or
            prepared["numeric_features"] != features or prepared.get("limit_smoke_test_only")):
        raise ValueError("Feature metadata differs from the reference or is smoke-only")
    thresholds = meta["thresholds_evaluated"]
    all_thresholds = sorted(set(thresholds + extras))
    frame = (spark.read.parquet(data + "/features")
             .where(F.col("label_complete") & (F.col("y30") >= 0))
             .withColumn("y30", F.round("y30", 3)))
    if meta["requires_recent_rainfall"]:
        frame = frame.where(F.col("history_complete"))
    if "target_end" not in frame.columns:
        frame = frame.withColumn("target_end", F.col("timestamp") + F.expr("INTERVAL 30 MINUTES"))
    train_full = temporal_split(frame, 2017, 2022)
    full_count = train_full.count()
    if full_count != meta["counts"]["train_full"]:
        raise ValueError("Full training count differs from reference; a reduced cache cannot be used")
    reference_count = deterministic_sample(train_full, meta["train_fraction"], meta["seed"]).count()
    if reference_count != meta["counts"]["train_sample"]:
        raise ValueError("Reference training sample count differs")
    fraction = meta["train_fraction"] if args.train_fraction is None else args.train_fraction
    train = deterministic_sample(train_full, fraction, meta["seed"]).persist(StorageLevel.MEMORY_AND_DISK)
    sample_count = train.count()
    if fraction == 1 and sample_count != full_count:
        raise ValueError("100% training must contain every eligible training row")
    print({"train_fraction": fraction, "train_full": full_count,
           "train_sample": sample_count, "reference_train_sample": reference_count}, flush=True)
    max_bins = max(128, train.select("station_id").distinct().count() + 2)
    expanded = expand_thresholds(train, thresholds).persist(StorageLevel.MEMORY_AND_DISK)

    def cohort(start, name):
        result = deterministic_sample(temporal_split(frame, start, start + 1),
                                      meta["eval_fraction"], meta["seed"])
        if result.count() != meta["counts"][name]:
            raise ValueError(name + " cohort count differs from reference")
        return result

    validation = expand_thresholds(cohort(2022, "validation"), thresholds).persist(StorageLevel.MEMORY_AND_DISK)
    candidates, best, best_score, best_depth = [], None, float("inf"), None
    for depth in depths:
        fit_started = time.monotonic()
        model = gbt_pipeline(features, depth, args.iterations, max_bins, meta["seed"]).fit(expanded)
        score = float(macro_brier(score_binary(model, validation)))
        if not math.isfinite(score):
            raise ValueError("Nonfinite validation score")
        candidates.append({"depth": depth, "validation_macro_brier": score,
                           "elapsed_seconds": time.monotonic() - fit_started})
        model.write().save(output + "/candidates/depth" + str(depth) + "/pipeline")
        write_json(spark, candidates[-1], output + "/candidates/depth" + str(depth) + "/result")
        print(candidates[-1], flush=True)
        if score < best_score:
            best, best_score, best_depth = model, score, depth
    best.write().save(output + "/pipeline")
    write_csv(spark.createDataFrame(candidates), output + "/model_selection")
    train.unpersist(); expanded.unpersist(); validation.unpersist()
    calibration = score_binary(best, expand_thresholds(cohort(2023, "calibration"), thresholds)).persist(StorageLevel.MEMORY_AND_DISK)
    calibration_rows = [{"temperature": t, "macro_brier": float(macro_brier(temperature_predictions(calibration, t)))}
                        for t in TEMPERATURES]
    temperature = min(calibration_rows, key=lambda r: (r["macro_brier"], abs(r["temperature"] - 1)))["temperature"]
    calibration.unpersist()
    write_csv(spark.createDataFrame(calibration_rows), output + "/calibration_selection")
    record = {"created_utc": datetime.now(timezone.utc).isoformat(), "model": "GBTClassifier with threshold feature",
              "reference_model": reference, "source_data_root": data, "feature_mode": meta["feature_mode"],
              "numeric_features": features, "split_years": expected_split, "seed": meta["seed"],
              "train_fraction": fraction, "reference_train_fraction": meta["train_fraction"],
              "counts": {"train_full": full_count, "train_sample": sample_count,
                         **{k: meta["counts"][k] for k in ("validation", "calibration", "test")}},
              "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "eval_fraction": meta["eval_fraction"],
              "training_thresholds": thresholds, "diagnostic_thresholds": extras,
              "depth": best_depth, "iterations": args.iterations, "temperature": temperature,
              "step_size": 0.1, "min_instances_per_node": 25, "subsampling_rate": 0.8,
              "max_bins": max_bins, "spark_version": spark.version,
              "limitations": ["Supplementary experiment designed after original 2024 results were inspected.",
                              "Threshold monotonicity is not constrained; arbitrary-threshold accuracy is not guaranteed.",
                              "A data override must contain the same observations; equal counts alone do not prove identity."],
              "test_evaluation_completed": False}
    write_json(spark, record, output + "/metadata")
    test = cohort(2024, "test").persist(StorageLevel.MEMORY_AND_DISK)
    test_expanded = expand_thresholds(test, all_thresholds)
    predictions = {
        "gbt": temperature_predictions(score_binary(best, test_expanded), temperature),
        "random_forest": threshold_predictions(score_distribution(PipelineModel.load(reference + "/pipeline"), test),
            read_json(spark, reference + "/empirical_support"), all_thresholds, meta["temperature"]),
        "binary_logistic": score_binary(PipelineModel.load(reference + "/binary_pipeline"), test_expanded),
        "climatology": predict_climatology(test, spark.read.parquet(reference + "/climatology"),
            spark.read.parquet(reference + "/global_climatology"), thresholds),
    }
    for name, pred in predictions.items():
        pred = pred.persist(StorageLevel.MEMORY_AND_DISK)
        metrics, reliability = evaluation_tables(pred, "test", name)
        write_csv(metrics, output + "/metrics/" + name)
        write_csv(reliability, output + "/reliability/" + name)
        write_csv(threshold_order_diagnostics(pred), output + "/threshold_order/" + name)
        write_csv(pred.groupBy("threshold", F.to_date("timestamp").alias("date")).agg(
            F.count("*").alias("n"), F.sum(F.pow(F.col("probability") - F.col("label"), 2)).alias("sum_squared_error")),
            output + "/daily_scores/" + name)
        pred.unpersist()
    record["test_evaluation_completed"] = True
    record["elapsed_seconds"] = time.monotonic() - started
    write_json(spark, record, output + "/metadata")
    test.unpersist()
    spark.stop()


if __name__ == "__main__":
    main()

