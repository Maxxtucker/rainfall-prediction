#!/usr/bin/env bash
# Shared validation only; does not create cloud resources.
RAINFALL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAINFALL_ENV_FILE="${RAINFALL_ENV_FILE:-${RAINFALL_ROOT}/cloud/env.sh}"
if [[ ! -f "$RAINFALL_ENV_FILE" ]]; then
  echo "First copy cloud/env.example to cloud/env.sh and edit PROJECT_ID and BUCKET." >&2
  exit 1
fi
source "$RAINFALL_ENV_FILE"
: "${PROJECT_ID:?Set PROJECT_ID}" "${BUCKET:?Set BUCKET}" "${REGION:?Set REGION}"
if [[ "$PROJECT_ID" == YOUR_* || "$BUCKET" == YOUR_* || "$BUCKET" == gs://* ]]; then
  echo "Edit PROJECT_ID and BUCKET in cloud/env.sh; BUCKET must not begin with gs://." >&2
  exit 1
fi
export SERVICE_ACCOUNT="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
export GCS_ROOT="gs://${BUCKET}"
export PROJECT_ROOT="${GCS_ROOT}/project"
export OUTPUT_ROOT="${PROJECT_ROOT}/runs/${RUN_ID}"
