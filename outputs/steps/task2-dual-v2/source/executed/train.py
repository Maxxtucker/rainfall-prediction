#!/usr/bin/env python3
"""Train/select/calibrate/evaluate a Spark distributional rainfall model."""
import argparse
from datetime import datetime, timezone
import json
import math
import platform
import sys
import time

from pyspark import StorageLevel
from pyspark.sql import SparkSession, functions as F

from rainfall.data import NUMERIC_FEATURES, HISTORY_NUMERIC_FEATURES, FEATURE_MODE
from rainfall.model import (
    expand_thresholds, binary_pipeline, score_binary, threshold_order_diagnostics,
    DEFAULT_THRESHOLDS, AMOUNT_EDGES, amount_class, build_empirical_support,
    choose_cutoffs, deterministic_sample, evaluation_tables, fit_climatology,
    macro_brier, make_pipeline, predict_climatology, score_distribution,
    read_json, select_temperature, subgroup_table, temporal_split, threshold_predictions, write_csv, write_json,
)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="prepare.py output root (features is appended)")
    parser.add_argument("--output", required=True, help="New model/results root, e.g. gs://BUCKET/run/model")
    parser.add_argument("--train-fraction", type=float, default=0.15)
    parser.add_argument("--eval-fraction", type=float, default=1.0, help="Label-independent sample; final run should use 1")
    parser.add_argument("--depths", default="5,8")
    parser.add_argument("--trees", type=int, default=40)
    parser.add_argument("--thresholds", default=",".join(str(t) for t in DEFAULT_THRESHOLDS))
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--shuffle-partitions", type=int, default=192)
    return parser.parse_args()


def union_tables(tables):
    result = tables[0]
    for table in tables[1:]:
        result = result.unionByName(table)
    return result


