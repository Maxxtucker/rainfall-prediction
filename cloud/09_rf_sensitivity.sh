#!/usr/bin/env bash
# Validation-only nested-sample RF experiment; existing feature tables are reused.
set -euo pipefail
source "$(dirname "$0")/_env.sh"
cd "$RAINFALL_ROOT"
run="${1:-rf-sensitivity-20261010}"
root="${PROJECT_ROOT}/steps/${run}"
python3 scripts/build_package.py
gcloud storage cp dist/rainfall.zip "${root}/source/rainfall.zip"
gcloud storage cp jobs/rf_sensitivity.py "${root}/source/rf_sensitivity.py"
gcloud dataproc jobs submit pyspark "${root}/source/rf_sensitivity.py" \
  --project "$PROJECT_ID" --region "$REGION" --cluster "$CLUSTER" \
  --py-files "${root}/source/rainfall.zip" \
  --properties 'spark.sql.session.timeZone=Asia/Singapore,spark.driver.memory=6g,spark.driver.maxResultSize=1g' \
  -- --data "${PROJECT_ROOT}/steps/task2-dual-v1/data" \
  --models "${PROJECT_ROOT}/steps/task2-dual-v2/models" --output "$root"
