"""Spark distribution classifier and coherent threshold-exceedance probabilities.

The classifier estimates P(amount bin | history).  Within-bin amount distributions
are learned from training data only.  Their mixture supports every numeric rainfall
threshold and is monotone, unlike independently fitted binary classifiers.
"""
import json

from pyspark.ml import Pipeline
from pyspark.ml.classification import RandomForestClassifier, LogisticRegression
from pyspark.ml.evaluation import BinaryClassificationEvaluator
from pyspark.ml.feature import Imputer, StringIndexer, VectorAssembler, OneHotEncoder, StandardScaler
from pyspark.ml.functions import vector_to_array
from pyspark.sql import functions as F
from rainfall.probability import AMOUNT_EDGES, N_CLASSES, survival_weights

DEFAULT_THRESHOLDS = [0.0, 0.2, 1.0, 2.0, 5.0, 10.0, 20.0]
TEMPERATURES = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
EPS = 1e-12


def amount_class(column="y30"):
    """Intervals are {0}, (0,1], ..., (10,20], (20,+inf)."""
    value = F.col(column) if isinstance(column, str) else column
    expression = F.when(value <= AMOUNT_EDGES[0], F.lit(0.0))
    for index, edge in enumerate(AMOUNT_EDGES[1:], start=1):
        expression = expression.when(value <= edge, F.lit(float(index)))
    return expression.otherwise(F.lit(float(N_CLASSES - 1)))


def deterministic_sample(frame, fraction, seed=2026):
    if not 0 < fraction <= 1:
        raise ValueError("Sampling fraction must be in (0, 1].")
    if fraction == 1:
        return frame
    score = F.pmod(F.xxhash64("station_id", "timestamp", F.lit(int(seed))), F.lit(1_000_000))
    return frame.where(score < int(fraction * 1_000_000))


def write_json(spark, value, path):
    """Write one small JSON document using Hadoop-supported local/GCS paths."""
    spark.createDataFrame([(json.dumps(value, ensure_ascii=False, allow_nan=False),)], ["value"]).coalesce(1).write.mode("overwrite").text(path)


def read_json(spark, path):
    rows = spark.read.option("wholetext", True).text(path).collect()
    return json.loads("\n".join(row.value for row in rows))


def write_csv(frame, path):
    frame.coalesce(1).write.mode("overwrite").option("header", True).csv(path)


def build_empirical_support(train):
    """Exact grouped support after 0.001-mm rounding; collect only aggregate data."""
    records = (train.withColumn("amount", F.round("y30", 3))
               .withColumn("label_bin", amount_class("amount"))
               .groupBy("label_bin", "amount").count()
               .orderBy("label_bin", "amount").collect())
    supports = [{"amounts": [], "counts": [], "cumulative": [], "n": 0} for _ in range(N_CLASSES)]
    for row in records:
        item = supports[int(row.label_bin)]
        item["amounts"].append(float(row.amount))
        item["counts"].append(int(row["count"]))
        item["n"] += int(row["count"])
    for item in supports:
        cumulative = 0
        for count in item["counts"]:
            cumulative += count
            item["cumulative"].append(cumulative / item["n"])
    return supports


def temporal_split(frame, start_year, end_year):
    """Half-open anchor interval; purge labels reaching the next interval."""
    return frame.where(
        (F.col("timestamp") >= F.to_timestamp(F.lit(f"{start_year}-01-01 00:00:00")))
        & (F.col("timestamp") < F.to_timestamp(F.lit(f"{end_year}-01-01 00:00:00")))
        & (F.col("target_end") < F.to_timestamp(F.lit(f"{end_year}-01-01 00:00:00"))))


def calibrated_array(probability, temperature=1.0):
    """Keep zero-probability classes zero, including classes absent in training."""
    if temperature <= 0:
        raise ValueError("Temperature must be positive.")
    if temperature == 1.0:
        return probability
    powers = F.transform(probability, lambda p: F.pow(p, F.lit(1.0 / temperature)))
    normalizer = F.aggregate(powers, F.lit(0.0), lambda a, b: a + b)
    return F.transform(powers, lambda p: p / normalizer)


