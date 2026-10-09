"""Auditable rainfall preparation using Spark SQL/DataFrame operations.

All timestamps are interpreted/displayed in Asia/Singapore. Rainfall is an amount
per observation interval, not a rate: sums below have units mm, never mm/hour.
"""

from __future__ import annotations

import re
from functools import reduce
from typing import Optional

from pyspark import StorageLevel
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

YEARS = list(range(2017, 2025))
HISTORY_NUMERIC_FEATURES = [
    "latitude", "longitude", "hour_sin", "hour_cos", "doy_sin", "doy_cos",
    "rain_lag_1", "rain_lag_2", "rain_lag_3", "rain_sum_15", "rain_sum_30",
    "rain_sum_60", "rain_max_30", "wet_count_60", "dry_fraction_60",
    "rain_trend_15",
]


def _normal_name(name: str) -> str:
    if name.strip().lstrip("\ufeff") == "_corrupt_record":
        return "_corrupt_record"
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name.strip().lstrip("\ufeff"))
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


_ALIASES = {
    "timestamp": ("timestamp", "observation_time", "observation_timestamp", "time"),
    "update_timestamp": ("update_timestamp", "updated_timestamp", "update_time", "updatedtimestamp"),
    "reading_update_timestamp": ("reading_update_timestamp", "reading_updated_timestamp", "reading_update_time", "reading_updatedtimestamp"),
    "station_id": ("station_id", "stationid", "station_identifier"),
    "station_name": ("station_name", "stationname", "name"),
    "latitude": ("station_location_latitude", "station_location_lat", "station_latitude", "station_locationlatitude", "location_latitude", "latitude"),
    "longitude": ("station_location_longitude", "station_location_lon", "station_longitude", "station_locationlongitude", "location_longitude", "longitude"),
    "rainfall": ("rainfall", "rainfall_amount", "rainfall_mm", "reading_value", "value"),
    "reading_unit": ("reading_unit", "rainfall_unit", "unit"),
    "reading_type": ("reading_type", "rainfall_type", "type"),
    "station_device_id": ("station_device_id", "device_id", "station_deviceid"),
}


def _canonicalize(raw: DataFrame) -> DataFrame:
    normalized = [_normal_name(name) for name in raw.columns]
    if len(set(normalized)) != len(normalized):
        raise ValueError("Column normalization creates duplicate names; inspect the CSV header.")
    frame = raw.toDF(*normalized)
    for target, aliases in _ALIASES.items():
        found = [name for name in aliases if name in frame.columns]
        if target not in frame.columns and found:
            frame = frame.withColumnRenamed(found[0], target)
    required = {"timestamp", "station_id", "latitude", "longitude", "rainfall", "reading_unit", "reading_type"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}; available: {frame.columns}")
    for name in ("station_name", "station_device_id", "update_timestamp", "reading_update_timestamp"):
        if name not in frame.columns:
            frame = frame.withColumn(name, F.lit(None).cast("string"))
    return frame


def _parse_timestamp(column):
    # Spark's cast accepts both offset-bearing ISO strings and local timestamps.
    # ANSI mode is disabled in the job so malformed values become null, auditable.
    return F.to_timestamp(F.trim(column.cast("string")))


