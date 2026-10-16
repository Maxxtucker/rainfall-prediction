#!/usr/bin/env bash
# Complete the saved standard RF30 models' calibration/test on an existing cluster.
set -euo pipefail
if [[ $# -ne 1 || ! "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo 'Usage: bash cloud/12_evaluate_rf_sampling.sh NEW_RUN' >&2
  exit 2
fi
run="$1"
source "$(dirname "$0")/_env.sh"
cd "$RAINFALL_ROOT"
root="${PROJECT_ROOT}/steps/${run}"
source_root="${PROJECT_ROOT}/steps/${run}-source"
python3 scripts/build_package.py
gcloud storage cp --if-generation-match=0 dist/rainfall.zip "${source_root}/rainfall.zip"
gcloud storage cp --if-generation-match=0 jobs/evaluate_rf_sampling.py "${source_root}/evaluate_rf_sampling.py"
gcloud dataproc jobs submit pyspark "${source_root}/evaluate_rf_sampling.py" \
  --project "$PROJECT_ID" --region "$REGION" --cluster "$CLUSTER" \
  --py-files "${source_root}/rainfall.zip" \
  --properties 'spark.sql.session.timeZone=Asia/Singapore,spark.driver.memory=6g,spark.driver.maxResultSize=1g' \
  -- --reference-root "${PROJECT_ROOT}/steps/task2-dual-v2/models" \
     --sensitivity-root "${PROJECT_ROOT}/steps/rf-sensitivity-20261010" \
     --data-root "${PROJECT_ROOT}/steps/task2-dual-v1/data" --output "$root"