def survival_expression(probability, weights):
    # One array dot product avoids expanding a calibrated-array expression once
    # for every class. zip_with pads absent tail classes with null/zero.
    terms = F.zip_with(probability, F.array(*[F.lit(float(w)) for w in weights]),
        lambda p, w: F.coalesce(p, F.lit(0.0)) * F.coalesce(w, F.lit(0.0)))
    dot = F.aggregate(terms, F.lit(0.0), lambda a, b: a + b)
    return F.greatest(F.lit(0.0), F.least(F.lit(1.0), dot))


def calibrated_survival(probability, weights, temperature=1.0):
    """Compute weighted survival / total power directly, without nested normalization."""
    if temperature <= 0:
        raise ValueError("Temperature must be positive.")
    if temperature == 1.0:
        return survival_expression(probability, weights)
    powers = F.transform(probability, lambda p: F.pow(p, F.lit(1.0 / temperature)))
    terms = F.zip_with(powers, F.array(*[F.lit(float(w)) for w in weights]),
        lambda p, w: F.coalesce(p, F.lit(0.0)) * F.coalesce(w, F.lit(0.0)))
    numerator = F.aggregate(terms, F.lit(0.0), lambda a,b:a+b)
    denominator = F.aggregate(powers, F.lit(0.0), lambda a,b:a+b)
    return F.greatest(F.lit(0.0),F.least(F.lit(1.0),numerator/denominator))


def make_pipeline(numeric_features, depth, trees=40, max_bins=128, seed=2026,
                  min_instances_per_node=25, feature_subset_strategy="sqrt", subsampling_rate=0.8):
    imputed = [name + "_imputed" for name in numeric_features]
    stages = [
        StringIndexer(inputCol="station_id", outputCol="station_index", handleInvalid="keep", stringOrderType="alphabetAsc"),
        Imputer(strategy="median", inputCols=numeric_features, outputCols=imputed),
        VectorAssembler(inputCols=imputed + ["station_index"], outputCol="features"),
        RandomForestClassifier(labelCol="label_bin", featuresCol="features", probabilityCol="probability", numTrees=trees,
                               maxDepth=depth, maxBins=max_bins, minInstancesPerNode=min_instances_per_node,
                               featureSubsetStrategy=feature_subset_strategy, subsamplingRate=subsampling_rate,
                               seed=seed, maxMemoryInMB=512),
    ]
    return Pipeline(stages=stages)


def score_distribution(pipeline, frame):
    columns = [c for c in ["station_id", "timestamp", "month", "hour", "y30", "rain_sum_30"] if c in frame.columns]
    return pipeline.transform(frame).select(*columns, vector_to_array("probability").alias("class_probability"))


def threshold_predictions(scored, supports, thresholds, temperature=1.0):
    entries = []
    for threshold in thresholds:
        entries.append(F.struct(
            F.lit(float(threshold)).alias("threshold"),
            calibrated_survival(F.col("class_probability"), survival_weights(supports, threshold), temperature).alias("probability"),
            (F.col("y30") > threshold).cast("double").alias("label")))
    return (scored.withColumn("point", F.explode(F.array(*entries)))
            .select("station_id", "timestamp", "month", "hour", "y30", "point.*"))


def select_temperature(scored, supports, thresholds):
    expressions = []
    for ti, temperature in enumerate(TEMPERATURES):
        for qi, threshold in enumerate(thresholds):
            prediction = calibrated_survival(F.col("class_probability"), survival_weights(supports, threshold), temperature)
            label = (F.col("y30") > threshold).cast("double")
            expressions.append(F.avg(F.pow(prediction - label, 2)).alias(f"t{ti}_q{qi}"))
    row = scored.agg(*expressions).first()
    records = [{"temperature": temperature,
                "macro_brier": sum(row[f"t{ti}_q{qi}"] for qi in range(len(thresholds))) / len(thresholds)}
               for ti, temperature in enumerate(TEMPERATURES)]
    best = min(records, key=lambda item: (item["macro_brier"], abs(item["temperature"] - 1.0)))
    return best["temperature"], records


def macro_brier(predictions):
    return predictions.groupBy("threshold").agg(F.avg(F.pow(F.col("probability") - F.col("label"), 2)).alias("brier")).agg(F.avg("brier")).first()[0]