def clean(raw_df: DataFrame) -> tuple[DataFrame, DataFrame, DataFrame]:
    """Return clean records, rejected source rows, and a metric/value QA table.

    Repeated identical measurements with different publication metadata are
    combined conservatively: the latest publication timestamps determine feature
    availability. Conflicting measurements/coordinates quarantine the entire key.
    Exact source duplicates are counted separately. No positive rainfall is capped.
    """
    raw_df.sparkSession.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    raw_df.sparkSession.conf.set("spark.sql.ansi.enabled", "false")
    source = _canonicalize(raw_df)
    if "source_file" not in source.columns:
        source = source.withColumn("source_file", F.input_file_name())
    if "_corrupt_record" not in source.columns:
        source = source.withColumn("_corrupt_record", F.lit(None).cast("string"))
    source = (source
        .withColumn("source_year", F.coalesce(
            F.regexp_extract("source_file", r"(?:^|/)year=(20(?:17|18|19|20|21|22|23|24))(?:/|$)", 1).cast("int"),
            F.regexp_extract(F.regexp_extract("source_file", r"([^/]+)$", 1), r"(?:^|[^0-9])(20(?:17|18|19|20|21|22|23|24))(?:[^0-9]|$)", 1).cast("int")))
        .withColumn("raw_timestamp", F.col("timestamp").cast("string"))
        .withColumn("raw_update_timestamp", F.col("update_timestamp").cast("string"))
        .withColumn("raw_reading_update_timestamp", F.col("reading_update_timestamp").cast("string"))
        .withColumn("raw_rainfall", F.col("rainfall").cast("string"))
        .withColumn("raw_latitude", F.col("latitude").cast("string"))
        .withColumn("raw_longitude", F.col("longitude").cast("string"))
        .withColumn("observed_timestamp", _parse_timestamp(F.col("timestamp")))
        .withColumn("update_timestamp", _parse_timestamp(F.col("update_timestamp")))
        .withColumn("reading_update_timestamp", _parse_timestamp(F.col("reading_update_timestamp")))
        .withColumn("station_id", F.upper(F.trim(F.col("station_id").cast("string"))))
        .withColumn("station_name", F.trim(F.col("station_name").cast("string")))
        .withColumn("rainfall", F.col("rainfall").cast("double"))
        .withColumn("latitude", F.col("latitude").cast("double"))
        .withColumn("longitude", F.col("longitude").cast("double"))
        .withColumn("_epoch", F.col("observed_timestamp").cast("double"))
        .withColumn("_grid_epoch", F.round(F.col("_epoch") / F.lit(300)) * 300)
        .withColumn("timestamp", F.col("_grid_epoch").cast("timestamp"))
        .withColumn("grid_shift_seconds", F.col("_grid_epoch") - F.col("_epoch")))
    reasons = [
        F.when(F.col("_corrupt_record").isNotNull(), "malformed_csv"),
        F.when(F.col("station_id").isNull() | (F.length("station_id") == 0), "missing_station_id"),
        F.when(F.col("observed_timestamp").isNull(), "invalid_timestamp"),
        F.when(F.abs(F.col("grid_shift_seconds")) > 2, "off_five_minute_grid"),
        F.when(~F.year("timestamp").isin(YEARS), "outside_2017_2024"),
        F.when(F.col("rainfall").isNull() | F.isnan("rainfall") | (F.abs(F.col("rainfall")) == float("inf")) | (F.col("rainfall") < 0), "invalid_rainfall"),
        F.when(F.col("latitude").isNull() | F.isnan("latitude") | ~F.col("latitude").between(-90, 90), "invalid_latitude"),
        F.when(F.col("longitude").isNull() | F.isnan("longitude") | ~F.col("longitude").between(-180, 180), "invalid_longitude"),
        F.when(F.col("reading_unit").isNull() | (F.lower(F.trim("reading_unit")) != "mm"), "unexpected_unit"),
        F.when(F.col("reading_type").isNull() | ~F.lower(F.trim("reading_type")).isin("tb1 rainfall 5 minute total f", "rainfall"), "unexpected_reading_type"),
    ]
    source = (source.withColumn("rejection_reasons", F.filter(F.array(*reasons), lambda x: x.isNotNull()))
        .withColumn("availability_missing", F.col("update_timestamp").isNull() | F.col("reading_update_timestamp").isNull())
        .withColumn("outside_singapore_box_flag", ~F.col("latitude").between(1.1, 1.6) | ~F.col("longitude").between(103.5, 104.2))
        .persist(StorageLevel.DISK_ONLY))
    valid = source.filter(F.size("rejection_reasons") == 0)
    invalid_keys = (source.filter((F.size("rejection_reasons") > 0)
                    & F.col("station_id").isNotNull() & (F.length("station_id") > 0)
                    & F.col("timestamp").isNotNull() & (F.abs(F.col("grid_shift_seconds")) <= 2))
                    .select("station_id", "timestamp").distinct()
                    .withColumn("_invalid_sibling", F.lit(True)))
    # Collapse exact source duplicates for data values and metadata, ignoring file
    # path: copying an annual file must not change either rainfall or availability.
    duplicate_columns = [c for c in valid.columns if c not in ("source_file", "source_year", "rejection_reasons")]
    unique = valid.dropDuplicates(duplicate_columns)
    grouped = unique.groupBy("station_id", "timestamp").agg(
        F.countDistinct(F.struct("rainfall", "latitude", "longitude")).alias("measurement_variants"),
        F.count("*").alias("metadata_variants"),
        F.max("station_name").alias("station_name"),
        F.max("station_device_id").alias("station_device_id"),
        F.max("rainfall").alias("rainfall"),
        F.max("latitude").alias("latitude"), F.max("longitude").alias("longitude"),
        F.max("update_timestamp").alias("update_timestamp"),
        F.max("reading_update_timestamp").alias("reading_update_timestamp"),
        F.max(F.col("availability_missing").cast("int")).cast("boolean").alias("availability_missing"),
        F.min("observed_timestamp").alias("observed_timestamp_min"),
        F.max("observed_timestamp").alias("observed_timestamp_max"),
        F.sort_array(F.collect_set("raw_timestamp")).alias("raw_timestamps"),
        F.sort_array(F.collect_set("raw_update_timestamp")).alias("raw_update_timestamps"),
        F.sort_array(F.collect_set("raw_reading_update_timestamp")).alias("raw_reading_update_timestamps"),
        F.max(F.abs(F.col("grid_shift_seconds"))).alias("max_grid_shift_seconds"),
        F.max(F.col("outside_singapore_box_flag").cast("int")).cast("boolean").alias("outside_singapore_box_flag"),
    ).join(invalid_keys, ["station_id", "timestamp"], "left").persist(StorageLevel.DISK_ONLY)
    rejected_keys = (grouped.filter((F.col("measurement_variants") > 1) | F.coalesce(F.col("_invalid_sibling"), F.lit(False)))
        .select("station_id", "timestamp", F.filter(F.array(
            F.when(F.col("measurement_variants") > 1, F.lit("conflicting_station_time_measurement")),
            F.when(F.col("_invalid_sibling"), F.lit("key_has_invalid_source_record"))), lambda x: x.isNotNull()).alias("rejection_reasons")))
    bad_conflicts = valid.drop("rejection_reasons").join(rejected_keys, ["station_id", "timestamp"], "inner")
    quarantine = source.filter(F.size("rejection_reasons") > 0).unionByName(bad_conflicts)
    clean_key = (F.col("measurement_variants") == 1) & ~F.coalesce(F.col("_invalid_sibling"), F.lit(False))
    cleaned = (grouped.filter(clean_key)
        .drop("measurement_variants", "_invalid_sibling")
        .withColumn("year", F.year("timestamp"))
        .withColumn("month", F.month("timestamp")))

    raw_metrics = source.agg(
        F.count("*").alias("raw_rows"),
        F.sum((F.size("rejection_reasons") > 0).cast("long")).alias("invalid_source_rows"),
        F.sum(((F.abs(F.col("grid_shift_seconds")) > 0) & (F.abs(F.col("grid_shift_seconds")) <= 2)).cast("long")).alias("rounded_timestamp_source_rows"),
        F.sum(F.col("availability_missing").cast("long")).alias("missing_or_invalid_availability_source_rows"),
        F.sum((F.col("source_year").isNotNull() & (F.col("source_year") != F.year("timestamp"))).cast("long")).alias("source_year_mismatch_rows"),
    )
    grouped_metrics = grouped.agg(
        F.sum(clean_key.cast("long")).alias("clean_station_time_rows"),
        F.sum((F.col("measurement_variants") > 1).cast("long")).alias("conflicting_station_time_keys"),
        F.sum(F.coalesce(F.col("_invalid_sibling"), F.lit(False)).cast("long")).alias("valid_station_time_keys_with_invalid_sibling"),
        F.sum("metadata_variants").alias("valid_rows_after_exact_deduplication"),
    )
    def unpivot(frame):
        return frame.select(F.explode(F.array(*[
            F.struct(F.lit(c).alias("metric"), F.coalesce(F.col(c).cast("double"), F.lit(0.0)).alias("value"))
            for c in frame.columns])).alias("m")).select("m.*")
    quality = unpivot(raw_metrics).unionByName(unpivot(grouped_metrics))
    exact_duplicates = raw_metrics.crossJoin(grouped_metrics).select(F.lit("exact_duplicate_valid_source_rows").alias("metric"),
        (F.col("raw_rows") - F.col("invalid_source_rows") - F.col("valid_rows_after_exact_deduplication")).cast("double").alias("value"))
    quality = quality.unionByName(exact_duplicates)
    reasons_quality = (quarantine.select(F.explode("rejection_reasons").alias("reason"))
        .groupBy("reason").count().select(F.concat(F.lit("rejected_reason_"), F.col("reason")).alias("metric"), F.col("count").cast("double").alias("value")))
    return cleaned, quarantine, quality.unionByName(reasons_quality)


