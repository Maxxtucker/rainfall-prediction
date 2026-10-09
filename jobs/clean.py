#!/usr/bin/env python3
"""Clean rainfall CSVs only; no EDA, features, or model training."""
import argparse

from pyspark.sql import SparkSession, types as T

from rainfall.data import clean, profile_rainfall


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", required=True, help="One annual CSV folder, or the complete raw folder")
    parser.add_argument("--output", required=True, help="A new output root; existing outputs are not overwritten")
    parser.add_argument("--shuffle-partitions", type=int, default=200)
    args = parser.parse_args()
    spark = (SparkSession.builder.appName("rainfall-clean-only")
             .config("spark.sql.session.timeZone", "Asia/Singapore")
             .config("spark.sql.ansi.enabled", "false")
             .config("spark.sql.shuffle.partitions", args.shuffle_partitions)
             .config("spark.sql.adaptive.enabled", "true")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    try:
        reader = (spark.read.option("header", True).option("inferSchema", False)
                  .option("recursiveFileLookup", True).option("pathGlobFilter", "*.csv*")
                  .option("mode", "PERMISSIVE")
                  .option("columnNameOfCorruptRecord", "_corrupt_record"))
        # Keep input values as strings, including malformed CSV records, until validation.
        schema = reader.csv(args.raw).schema
        if "_corrupt_record" not in schema.fieldNames():
            schema = T.StructType(schema.fields + [T.StructField("_corrupt_record", T.StringType(), True)])
        raw = reader.schema(schema).csv(args.raw)
        print("Input columns:", raw.columns, flush=True)
        cleaned, quarantine, quality = clean(raw)
        root = args.output.rstrip("/")
        # Default error-if-exists prevents accidentally replacing an earlier experiment.
        cleaned.repartition(args.shuffle_partitions, "year", "month").write.partitionBy("year", "month").parquet(root + "/clean")
        quarantine.write.parquet(root + "/quarantine")
        quality.coalesce(1).write.option("header", True).csv(root + "/quality")
        # Profile the persisted data rather than recomputing the cleaning lineage.
        profile_rainfall(spark.read.parquet(root + "/clean"), root + "/inspection")
        print("Saved clean, quarantine and quality under:", root, flush=True)
        spark.read.option("header", True).csv(root + "/quality").orderBy("metric").show(100, truncate=False)
        spark.read.parquet(root + "/clean").select("station_id", "timestamp", "rainfall", "latitude", "longitude").orderBy("station_id", "timestamp").show(10, truncate=False)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