def fit_climatology(train, thresholds, alpha=100.0):
    """Unweighted train frequencies, shrunk toward global frequency by alpha."""
    expanded = train.withColumn("threshold", F.explode(F.array(*[F.lit(float(t)) for t in thresholds])))
    expanded = expanded.withColumn("label", (F.col("y30") > F.col("threshold")).cast("double"))
    global_rates = expanded.groupBy("threshold").agg(F.avg("label").alias("global_rate"))
    table = (expanded.groupBy("station_id", "month", "hour", "threshold")
             .agg(F.count("*").alias("group_n"), F.sum("label").alias("positive_n"))
             .join(global_rates, "threshold")
             .withColumn("probability", (F.col("positive_n") + alpha * F.col("global_rate")) / (F.col("group_n") + alpha)))
    return table, global_rates


def predict_climatology(frame, table, global_rates, thresholds):
    frame = frame.select("station_id", "timestamp", "month", "hour", "y30")
    frame = frame.withColumn("threshold", F.explode(F.array(*[F.lit(float(t)) for t in thresholds])))
    keys = ["station_id", "month", "hour", "threshold"]
    return (frame.join(table.select(*keys, "probability"), keys, "left")
            .join(global_rates, "threshold", "left")
            .withColumn("probability", F.coalesce("probability", "global_rate"))
            .withColumn("label", (F.col("y30") > F.col("threshold")).cast("double")))


