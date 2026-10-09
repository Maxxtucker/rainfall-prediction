#!/usr/bin/env bash
# Explicit independent Task 2 stages; uses existing cleaned data and cluster.
set -euo pipefail
source "$(dirname "$0")/_env.sh"
cd "$RAINFALL_ROOT"
stage="${1:?Usage: bash cloud/08_task2.sh features|train-calendar|train-short-term|compare|predict-calendar|predict-short-term RUN [extra args]}"
run="${2:?Choose a fresh Task 2 run name}"
shift 2
root="${PROJECT_ROOT}/steps/${run}"
python3 scripts/build_package.py
gcloud storage cp dist/rainfall.zip "${root}/source/rainfall.zip"
case "$stage" in
  features) entry=features; args=(--clean "${PROJECT_ROOT}/steps/clean-all-v1/clean" --output "${root}/data") ;;
  train-calendar|train) entry=train; args=(--data "${root}/data/calendar" --output "${root}/models/calendar" --shuffle-partitions 128) ;;
  train-short-term) entry=train; args=(--data "${root}/data/short_term" --output "${root}/models/short_term" --shuffle-partitions 128) ;;
  compare) entry=compare; args=(--data "${root}/data" --models "${root}/models" --output "${root}/comparison") ;;
  predict-calendar|predict) entry=predict; args=(--model "${root}/models/calendar" --output "${root}/predictions/calendar-$(date -u +%Y%m%dT%H%M%SZ)") ;;
  predict-short-term) entry=predict; args=(--model "${root}/models/short_term" --clean "${PROJECT_ROOT}/steps/clean-all-v1/clean" --output "${root}/predictions/short-term-$(date -u +%Y%m%dT%H%M%SZ)") ;;
  *) echo 'Stage must be features, train-calendar, train-short-term, compare, predict-calendar or predict-short-term' >&2; exit 2 ;;
esac
gcloud storage cp "jobs/${entry}.py" "${root}/source/${entry}.py"
gcloud dataproc jobs submit pyspark "${root}/source/${entry}.py" \
  --project "$PROJECT_ID" --region "$REGION" --cluster "$CLUSTER" \
  --py-files "${root}/source/rainfall.zip" \
  --properties 'spark.sql.session.timeZone=Asia/Singapore,spark.driver.memory=6g,spark.driver.maxResultSize=1g' \
  -- "${args[@]}" "$@"
