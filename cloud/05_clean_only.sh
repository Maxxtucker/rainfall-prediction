#!/usr/bin/env bash
# Submit only cleaning. Usage: bash cloud/05_clean_only.sh 2017 clean2017-v1
# Or: bash cloud/05_clean_only.sh all clean-all-v1
set -euo pipefail
source "$(dirname "$0")/_env.sh"
cd "$RAINFALL_ROOT"
YEAR="${1:?Supply 2017–2024 or all}"
RESULT_NAME="${2:?Supply a fresh output name, e.g. clean2017-v1}"
if [[ ! "$RESULT_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "Output name must contain only letters, digits, hyphens or underscores." >&2
  exit 1
fi
if [[ "$YEAR" == all ]]; then
  RAW_PATH="${PROJECT_ROOT}/raw"
elif [[ "$YEAR" =~ ^(2017|2018|2019|2020|2021|2022|2023|2024)$ ]]; then
  RAW_PATH="${PROJECT_ROOT}/raw/year=${YEAR}"
else
  echo "Year must be 2017–2024 or all." >&2
  exit 1
fi
RESULT_ROOT="${PROJECT_ROOT}/steps/${RESULT_NAME}"
if gcloud storage ls "${RESULT_ROOT}/" >/dev/null 2>&1; then
  echo "Output already exists. Choose a fresh output name." >&2
  exit 1
fi
python3 scripts/build_package.py
gcloud storage cp dist/rainfall.zip "${PROJECT_ROOT}/code/rainfall.zip"
gcloud storage cp jobs/clean.py "${PROJECT_ROOT}/code/jobs/clean.py"
gcloud dataproc jobs submit pyspark "${PROJECT_ROOT}/code/jobs/clean.py" \
  --project "$PROJECT_ID" --region "$REGION" --cluster "$CLUSTER" \
  --py-files "${PROJECT_ROOT}/code/rainfall.zip" \
  --properties 'spark.driver.memory=6g,spark.driver.maxResultSize=1g' \
  -- --raw "$RAW_PATH" --output "$RESULT_ROOT"
echo "Cleaning finished: ${RESULT_ROOT}"