def choose_cutoffs(predictions):
    candidates = [0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    expanded = predictions.withColumn("cutoff", F.explode(F.array(*[F.lit(x) for x in candidates])))
    positive = F.col("probability") >= F.col("cutoff")
    rows = expanded.groupBy("threshold", "cutoff").agg(
        F.sum((positive & (F.col("label") == 1)).cast("long")).alias("tp"),
        F.sum((positive & (F.col("label") == 0)).cast("long")).alias("fp"),
        F.sum((~positive & (F.col("label") == 1)).cast("long")).alias("fn")).collect()
    selected = {}
    for row in rows:
        denominator = 2 * row.tp + row.fp + row.fn
        score = 2 * row.tp / denominator if denominator else 0.0
        previous = selected.get(row.threshold)
        if previous is None or (score, -abs(row.cutoff - 0.5)) > (previous[0], -abs(previous[1] - 0.5)):
            selected[row.threshold] = (score, float(row.cutoff))
    return {str(threshold): values[1] for threshold, values in selected.items()}


def roc_pr_auc(subset):
    """Reuse Spark's sorted score counts for both AUCs (Spark 3.5 API)."""
    evaluator = BinaryClassificationEvaluator(rawPredictionCol="probability", labelCol="label", numBins=1000)
    evaluator._transfer_params_to_java()
    metrics = evaluator._java_obj.getMetrics(subset._jdf)
    try:
        return float(metrics.areaUnderROC()), float(metrics.areaUnderPR())
    finally:
        metrics.unpersist()


def evaluation_tables(predictions, split, name, cutoffs=None):
    """Probabilistic metrics plus two classification operating points.

    AUC is undefined for single-class slices and recorded as NULL.  PR-AUC uses
    Spark's area-under-PR convention, which differs from average precision.
    """
    clipped = F.greatest(F.lit(EPS), F.least(F.lit(1.0 - EPS), F.col("probability")))
    basic = predictions.groupBy("threshold").agg(
        F.count("*").alias("n"), F.avg("label").alias("prevalence"),
        F.avg(F.pow(F.col("probability") - F.col("label"), 2)).alias("brier"),
        F.avg(-F.col("label") * F.log(clipped) - (1 - F.col("label")) * F.log(1 - clipped)).alias("log_loss"))
    records = []
    for row in basic.collect():
        threshold = float(row.threshold)
        subset = predictions.where(F.col("threshold") == threshold)
        item = row.asDict()
        if 0 < row.prevalence < 1:
            item["roc_auc"], item["pr_auc"] = roc_pr_auc(subset)
        else:
            item["roc_auc"] = None
            item["pr_auc"] = None
        operating = [("default_0.5", 0.5)]
        if cutoffs is not None:
            operating.append(("validation_f1", float(cutoffs.get(str(threshold), 0.5))))
        for kind, cutoff in operating:
            positive = F.col("probability") >= cutoff
            confusion = subset.agg(
                F.sum((positive & (F.col("label") == 1)).cast("long")).alias("tp"),
                F.sum((positive & (F.col("label") == 0)).cast("long")).alias("fp"),
                F.sum((~positive & (F.col("label") == 0)).cast("long")).alias("tn"),
                F.sum((~positive & (F.col("label") == 1)).cast("long")).alias("fn")).first().asDict()
            tp, fp, fn = confusion["tp"], confusion["fp"], confusion["fn"]
            record = dict(item, split=split, model=name, cutoff_kind=kind, cutoff=float(cutoff), **confusion)
            record["precision"] = tp / (tp + fp) if tp + fp else None
            record["recall"] = tp / (tp + fn) if tp + fn else None
            record["f1"] = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
            records.append(record)
    # Explicit schema keeps all-NULL AUC/precision columns valid on tiny samples.
    schema = "threshold double,n long,prevalence double,brier double,log_loss double,roc_auc double,pr_auc double,split string,model string,cutoff_kind string,cutoff double,tp long,fp long,tn long,fn long,precision double,recall double,f1 double"
    order = [part.strip().split()[0] for part in schema.split(",")]
    metrics = predictions.sparkSession.createDataFrame([tuple(record.get(key) for key in order) for record in records], schema)
    reliability = (predictions.withColumn("bin", F.least(F.lit(9), F.floor(F.col("probability") * 10)))
                   .groupBy("threshold", "bin").agg(F.count("*").alias("n"), F.avg("probability").alias("mean_probability"), F.avg("label").alias("event_rate"))
                   .withColumn("split", F.lit(split)).withColumn("model", F.lit(name)))
    return metrics, reliability


def subgroup_table(predictions, split, name):
    outputs = []
    for column in ["station_id", "month"]:
        outputs.append(predictions.groupBy("threshold", column).agg(
            F.count("*").alias("n"), F.avg("label").alias("prevalence"),
            F.avg(F.pow(F.col("probability") - F.col("label"), 2)).alias("brier"),
            F.avg("probability").alias("mean_probability"))
            .withColumnRenamed(column, "group_value")
            .withColumn("group_value", F.col("group_value").cast("string"))
            .withColumn("group_type", F.lit(column)))
    return outputs[0].unionByName(outputs[1]).withColumn("split", F.lit(split)).withColumn("model", F.lit(name))


def expand_thresholds(frame, thresholds):
    return (frame.withColumn("threshold", F.explode(F.array(*[F.lit(float(q)) for q in thresholds])))
        .withColumn("label", (F.col("y30") > F.col("threshold")).cast("double")))


def binary_pipeline(numeric_features, reg_param):
    # One-hot station IDs avoid imposing an artificial ordering on stations.
    return Pipeline(stages=[
        StringIndexer(inputCol="station_id", outputCol="station_index", handleInvalid="keep"),
        OneHotEncoder(inputCols=["station_index"], outputCols=["station_vector"], handleInvalid="keep"),
        VectorAssembler(inputCols=list(numeric_features) + ["threshold", "station_vector"], outputCol="binary_raw_features"),
        StandardScaler(inputCol="binary_raw_features", outputCol="features", withMean=False),
        LogisticRegression(featuresCol="features", labelCol="label", regParam=reg_param, maxIter=100),
    ])


def score_binary(model, expanded):
    return model.transform(expanded).select("station_id", "timestamp", "month", "threshold", "label",
        vector_to_array("probability")[1].alias("probability"))


def threshold_order_diagnostics(predictions):
    """Adjacent-threshold violations, keeping the same station/time query."""
    from pyspark.sql import Window
    order = Window.partitionBy("station_id", "timestamp").orderBy("threshold")
    pairs = predictions.withColumn("previous_probability", F.lag("probability").over(order)).where(F.col("previous_probability").isNotNull())
    increase = F.greatest(F.lit(0.0), F.col("probability") - F.col("previous_probability"))
    return pairs.agg(F.count("*").alias("adjacent_threshold_pairs"),
        F.avg((increase > 1e-10).cast("double")).alias("violation_fraction"),
        F.max(increase).alias("max_probability_increase"))