def make_features(clean_df: DataFrame, with_labels: bool = True,
                  latency_minutes: int = 10, anchors: Optional[DataFrame] = None) -> DataFrame:
    """Construct causal histories and optionally six exact future observations.

    ``rain_lag_1`` ends at t-latency; lag_2 at t-latency-5 min, etc. A
    60-minute history comprises 12 intervals. Every lag requires exact timestamp
    matching AND both source publication timestamps <= prediction t. Missing
    intervals or publication timestamps never become zero rainfall.

    Supplying anchors(station_id,timestamp) also supports prediction at a grid
    instant with no contemporaneous rainfall record. Non-anchor timeline rows are
    used solely to build history and are removed after window evaluation.
    """
    if latency_minutes < 5 or latency_minutes % 5:
        raise ValueError("latency_minutes must be a positive multiple of five, >=5")
    clean_df.sparkSession.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    selected = ["station_id", "timestamp", "station_name", "latitude", "longitude", "rainfall", "update_timestamp", "reading_update_timestamp", "availability_missing"]
    timeline = clean_df.select(*selected)
    if anchors is None:
        timeline = timeline.withColumn("_is_anchor", F.lit(True))
    else:
        anchor_keys = anchors.select("station_id", "timestamp").distinct().withColumn("_is_anchor", F.lit(True))
        timeline = timeline.join(anchor_keys, ["station_id", "timestamp"], "full_outer")
    # Exact epoch ranges avoid making an unrelated missing t-5 row a hidden
    # prerequisite when the selected history begins at t-10.
    order = Window.partitionBy("station_id").orderBy(F.col("timestamp").cast("long"))
    first_lag = latency_minutes // 5
    observation = F.struct("timestamp", "rainfall", "update_timestamp", "reading_update_timestamp", "availability_missing", "station_name", "latitude", "longitude")
    for index in range(12):
        offset = first_lag + index
        lag = F.first(observation).over(order.rangeBetween(-offset * 300, -offset * 300))
        timeline = timeline.withColumn(f"_history_{index}", lag)
    if with_labels:
        for step in range(1, 7):
            timeline = timeline.withColumn(f"_future_{step}", F.first(F.struct("timestamp", "rainfall")).over(order.rangeBetween(step * 300, step * 300)))
    history = []
    for index in range(12):
        lag = F.col(f"_history_{index}")
        expected = F.col("timestamp").cast("long") - (latency_minutes + index * 5) * 60
        valid = ((lag["timestamp"].cast("long") == expected)
                 & lag["rainfall"].isNotNull()
                 & (lag["update_timestamp"] <= F.col("timestamp"))
                 & (lag["reading_update_timestamp"] <= F.col("timestamp"))
                 & ~F.coalesce(lag["availability_missing"], F.lit(True)))
        history.append(F.when(valid, lag["rainfall"]))
    timeline = timeline.withColumn("_history", F.array(*history))
    # Station location can change. Use the metadata attached to the newest
    # available history observation, never the current/future record's metadata.
    for name in ("station_name", "latitude", "longitude"):
        timeline = timeline.withColumn(name, F.when(F.col("_history")[0].isNotNull(), F.col(f"_history_0.{name}")))
    timeline = timeline.withColumn("history_n", F.size(F.filter("_history", lambda x: x.isNotNull())))
    timeline = timeline.withColumn("history_complete", F.col("history_n") == 12)
    for index in range(3):
        timeline = timeline.withColumn(f"rain_lag_{index+1}", F.col("_history")[index])
    def sum_first(n):
        values = F.slice(F.col("_history"), 1, n)
        return F.when(F.size(F.filter(values, lambda x: x.isNotNull())) == n,
                      F.aggregate(values, F.lit(0.0), lambda a, x: a + x))
    for minutes, intervals in ((15, 3), (30, 6), (60, 12)):
        timeline = timeline.withColumn(f"rain_sum_{minutes}", sum_first(intervals))
    timeline = (timeline
        .withColumn("rain_max_30", F.when(F.col("rain_sum_30").isNotNull(), F.array_max(F.slice("_history", 1, 6))))
        .withColumn("wet_count_60", F.when(F.col("history_complete"), F.size(F.filter("_history", lambda x: x > 0))))
        .withColumn("dry_fraction_60", F.when(F.col("history_complete"), (12 - F.col("wet_count_60")) / 12.0))
        .withColumn("rain_trend_15", 2 * F.col("rain_sum_15") - F.col("rain_sum_30"))
        .withColumn("year", F.year("timestamp"))
        .withColumn("month", F.month("timestamp"))
        .withColumn("hour", F.hour("timestamp"))
        .withColumn("target_end", F.col("timestamp") + F.expr("INTERVAL 30 MINUTES")))
    fractional_hour = F.hour("timestamp") + F.minute("timestamp") / 60.0
    days_in_year = F.datediff(F.make_date(F.year("timestamp") + 1, F.lit(1), F.lit(1)), F.make_date(F.year("timestamp"), F.lit(1), F.lit(1)))
    annual_phase = (F.dayofyear("timestamp") - 1 + fractional_hour / 24.0) / days_in_year
    timeline = (timeline.withColumn("hour_sin", F.sin(2 * 3.141592653589793 * fractional_hour / 24))
        .withColumn("hour_cos", F.cos(2 * 3.141592653589793 * fractional_hour / 24))
        .withColumn("doy_sin", F.sin(2 * 3.141592653589793 * annual_phase))
        .withColumn("doy_cos", F.cos(2 * 3.141592653589793 * annual_phase)))
    output = ["station_id", "station_name", "timestamp", "year", "month", "hour", "target_end", "history_n", "history_complete"] + HISTORY_NUMERIC_FEATURES
    if with_labels:
        futures = [F.when(F.col(f"_future_{step}.timestamp").cast("long") == F.col("timestamp").cast("long") + step * 300,
                          F.col(f"_future_{step}.rainfall")) for step in range(1, 7)]
        timeline = timeline.withColumn("_future", F.array(*futures))
        timeline = timeline.withColumn("label_complete", F.size(F.filter("_future", lambda x: x.isNotNull())) == 6)
        timeline = timeline.withColumn("y30", F.when(F.col("label_complete"), F.round(F.aggregate("_future", F.lit(0.0), lambda a, x: a + x), 3)))
        output += ["label_complete", "y30"]
    return timeline.filter(F.col("_is_anchor") == True).select(*output)


