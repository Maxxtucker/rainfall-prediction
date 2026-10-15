#!/usr/bin/env python3
"""Query next-30-minute exceedance risk with a saved calendar or history model."""
import argparse
from datetime import datetime
import math
from zoneinfo import ZoneInfo

from pyspark.ml import PipelineModel
from pyspark.ml.functions import vector_to_array
from pyspark.sql import SparkSession, functions as F

from rainfall.data import calendar_features, make_features, FEATURE_MODE
from rainfall.model import calibrated_array, read_json, survival_expression, survival_weights


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--station", required=True, help="Exact station ID, e.g. S50")
    parser.add_argument("--time", required=True, help="ISO time; naive times mean Asia/Singapore")
    parser.add_argument("--threshold", required=True, type=float, help="Strict > threshold, in mm")
    parser.add_argument("--clean", help="Clean observation Parquet; required only for short-term model")
    parser.add_argument("--predictor", choices=["random_forest", "binary_logistic", "gbt"], default="random_forest")
    parser.add_argument("--model", required=True, help="Saved RF/LR/GBT model package")
    parser.add_argument("--output", required=True, help="JSON output directory")
    args = parser.parse_args()
    args.station = args.station.strip().upper()
    if not math.isfinite(args.threshold):
        raise ValueError("threshold must be finite")
    instant = datetime.fromisoformat(args.time.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=ZoneInfo("Asia/Singapore"))
    local = instant.astimezone(ZoneInfo("Asia/Singapore"))
    if local.minute % 5 or local.second or local.microsecond:
        raise ValueError("Prediction time must lie on the five-minute grid.")
    time_text = local.strftime("%Y-%m-%d %H:%M:%S")
    spark = (SparkSession.builder.appName("Singapore rainfall - predict")
             .config("spark.sql.session.timeZone", "Asia/Singapore").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    model_root = args.model.rstrip("/")
    metadata = read_json(spark, model_root + "/metadata")
    is_gbt = metadata.get("model", "").startswith("GBTClassifier")
    supported = metadata.get("supported_predictors", ["gbt"] if is_gbt else ["random_forest", "binary_logistic"])
    if args.predictor not in supported:
        spark.stop()
        raise ValueError(
            f"This model supports {', '.join(supported)}; predictor {args.predictor} is unavailable."
        )
    mode = metadata.get("feature_mode")
    if mode not in (FEATURE_MODE, "short_term_v3"):
        raise ValueError("Incompatible legacy model; retrain.")
    if mode == "short_term_v3":
        if not args.clean:
            raise ValueError("Short-term prediction requires --clean with observations available near the requested time.")
        timestamp = F.to_timestamp(F.lit(time_text))
        latency = int(metadata.get("latency_minutes") or 10)
        clean = (spark.read.parquet(args.clean).where((F.col("station_id") == args.station)
            & (F.col("timestamp") <= timestamp)
            & (F.col("timestamp") >= timestamp - F.expr(f"INTERVAL {latency + 70} MINUTES"))))
        anchors = spark.createDataFrame([(args.station, time_text)], 'station_id string,time_text string').select('station_id', F.to_timestamp('time_text').alias('timestamp'))
        features = make_features(clean, with_labels=False, latency_minutes=latency, anchors=anchors).where(F.col("history_complete"))
        if features.limit(1).count() == 0:
            raise ValueError("Recent station history is incomplete or unpublished. Use the calendar model for advance future-date risk; no silent fallback.")
    else:
        stations = spark.read.parquet(model_root + "/stations").where(F.col("station_id") == args.station)
        if stations.limit(1).count() == 0:
            raise ValueError("Unknown station: no location in frozen training catalogue.")
        features = calendar_features(stations.withColumn("timestamp", F.to_timestamp(F.lit(time_text))))
    if args.predictor == "random_forest":
        pipeline = PipelineModel.load(model_root + "/pipeline")
        supports = read_json(spark, model_root + "/empirical_support")
        scored = pipeline.transform(features)
        probabilities = calibrated_array(vector_to_array("probability"), float(metadata["temperature"]))
        probability = survival_expression(probabilities, survival_weights(supports, args.threshold))
    elif args.predictor == "gbt":
        pipeline = PipelineModel.load(model_root + "/pipeline")
        scored = pipeline.transform(features.withColumn("threshold", F.lit(args.threshold)))
        scored = scored.withColumn("_raw_probability", vector_to_array("probability")[1])
        from rainfall.model import calibrated_survival
        probability = F.lit(1.0) if args.threshold < 0 else calibrated_survival(
            F.array(1.0-F.col("_raw_probability"), F.col("_raw_probability")), [0.0,1.0], float(metadata["temperature"]))
    else:
        pipeline = PipelineModel.load(model_root + "/binary_pipeline")
        scored = pipeline.transform(features.withColumn("threshold", F.lit(args.threshold)))
        probability = F.lit(1.0) if args.threshold < 0 else vector_to_array("probability")[1]
    result = (scored.withColumn("threshold_mm", F.lit(args.threshold))
        .withColumn("probability_exceedance", probability)
        .withColumn("model", F.lit(args.predictor))
        .withColumn("prediction_kind", F.lit("short_term_risk" if mode == "short_term_v3" else "historical_calendar_risk"))
        .withColumn("threshold_beyond_training_support", F.lit(args.threshold >= float(metadata["train_max_y30"]) if metadata.get("train_max_y30") is not None else None).cast("boolean"))
        .select("station_id", "timestamp", "target_end", "threshold_mm", "probability_exceedance", "model", "prediction_kind", "threshold_beyond_training_support"))
    result.coalesce(1).write.mode("overwrite").json(args.output)
    result.show(truncate=False)
    spark.stop()


if __name__ == "__main__":
    main()
