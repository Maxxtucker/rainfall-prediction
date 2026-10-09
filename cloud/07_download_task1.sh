#!/usr/bin/env bash
# Download one Task 1 run to this local checkout; preserves other runs.
set -euo pipefail
source "$(dirname "$0")/_env.sh"
RESULT_NAME="${1:?Usage: bash cloud/07_download_task1.sh task1-v5}"
if [[ ! "$RESULT_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "Invalid result name" >&2
  exit 1
fi
SOURCE="${PROJECT_ROOT}/steps/${RESULT_NAME}"
TARGET="${RAINFALL_ROOT}/outputs/steps/${RESULT_NAME}"
# analyze.py writes metadata only after every aggregate table is saved.
gcloud storage ls "${SOURCE}/metadata/_SUCCESS" >/dev/null
mkdir -p "$TARGET"
gcloud storage rsync --recursive "$SOURCE" "$TARGET"
echo "Downloaded Task 1 run to ${TARGET}"
