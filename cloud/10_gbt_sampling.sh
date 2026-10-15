#!/usr/bin/env bash
# One supplementary threshold-conditioned GBT run on an existing cluster.
set -euo pipefail
if [[ $# -ne 3 || ! "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo 'Usage: bash cloud/10_gbt_sampling.sh NEW_RUN calendar|short_term 0.15|0.30|1.0' >&2
  exit 2
fi
run="$1"; mode="$2"; fraction="$3"
case "$mode" in calendar|short_term) ;; *) exit 2 ;; esac
case "$fraction" in 0.15|0.30|0.3|1.0|1) ;; *) exit 2 ;; esac
source "$(dirname "$0")/_env.sh"
cd "$RAINFALL_ROOT"
root="${PROJECT_ROOT}/steps/${run}"
source_root="${PROJECT_ROOT}/steps/${run}-source"
reference="${RAINFALL_GBT_REFERENCE_MODELS:-${PROJECT_ROOT}/steps/task2-dual-v2/models}/${mode}"
data="${RAINFALL_GBT_DATA:-${PROJECT_ROOT}/steps/task2-dual-v1/data}/${mode}"
existing_steps=$(gcloud storage ls "${PROJECT_ROOT}/steps/")
while IFS= read -r entry; do
  entry="${entry%:}"; entry="${entry%/}"
  if [[ "$entry" == "$root" || "$entry" == "$source_root" ]]; then
    echo 'Run or source path exists; choose a fresh run name.' >&2
    exit 1
  fi
done <<< "$existing_steps"
python3 scripts/build_package.py
gcloud storage cp --if-generation-match=0 dist/rainfall.zip "${source_root}/rainfall.zip"
gcloud storage cp --if-generation-match=0 jobs/train_gbt_sampling.py "${source_root}/train_gbt_sampling.py"
gcloud dataproc jobs submit pyspark "${source_root}/train_gbt_sampling.py" \
  --project "$PROJECT_ID" --region "$REGION" --cluster "$CLUSTER" \
  --py-files "${source_root}/rainfall.zip" \
  --properties 'spark.sql.session.timeZone=Asia/Singapore,spark.driver.memory=6g,spark.driver.maxResultSize=1g' \
  -- --reference-model "$reference" --data "$data" --output "$root" \
     --train-fraction "$fraction" --depths '3,5' --iterations 40
