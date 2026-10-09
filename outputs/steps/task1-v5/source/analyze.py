#!/usr/bin/env python3
"""Task 1 only: read persisted clean Parquet; no cleaning, features or training."""
import argparse
import json
from datetime import datetime, timezone

from pyspark.sql import SparkSession
from rainfall.exploration import explore_full


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", required=True, help="The clean/ Parquet directory")
    parser.add_argument("--output", required=True, help="Fresh Task 1 output directory")
    parser.add_argument("--shuffle-partitions", type=int, default=200)
    parser.add_argument("--monthly-coverage", type=float, default=.90, help="Minimum valid five-minute coverage per station-month")
    parser.add_argument("--raw", help="Optional raw root for a source-versus-clean daily audit")
    args = parser.parse_args()
    spark = (SparkSession.builder.appName("rainfall-task1-only")
             .config("spark.sql.session.timeZone", "Asia/Singapore")
             .config("spark.sql.shuffle.partitions", args.shuffle_partitions)
             .config("spark.sql.adaptive.enabled", "true").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    try:
        clean = spark.read.parquet(args.clean)
        years = sorted(row.year for row in clean.select("year").distinct().collect())
        if years != list(range(2017, 2025)):
            raise ValueError(f"Task 1 requires all eight years; found {years}.")
        explore_full(clean, args.output.rstrip("/") + "/eda", mode="errorifexists", monthly_coverage=args.monthly_coverage, raw_path=args.raw)
        metadata = {"created_utc": datetime.now(timezone.utc).isoformat(),
                    "spark_version": spark.version, "clean_input": args.clean,
                    "years": years, "timezone": "Asia/Singapore",
                    "comparison": "all 96 year-months; available eligible station-months plus pair-specific common-station comparisons",
                    "totals": "observed amounts, no missing-data scaling or imputation",
                    "monthly_coverage_threshold": args.monthly_coverage,
                    "daily_policy": "all eligible station-months; station days with coverage >=95%"}
        spark.createDataFrame([(json.dumps(metadata),)], "value string").coalesce(1).write.text(args.output.rstrip("/") + "/metadata")
        print("Task 1 aggregates saved:", args.output, flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
