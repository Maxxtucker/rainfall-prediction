#!/usr/bin/env bash
# Validation-only nested-sample RF experiment; existing feature tables are reused.
set -euo pipefail
if [[ $# -ne 1 || ! "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "Usage: bash cloud/09_rf_sensitivity.sh NEW_RUN_NAME" >&2
  echo "Use a new name containing letters, digits, dots, underscores or hyphens; resume is not supported." >&2
  exit 2
fi
run="$1"
source "$(dirname "$0")/_env.sh"
cd "$RAINFALL_ROOT"
root="${PROJECT_ROOT}/steps/${run}"
data_root="${RAINFALL_SENSITIVITY_DATA:-${PROJECT_ROOT}/steps/task2-dual-v1/data}"
models_root="${RAINFALL_SENSITIVITY_MODELS:-${PROJECT_ROOT}/steps/task2-dual-v2/models}"
# Keep source outside the output root: the Spark job requires a fresh output.
source_root="${PROJECT_ROOT}/steps/${run}-source"
# List the known existing steps parent. Any failure (including denied access)
# aborts; a failed request is never interpreted as a missing run.
if ! existing_steps=$(gcloud storage ls "${PROJECT_ROOT}/steps/"); then
  echo "Cannot confirm that the run and source paths are unused; aborting before upload." >&2
  exit 1
fi
while IFS= read -r entry; do
  entry="${entry%:}"
  entry="${entry%/}"
  if [[ "$entry" == "$root" || "$entry" == "$source_root" ]]; then
    echo "Existing run or source path: ${entry}. Choose a new run name; resume is not supported." >&2
    exit 1
  fi
done <<< "$existing_steps"
python3 scripts/build_package.py
# Generation preconditions also prevent a concurrent invocation from replacing
# these source objects after the preflight listing.
gcloud storage cp --if-generation-match=0 dist/rainfall.zip "${source_root}/rainfall.zip"
gcloud storage cp --if-generation-match=0 jobs/rf_sensitivity.py "${source_root}/rf_sensitivity.py"
gcloud dataproc jobs submit pyspark "${source_root}/rf_sensitivity.py" \
  --project "$PROJECT_ID" --region "$REGION" --cluster "$CLUSTER" \
  --py-files "${source_root}/rainfall.zip" \
  --properties 'spark.sql.session.timeZone=Asia/Singapore,spark.driver.memory=6g,spark.driver.maxResultSize=1g' \
  -- --data "$data_root" --models "$models_root" --output "$root"