def main():
    args = arguments()
    start = time.monotonic()
    spark = (SparkSession.builder.appName("Singapore rainfall - train and evaluate")
             .config("spark.sql.session.timeZone", "Asia/Singapore")
             .config("spark.sql.shuffle.partitions", args.shuffle_partitions)
             .config("spark.sql.adaptive.enabled", "true").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    output = args.output.rstrip("/")
    path = spark._jvm.org.apache.hadoop.fs.Path(output)
    if path.getFileSystem(spark._jsc.hadoopConfiguration()).exists(path):
        raise ValueError("Model output exists; choose a fresh run name.")
    thresholds = sorted(set(float(v) for v in args.thresholds.split(",")))
    depths = [int(v) for v in args.depths.split(",")]
    if not thresholds or not depths:
        raise ValueError("At least one threshold and model depth is required")
    if any(not math.isfinite(value) or value < 0 for value in thresholds):
        raise ValueError("All training/evaluation thresholds must be finite and nonnegative")
    prepare_metadata = read_json(spark, args.data.rstrip("/") + "/metadata")
    feature_mode = prepare_metadata.get("feature_mode")
    if feature_mode not in (FEATURE_MODE, "short_term_v3"):
        raise ValueError("Rebuild Task 2 features with jobs/features.py before training.")
    history_model = feature_mode == "short_term_v3"
    feature_names = HISTORY_NUMERIC_FEATURES if history_model else NUMERIC_FEATURES
    if prepare_metadata.get("numeric_features") != list(feature_names):
        raise ValueError("Prepared feature schema does not match selected model mode.")
    frame = (spark.read.parquet(args.data.rstrip("/") + "/features")
             .where(F.col("label_complete") & (F.col("y30") >= 0))
             .withColumn("y30", F.round("y30", 3))
             .withColumn("label_bin", amount_class()))
    if history_model:
        frame = frame.where(F.col("history_complete"))
    if "target_end" not in frame.columns:
        frame = frame.withColumn("target_end", F.col("timestamp") + F.expr("INTERVAL 30 MINUTES"))
    full_train = temporal_split(frame, 2017, 2022).persist(StorageLevel.MEMORY_AND_DISK)
    train = deterministic_sample(full_train, args.train_fraction, args.seed).persist(StorageLevel.MEMORY_AND_DISK)
    validation = deterministic_sample(temporal_split(frame, 2022, 2023), args.eval_fraction, args.seed).persist(StorageLevel.MEMORY_AND_DISK)
    calibration = deterministic_sample(temporal_split(frame, 2023, 2024), args.eval_fraction, args.seed)
    test = deterministic_sample(temporal_split(frame, 2024, 2025), args.eval_fraction, args.seed)
    counts = {"train_full": full_train.count(), "train_sample": train.count(), "validation": validation.count(),
              "calibration": calibration.count(), "test": test.count()}
    if any(count == 0 for count in counts.values()):
        raise ValueError(f"Every chronological split must be nonempty; observed counts={counts}")
    print("Split counts:", json.dumps(counts), flush=True)
    write_csv(full_train.groupBy("label_bin").count(), output + "/audit/train_amount_classes")
    write_csv(train.groupBy("label_bin").count(), output + "/audit/sampled_train_amount_classes")
    supports = build_empirical_support(full_train)
    sampled_classes = {int(row.label_bin) for row in train.select("label_bin").distinct().collect()}
    missing = [i for i, item in enumerate(supports) if item["n"] and i not in sampled_classes]
    if missing:
        raise ValueError(f"Training sample missed amount classes {missing}; increase --train-fraction.")
    write_json(spark, supports, output + "/empirical_support")
    max_bins = max(64, train.select("station_id").distinct().count() + 2)
    climatology, global_rates = fit_climatology(full_train, thresholds)
    climatology.write.mode("overwrite").parquet(output + "/climatology")
    global_rates.write.mode("overwrite").parquet(output + "/global_climatology")
    # Materialize from disk: do not rerun training aggregations at every evaluation.
    climatology = spark.read.parquet(output + "/climatology")
    global_rates = spark.read.parquet(output + "/global_climatology")
    candidates = []
    best_score = float("inf")
    best_model = None
    best_depth = None
    for depth in depths:
        print(f"Fitting random forest depth={depth}, trees={args.trees}", flush=True)
        model = make_pipeline(feature_names, depth, args.trees, max_bins, args.seed).fit(train)
        scored = score_distribution(model, validation).persist(StorageLevel.MEMORY_AND_DISK)
        score = float(macro_brier(threshold_predictions(scored, supports, thresholds)))
        candidates.append({"max_depth": depth, "num_trees": args.trees, "validation_macro_brier": score})
        scored.unpersist()
        print("Candidate:", json.dumps(candidates[-1]), flush=True)
        if score < best_score:
            best_score, best_model, best_depth = score, model, depth
    write_csv(spark.createDataFrame(candidates), output + "/metrics/model_selection")
    # Binary baseline uses the same anchor sample, splits and evaluation thresholds.
    binary_train = expand_thresholds(train, thresholds).persist(StorageLevel.MEMORY_AND_DISK)
    binary_val = expand_thresholds(validation, thresholds)
    binary_candidates, best_binary, binary_best_score = [], None, float("inf")
    for reg in (0.01, 0.1):
        candidate = binary_pipeline(feature_names, reg).fit(binary_train)
        score = float(macro_brier(score_binary(candidate, binary_val)))
        binary_candidates.append({"reg_param": reg, "validation_macro_brier": score})
        if score < binary_best_score:
            best_binary, binary_best_score = candidate, score
    best_binary.write().overwrite().save(output + "/binary_pipeline")
    write_csv(spark.createDataFrame(binary_candidates), output + "/metrics/binary_model_selection")
    binary_train.unpersist()
    # Freeze latest known training locations; prediction needs no observation lookup.
    from pyspark.sql import Window
    locations = (full_train.withColumn("_rank", F.row_number().over(Window.partitionBy("station_id").orderBy(F.col("timestamp").desc())))
        .where(F.col("_rank") == 1).select("station_id", "latitude", "longitude"))
    locations.write.mode("overwrite").parquet(output + "/stations")
    train.unpersist()
    full_train.unpersist()
    best_model.write().overwrite().save(output + "/pipeline")
    calibration_scores = score_distribution(best_model, calibration).persist(StorageLevel.MEMORY_AND_DISK)
    temperature, temperature_scores = select_temperature(calibration_scores, supports, thresholds)
    write_csv(spark.createDataFrame(temperature_scores), output + "/metrics/calibration_selection")
    calibration_scores.unpersist()
    print(f"Selected max_depth={best_depth}, temperature={temperature}", flush=True)

    # Tune decision cutoffs on 2022 using the final calibrated probability scale.
    # The temperature alone is estimated from 2023; 2024 remains unused here.
    val_scores = score_distribution(best_model, validation).persist(StorageLevel.MEMORY_AND_DISK)
    val_rf = threshold_predictions(val_scores, supports, thresholds, temperature).persist(StorageLevel.MEMORY_AND_DISK)
    val_base = predict_climatology(validation, climatology, global_rates, thresholds).persist(StorageLevel.MEMORY_AND_DISK)
    val_binary = score_binary(best_binary, expand_thresholds(validation, thresholds)).persist(StorageLevel.MEMORY_AND_DISK)
    cutoffs_binary = choose_cutoffs(val_binary)
    cutoffs_rf, cutoffs_base = choose_cutoffs(val_rf), choose_cutoffs(val_base)
    validation_metrics, validation_reliability = [], []
    for name, predictions, cutoffs in [("random_forest", val_rf, cutoffs_rf), ("climatology", val_base, cutoffs_base), ("binary_logistic", val_binary, cutoffs_binary)]:
        metrics, reliability = evaluation_tables(predictions, "validation", name, cutoffs)
        validation_metrics.append(metrics)
        validation_reliability.append(reliability)
    write_csv(union_tables(validation_metrics), output + "/metrics/validation_metrics")
    write_csv(union_tables(validation_reliability), output + "/metrics/validation_reliability")
    for cached in [val_rf, val_base, val_binary, val_scores, validation]:
        cached.unpersist()

    metadata = {
        "schema_version": 2, "feature_mode": feature_mode, "created_utc": datetime.now(timezone.utc).isoformat(),
        "spark_version": spark.version, "python_version": platform.python_version(),
        "model": "RandomForestClassifier + train empirical within-bin survival + temperature calibration",
        "amount_edges": AMOUNT_EDGES, "thresholds_evaluated": thresholds,
        "numeric_features": feature_names, "categorical_features": ["station_id"],
        "depth": best_depth, "num_trees": args.trees, "max_bins": max_bins,
        "min_instances_per_node": 25, "seed": args.seed, "temperature": temperature,
        "train_fraction": args.train_fraction, "eval_fraction": args.eval_fraction,
        "counts": counts, "binary_baseline": "LogisticRegression; threshold feature; uncalibrated",
        "source_data_root": args.data, "requires_recent_rainfall": history_model,
        "latency_minutes": prepare_metadata.get("latency_minutes"),
        "prepare_metadata": prepare_metadata,
        "prepare_smoke_limit": prepare_metadata.get("limit_smoke_test_only"),
        "split_years": {"train": [2017, 2021], "validation": [2022, 2022], "calibration": [2023, 2023], "test": [2024, 2024]},
        "purge": "target_end must precede next split boundary; short-term history is available by anchor time; calendar mode uses no history",
        "cutoffs_binary": cutoffs_binary, "cutoffs_random_forest": cutoffs_rf, "cutoffs_climatology": cutoffs_base,
        "rainfall_rounding_mm": 0.001, "climatology_shrinkage_pseudocount": 100.0,
        "empirical_bin_counts": [item["n"] for item in supports],
        "train_max_y30": max(max(item["amounts"]) for item in supports if item["n"]),
        "limitations": ["Within-bin rainfall shape is global, not conditional on current weather.",
                        "Probabilities above the largest training total are zero; this is a finite-support model limitation.",
                        "Calendar risk cannot anticipate storms; short-term risk needs available recent observations.",
                        "Binary logistic baseline is uncalibrated; threshold monotonicity is not constrained."],
        "test_evaluation_completed": False,
    }
    write_json(spark, metadata, output + "/metadata")
    importance = best_model.stages[-1].featureImportances.toArray().tolist()
    names = list(feature_names) + ["station_id"]
    write_csv(spark.createDataFrame([(name, float(value)) for name, value in zip(names, importance)], "feature string, importance double"), output + "/metrics/feature_importance")

    # Only the chosen calibrated forest and predetermined baseline touch final test.
    test_scores = score_distribution(best_model, test).persist(StorageLevel.MEMORY_AND_DISK)
    test_rf = threshold_predictions(test_scores, supports, thresholds, temperature).persist(StorageLevel.MEMORY_AND_DISK)
    test_base = predict_climatology(test, climatology, global_rates, thresholds).persist(StorageLevel.MEMORY_AND_DISK)
    test_binary = score_binary(best_binary, expand_thresholds(test, thresholds)).persist(StorageLevel.MEMORY_AND_DISK)
    test_metrics, test_reliability, test_subgroups = [], [], []
    for name, predictions, cutoffs in [("random_forest", test_rf, cutoffs_rf), ("climatology", test_base, cutoffs_base), ("binary_logistic", test_binary, cutoffs_binary)]:
        metrics, reliability = evaluation_tables(predictions, "test", name, cutoffs)
        write_csv(threshold_order_diagnostics(predictions), output + "/metrics/threshold_order_" + name)
        test_metrics.append(metrics)
        test_reliability.append(reliability)
        test_subgroups.append(subgroup_table(predictions, "test", name))
    write_csv(union_tables(test_metrics), output + "/metrics/test_metrics")
    write_csv(union_tables(test_reliability), output + "/metrics/reliability")
    write_csv(union_tables(test_subgroups), output + "/metrics/subgroups")
    join_keys = ["station_id", "timestamp", "threshold"]
    paired = (test_rf.select(*join_keys, "label", F.col("probability").alias("p_rf"))
              .join(test_base.select(*join_keys, F.col("probability").alias("p_baseline")), join_keys))
    daily = paired.groupBy("threshold", F.to_date("timestamp").alias("date")).agg(
        F.count("*").alias("n"), F.sum(F.pow(F.col("p_rf") - F.col("label"), 2)).alias("sum_sq_error_rf"),
        F.sum(F.pow(F.col("p_baseline") - F.col("label"), 2)).alias("sum_sq_error_baseline"))
    write_csv(daily, output + "/metrics/daily_scores")
    metadata["elapsed_seconds"] = round(time.monotonic() - start, 2)
    metadata["test_evaluation_completed"] = True
    metadata["spark_configuration"] = {key: value for key, value in spark.sparkContext.getConf().getAll()
                                        if key in {"spark.executor.instances", "spark.executor.cores", "spark.executor.memory", "spark.driver.memory", "spark.master", "spark.sql.shuffle.partitions"}}
    write_json(spark, metadata, output + "/metadata")
    print("Complete:", output, "elapsed_seconds=", metadata["elapsed_seconds"], flush=True)
    for cached in [test_rf, test_base, test_binary, test_scores]:
        cached.unpersist()
    spark.stop()


if __name__ == "__main__":
    main()