def write_csv(frame: DataFrame, path: str) -> None:
    """Write a small aggregate as a standard Spark CSV directory."""
    frame.coalesce(1).write.mode("overwrite").option("header", True).csv(path)


def profile_rainfall(clean_df: DataFrame, out: str, mode: str = "errorifexists") -> None:
    """Describe cleaned five-minute amounts without inventing an outlier cutoff.

    Quantiles use positive observations only: zeros must not hide the wet tail.
    These exploratory outputs never remove or relabel observations. Annual and
    station-year tables expose sensor/year differences. Percentiles are approximate.
    """
    probabilities = [0.5, 0.95, 0.99, 0.999]

    def summary(keys):
        frame = clean_df.groupBy(*keys).agg(
            F.count("*").alias("observations"),
            F.sum((F.col("rainfall") == 0).cast("long")).alias("zero_observations"),
            F.sum((F.col("rainfall") > 0).cast("long")).alias("positive_observations"),
            F.avg("rainfall").alias("mean_all_mm"),
            F.max("rainfall").alias("max_mm"),
            F.avg(F.when(F.col("rainfall") > 0, F.col("rainfall"))).alias("mean_positive_mm"),
            F.percentile_approx(F.when(F.col("rainfall") > 0, F.col("rainfall")), probabilities, 100000).alias("_positive_quantiles"),
        ).withColumn("zero_fraction", F.col("zero_observations") / F.col("observations"))
        for index, name in enumerate(["positive_p50_mm", "positive_p95_mm", "positive_p99_mm", "positive_p999_mm"]):
            frame = frame.withColumn(name, F.col("_positive_quantiles")[index])
        return frame.drop("_positive_quantiles")

    # Logarithmic bins describe scale; they are not rejection thresholds.
    histogram = (clean_df.where(F.col("rainfall") > 0)
                 .withColumn("log10_bin", F.floor(F.log10("rainfall")))
                 .groupBy("year", "log10_bin").count()
                 .withColumn("lower_mm", F.pow(F.lit(10.0), F.col("log10_bin")))
                 .withColumn("upper_mm", F.pow(F.lit(10.0), F.col("log10_bin") + 1)))
    top = clean_df.orderBy(F.desc("rainfall"), "station_id", "timestamp").limit(100)
    # Preserve adjacent readings and availability metadata for manual review.
    before = clean_df.select("station_id", (F.col("timestamp") + F.expr("INTERVAL 5 MINUTES")).alias("timestamp"), F.col("rainfall").alias("previous_5min_mm"))
    after = clean_df.select("station_id", (F.col("timestamp") - F.expr("INTERVAL 5 MINUTES")).alias("timestamp"), F.col("rainfall").alias("next_5min_mm"))
    review = (top.join(before, ["station_id", "timestamp"], "left")
              .join(after, ["station_id", "timestamp"], "left")
              .select("station_id", "station_name", "timestamp", "rainfall", "previous_5min_mm", "next_5min_mm", "latitude", "longitude", "update_timestamp", "reading_update_timestamp")
              .orderBy(F.desc("rainfall"), "station_id", "timestamp"))
    outputs = {
        "rainfall_distribution": summary(["year"]).orderBy("year"),
        "rainfall_distribution_by_station": summary(["station_id", "year"]).orderBy("station_id", "year"),
        "rainfall_positive_histogram": histogram.orderBy("year", "log10_bin"),
        "rainfall_top100_review": review,
    }
    for name, frame in outputs.items():
        frame.coalesce(1).write.mode(mode).option("header", True).csv(f"{out.rstrip('/')}/{name}")


