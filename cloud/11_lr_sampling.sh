#!/usr/bin/env bash
# Separate LR-only follow-up on an existing Dataproc cluster.
set -euo pipefail
if [[ $# -ne 1 || ! "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo 'Usage: bash cloud/11_lr_sampling.sh NEW_RUN' >&2
  exit 2
fi
run="$1"
source "$(dirname "$0")/_env.sh"
cd "$RAINFALL_ROOT"
root="${PROJECT_ROOT}/steps/${run}"
source_root="${PROJECT_ROOT}/steps/${run}-source"
# The training job rejects any existing output root. Generation preconditions
# also prevent replacing previously uploaded source/code packages.
python3 scripts/build_package.py
gcloud storage cp --if-generation-match=0 dist/rainfall.zip "${source_root}/rainfall.zip"
gcloud storage cp --if-generation-match=0 jobs/train_lr_sampling.py "${source_root}/train_lr_sampling.py"
gcloud dataproc jobs submit pyspark "${source_root}/train_lr_sampling.py" \
  --project "$PROJECT_ID" --region "$REGION" --cluster "$CLUSTER" \
  --py-files "${source_root}/rainfall.zip" \
  --properties 'spark.sql.session.timeZone=Asia/Singapore,spark.driver.memory=6g,spark.driver.maxResultSize=1g' \
  -- --reference-root "${PROJECT_ROOT}/steps/task2-dual-v2/models" \
     --data-root "${PROJECT_ROOT}/steps/task2-dual-v1/data" \
     --output "$root" --train-fraction 0.30
