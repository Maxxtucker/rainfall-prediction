#!/usr/bin/env bash
# Usage: bash cloud/06_analyze_only.sh clean-all-v1 task1-v4 [analysis options]
set -euo pipefail
source "$(dirname "$0")/_env.sh"
cd "$RAINFALL_ROOT"
CLEAN_NAME="${1:?Supply cleaning output name}"
RESULT_NAME="${2:?Supply a fresh Task 1 output name}"
shift 2
for VALUE in "$CLEAN_NAME" "$RESULT_NAME"; do
  if [[ ! "$VALUE" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "Names may contain only letters, digits, underscores and hyphens." >&2
    exit 1
  fi
done
RESULT_ROOT="${PROJECT_ROOT}/steps/${RESULT_NAME}"
if gcloud storage ls "${RESULT_ROOT}/" >/dev/null 2>&1; then
  echo "Output exists. Choose a new result name." >&2
  exit 1
fi
python3 scripts/build_package.py
gcloud storage cp dist/rainfall.zip "${RESULT_ROOT}/source/rainfall.zip"
gcloud storage cp jobs/analyze.py "${RESULT_ROOT}/source/analyze.py"
gcloud dataproc jobs submit pyspark "${RESULT_ROOT}/source/analyze.py" \
  --project "$PROJECT_ID" --region "$REGION" --cluster "$CLUSTER" \
  --py-files "${RESULT_ROOT}/source/rainfall.zip" \
  --properties 'spark.driver.memory=6g,spark.driver.maxResultSize=1g' \
  -- --clean "${PROJECT_ROOT}/steps/${CLEAN_NAME}/clean" --output "$RESULT_ROOT" "$@"
echo "Task 1 complete: ${RESULT_ROOT}"