def _matched_month_panel(monthly: DataFrame, stable_keys: DataFrame, threshold: float):
    """Select calendar months first, then their eight-year station intersection.

    Only coverage/location information determines eligibility, never rainfall.
    An empty intersection is reported rather than silently relaxing criteria.
    """
    pairs = (monthly.where(F.col("coverage") >= threshold)
        .join(stable_keys, "station_id", "left_semi")
        .groupBy("station_id", "month").agg(F.countDistinct("year").alias("years"))
        .where(F.col("years") == len(YEARS)).select("station_id", "month"))
    months = sorted(row.month for row in pairs.select("month").distinct().collect())
    panel = (pairs.groupBy("station_id").agg(F.count("*").alias("comparison_month_count"))
        .where(F.col("comparison_month_count") == len(months)))
    return pairs, months, panel


def explore(clean_df: DataFrame, out: str, mode: str = "overwrite", monthly_coverage: float = .90) -> None:
    """Coverage-aware monthly, yearly, diurnal and extreme rainfall summaries."""
    if not 0 < monthly_coverage <= 1:
        raise ValueError("monthly_coverage must be in (0, 1]")
    spark = clean_df.sparkSession
    spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    stations = clean_df.groupBy("station_id").agg(F.max("station_name").alias("station_name"), F.avg("latitude").alias("latitude"), F.avg("longitude").alias("longitude"))
    station_changes = (clean_df.groupBy("station_id").agg(
        F.countDistinct("station_name").alias("distinct_names"),
        F.min("latitude").alias("min_latitude"), F.max("latitude").alias("max_latitude"),
        F.min("longitude").alias("min_longitude"), F.max("longitude").alias("max_longitude"))
        .withColumn("latitude_span", F.col("max_latitude") - F.col("min_latitude"))
        .withColumn("longitude_span", F.col("max_longitude") - F.col("min_longitude"))
        .withColumn("spatially_stable", (F.col("latitude_span") <= .005) & (F.col("longitude_span") <= .005)))
    calendar = spark.createDataFrame([(y, m) for y in YEARS for m in range(1, 13)], "year int, month int")
    calendar = calendar.withColumn("expected_intervals", F.dayofmonth(F.last_day(F.make_date("year", "month", F.lit(1)))) * 288)
    monthly_observed = clean_df.groupBy("station_id", "year", "month").agg(
        F.count("*").alias("observed_intervals"), F.sum("rainfall").alias("rainfall_total_mm"),
        F.sum((F.col("rainfall") > 0).cast("long")).alias("wet_intervals"))
    monthly = (stations.crossJoin(F.broadcast(calendar)).join(monthly_observed, ["station_id", "year", "month"], "left")
        .fillna(0, subset=["observed_intervals", "wet_intervals"])
        .withColumn("coverage", F.col("observed_intervals") / F.col("expected_intervals"))
        .withColumn("wet_fraction", F.when(F.col("observed_intervals") > 0, F.col("wet_intervals") / F.col("observed_intervals")))
        .persist(StorageLevel.MEMORY_AND_DISK))
    # No-observation rainfall totals deliberately remain NULL, not zero.
    yearly = (monthly.groupBy("station_id", "year").agg(
        F.sum("observed_intervals").alias("observed_intervals"),
        F.sum("expected_intervals").alias("expected_intervals"),
        F.sum("rainfall_total_mm").alias("rainfall_total_mm"),
        F.sum("wet_intervals").alias("wet_intervals"),
        F.min("coverage").alias("min_month_coverage"),
        F.sum((F.col("observed_intervals") > 0).cast("int")).alias("months_observed"))
        .withColumn("coverage", F.col("observed_intervals") / F.col("expected_intervals"))
        .withColumn("wet_fraction", F.when(F.col("observed_intervals") > 0, F.col("wet_intervals") / F.col("observed_intervals")))
        .persist(StorageLevel.MEMORY_AND_DISK))
    strict_common = (yearly.groupBy("station_id").agg(F.count("*").alias("years"), F.min("coverage").alias("min_annual_coverage"), F.min("min_month_coverage").alias("min_month_coverage"))
        .filter((F.col("years") == 8) & (F.col("min_annual_coverage") >= .95) & (F.col("min_month_coverage") >= .90))
        .join(station_changes.filter("spatially_stable").select("station_id"), "station_id", "left_semi"))
    stable_keys = station_changes.filter("spatially_stable").select("station_id")
    qualified_monthly = monthly.where(F.col("coverage") >= monthly_coverage)
    month_pairs, comparison_months, common = _matched_month_panel(monthly, stable_keys, monthly_coverage)
    common_keys = common.select("station_id")
    matched_monthly = monthly.where(F.col("month").isin(comparison_months)).join(common_keys, "station_id", "left_semi")
    matched_yearly = (matched_monthly.groupBy("station_id", "year").agg(
        F.sum("observed_intervals").alias("observed_intervals"),
        F.sum("expected_intervals").alias("expected_intervals"),
        F.sum("rainfall_total_mm").alias("rainfall_total_mm"),
        F.sum("wet_intervals").alias("wet_intervals"),
        F.count("*").alias("comparison_month_count"))
        .withColumn("coverage", F.col("observed_intervals") / F.col("expected_intervals")))
    def aggregate_period(frame, keys):
        return frame.groupBy(*keys).agg(
            F.count("*").alias("stations"), F.avg("rainfall_total_mm").alias("mean_station_rainfall_mm"),
            F.min("rainfall_total_mm").alias("min_station_rainfall_mm"), F.max("rainfall_total_mm").alias("max_station_rainfall_mm"),
            F.avg("coverage").alias("mean_coverage"), F.sum("wet_intervals").alias("wet_intervals"),
            F.sum("observed_intervals").alias("observed_intervals"), F.sum("rainfall_total_mm").alias("_observed_mm"))
    annual_common = aggregate_period(matched_yearly, ["year"])
    monthly_common = aggregate_period(matched_monthly, ["year", "month"])
    monthly_available = aggregate_period(qualified_monthly, ["year", "month"])
    def wet_statistics(frame):
        return (frame.withColumn("wet_fraction", F.col("wet_intervals") / F.col("observed_intervals"))
            .withColumn("mean_wet_interval_mm", F.when(F.col("wet_intervals") > 0, F.col("_observed_mm") / F.col("wet_intervals"))).drop("_observed_mm"))
    annual_common = wet_statistics(annual_common)
    monthly_common = wet_statistics(monthly_common)
    monthly_available = wet_statistics(monthly_available)
    panel_count = common.count()
    print(f"Task 1 comparison months={comparison_months}; fixed stations={panel_count}; monthly coverage>={monthly_coverage:.0%}", flush=True)
    if panel_count == 0:
        print("WARNING: no matched comparison panel; full-season qualified-month and coverage tables remain available. No synthetic fallback.", flush=True)
    policy = spark.createDataFrame([(
        "matched-calendar-months-v2", monthly_coverage, ",".join(map(str, comparison_months)), panel_count,
        "Same stations and calendar months across 2017–2024; totals are partial-year observed amounts, not annual rainfall. No imputation.")],
        "policy string, monthly_coverage_threshold double, comparison_months string, comparison_stations long, interpretation string")
    def hourly(frame):
        return (frame.withColumn("hour", F.hour("timestamp")).groupBy("year", "hour").agg(
            F.count("*").alias("observed_intervals"), F.sum((F.col("rainfall") > 0).cast("long")).alias("wet_intervals"), F.avg("rainfall").alias("mean_rainfall_mm"))
            .withColumn("wet_fraction", F.col("wet_intervals") / F.col("observed_intervals")))
    year_month = (monthly.groupBy("year", "month").agg(
        F.sum((F.col("observed_intervals") > 0).cast("int")).alias("stations"),
        F.sum("observed_intervals").alias("observed_intervals"), F.sum("wet_intervals").alias("wet_intervals"),
        F.avg("coverage").alias("mean_coverage"), F.avg("rainfall_total_mm").alias("mean_station_observed_total_mm"))
        .withColumn("wet_fraction", F.when(F.col("observed_intervals") > 0, F.col("wet_intervals") / F.col("observed_intervals"))))
    daily = (clean_df.withColumn("date", F.to_date("timestamp")).groupBy("station_id", "date", "year", "month").agg(
        F.count("*").alias("observed_intervals"), F.sum("rainfall").alias("rainfall_total_mm"), F.sum((F.col("rainfall") > 0).cast("long")).alias("wet_intervals"))
        .withColumn("coverage", F.col("observed_intervals") / 288.0))
    common_clean = clean_df.where(F.col("month").isin(comparison_months)).join(common_keys, "station_id", "left_semi")
    # Equal-station averages expose network composition instead of treating all
    # recorded intervals as equally representative of Singapore's land area.
    hour_station = (common_clean.withColumn("hour", F.hour("timestamp"))
        .groupBy("station_id", "year", "month", "hour").agg(
            F.count("*").alias("observed_intervals"),
            F.sum((F.col("rainfall") > 0).cast("long")).alias("wet_intervals"),
            F.sum("rainfall").alias("observed_mm"))
        .join(calendar.select("year", "month", (F.col("expected_intervals") / 24).alias("expected_hour_intervals")), ["year", "month"])
        .withColumn("coverage", F.col("observed_intervals") / F.col("expected_hour_intervals"))
        .where(F.col("coverage") >= .90)
        .withColumn("wet_fraction", F.col("wet_intervals") / F.col("observed_intervals")))
    month_hour = hour_station.groupBy("month", "hour").agg(
        F.count("*").alias("station_year_groups"),
        F.avg("wet_fraction").alias("mean_station_year_wet_fraction"),
        F.avg(F.when(F.col("wet_intervals") > 0, F.col("observed_mm") / F.col("wet_intervals"))).alias("mean_station_year_wet_interval_mm"))
    spatial_year = (matched_yearly.join(common_keys, "station_id", "left_semi")
        .join(stations, "station_id").orderBy("year", "station_id"))
    spatial_month = (monthly.join(month_pairs, ["station_id", "month"], "left_semi")
        .orderBy("year", "month", "station_id"))
    qualified_daily = daily.where(F.col("coverage") >= .95)
    common_daily = qualified_daily.where(F.col("month").isin(comparison_months)).join(common_keys, "station_id", "left_semi")
    daily_distribution = common_daily.groupBy("year").agg(
        F.count("*").alias("qualified_station_days"),
        F.sum((F.col("rainfall_total_mm") > 0).cast("long")).alias("wet_station_days"),
        F.max("rainfall_total_mm").alias("max_station_day_mm"),
        F.percentile_approx("rainfall_total_mm", [.5, .9, .95, .99], 10000).alias("_quantiles"))
    for index, name in enumerate(["p50_daily_mm", "p90_daily_mm", "p95_daily_mm", "p99_daily_mm"]):
        daily_distribution = daily_distribution.withColumn(name, F.col("_quantiles")[index])
    daily_distribution = daily_distribution.drop("_quantiles").withColumn("wet_day_fraction", F.col("wet_station_days") / F.col("qualified_station_days"))
    sensitivity = (yearly.where((F.col("coverage") >= .95) & (F.col("min_month_coverage") >= .90))
        .groupBy("year").agg(F.count("*").alias("stations"), F.avg("rainfall_total_mm").alias("mean_station_rainfall_mm"), F.avg("coverage").alias("mean_coverage")))
    delay_rows = clean_df.withColumn("publication_delay_minutes", F.when(
        ~F.col("availability_missing"),
        (F.greatest("update_timestamp", "reading_update_timestamp").cast("double") - F.col("timestamp").cast("double")) / 60.0))
    delays = delay_rows.groupBy("year").agg(
        F.count("*").alias("observations"),
        F.count("publication_delay_minutes").alias("known_availability"),
        F.sum(F.col("availability_missing").cast("long")).alias("missing_availability"),
        F.percentile_approx("publication_delay_minutes", [.5, .9, .99], 10000).alias("_quantiles"),
        F.sum((F.col("publication_delay_minutes") < (-2.0/60)).cast("long")).alias("publication_before_observation_count"),
        *[F.sum(F.coalesce(F.col("publication_delay_minutes") <= minutes, F.lit(False)).cast("long")).alias(f"_within_{minutes}") for minutes in (10, 30, 60)],
    )
    delays = (delays.withColumn("median_delay_minutes", F.col("_quantiles")[0])
        .withColumn("p90_delay_minutes", F.col("_quantiles")[1])
        .withColumn("p99_delay_minutes", F.col("_quantiles")[2])
        .withColumn("availability_known_fraction", F.col("known_availability") / F.col("observations")))
    for minutes in (10, 30, 60):
        delays = delays.withColumn(f"fraction_all_available_within_{minutes}m", F.col(f"_within_{minutes}") / F.col("observations"))
    delays = delays.drop("_quantiles", "_within_10", "_within_30", "_within_60")
    # Compare eligibility at predeclared coverage cutoffs, without imputing rain.
    coverage_sensitivity = reduce(lambda a, b: a.unionByName(b), [
        monthly.where(F.col("coverage") >= cutoff).groupBy("year").agg(
            F.count("*").alias("qualified_station_months"),
            F.countDistinct("station_id").alias("qualified_stations"))
        .withColumn("monthly_coverage_threshold", F.lit(cutoff)) for cutoff in (.80, .90, .95)])
    outputs = {
        "coverage_threshold_sensitivity": coverage_sensitivity.orderBy("monthly_coverage_threshold", "year"),
        "station_month": monthly.orderBy("station_id", "year", "month"),
        "station_year": yearly.orderBy("station_id", "year"),
        "common_stations": common.orderBy("station_id"),
        "strict_common_stations": strict_common.orderBy("station_id"),
        "comparison_policy": policy,
        "month_comparison_stations": month_pairs.orderBy("month", "station_id"),
        "monthly_available_qualified": monthly_available.orderBy("year", "month"),
        "station_metadata_changes": station_changes.orderBy("station_id"),
        "annual_common": annual_common.orderBy("year"),
        "monthly_common": monthly_common.orderBy("year", "month"),
        "hourly": hourly(clean_df).orderBy("year", "hour"),
        "hourly_common": hourly(common_clean).orderBy("year", "hour"),
        "year_month": year_month.orderBy("year", "month"),
        "daily_qualified": daily.filter(F.col("coverage") >= .95).orderBy("station_id", "date"),
        "extremes": clean_df.orderBy(F.desc("rainfall"), "timestamp", "station_id").limit(100).select("station_id", "station_name", "timestamp", "rainfall", "latitude", "longitude"),
        "daily_extremes": daily.filter(F.col("coverage") >= .95).orderBy(F.desc("rainfall_total_mm"), "date", "station_id").limit(100),
        "month_hour_common": month_hour.orderBy("month", "hour"),
        "spatial_year_common": spatial_year,
        "spatial_year_available": (yearly.where((F.col("coverage") >= .95) & (F.col("min_month_coverage") >= monthly_coverage))
            .join(stable_keys, "station_id", "left_semi").join(stations, "station_id")
            .orderBy("year", "station_id")),
        "spatial_month_common": spatial_month,
        "daily_distribution_common": daily_distribution.orderBy("year"),
        "annual_available_qualified": sensitivity.orderBy("year"),
        "publication_delay_by_year": delays.orderBy("year"),
    }
    # Resolve all output schemas before writing any files, so schema errors do
    # not leave a partially written analysis directory.
    for name, frame in outputs.items():
        columns = [column.casefold() for column in frame.columns]
        duplicates = sorted({column for column in columns if columns.count(column) > 1})
        if duplicates:
            raise ValueError(f"Duplicate columns in Task 1 output {name}: {duplicates}")
    for name, frame in outputs.items():
        frame.coalesce(1).write.mode(mode).option("header", True).csv(f"{out.rstrip('/')}/{name}")
    monthly.unpersist()
    yearly.unpersist()


# Task 2 future-date risk model: no rainfall history or target-year feature.
NUMERIC_FEATURES = ["latitude", "longitude", "hour_sin", "hour_cos", "doy_sin", "doy_cos"]
FEATURE_MODE = "calendar_risk_v2"


def calendar_features(frame):
    """Encode station metadata and requested SGT time, including future dates."""
    frame.sparkSession.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    hour = F.hour("timestamp") + F.minute("timestamp") / 60.0
    days = F.datediff(F.make_date(F.year("timestamp") + 1, F.lit(1), F.lit(1)),
                      F.make_date(F.year("timestamp"), F.lit(1), F.lit(1)))
    phase = (F.dayofyear("timestamp") - 1 + hour / 24.0) / days
    return (frame.withColumn("year", F.year("timestamp"))
        .withColumn("month", F.month("timestamp")).withColumn("hour", F.hour("timestamp"))
        .withColumn("target_end", F.col("timestamp") + F.expr("INTERVAL 30 MINUTES"))
        .withColumn("hour_sin", F.sin(2 * 3.141592653589793 * hour / 24))
        .withColumn("hour_cos", F.cos(2 * 3.141592653589793 * hour / 24))
        .withColumn("doy_sin", F.sin(2 * 3.141592653589793 * phase))
        .withColumn("doy_cos", F.cos(2 * 3.141592653589793 * phase)))


def make_calendar_samples(clean_df):
    """Labels require six exact future intervals; no historical window required.

    Location is attached to the observation at the anchor; future location/rain
    never enters features. Deployment uses a frozen training station catalogue.
    """
    order = Window.partitionBy("station_id").orderBy(F.col("timestamp").cast("long"))
    frame = calendar_features(clean_df)
    futures = []
    for step in range(1, 7):
        name = f"_future_rain_{step}"
        frame = frame.withColumn(name, F.first("rainfall").over(order.rangeBetween(step * 300, step * 300)))
        futures.append(F.col(name))
    frame = frame.withColumn("_future", F.array(*futures))
    return (frame.withColumn("label_complete", F.size(F.filter("_future", lambda x: x.isNotNull())) == 6)
        .withColumn("y30", F.when(F.col("label_complete"), F.round(F.aggregate("_future", F.lit(0.0), lambda a, x: a + x), 3)))
        .select("station_id", "timestamp", "year", "month", "hour", "target_end", "label_complete", "y30", *NUMERIC_FEATURES))
