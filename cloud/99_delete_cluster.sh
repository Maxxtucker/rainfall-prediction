#!/usr/bin/env bash
# Deletes only the named Spark cluster, preserving the project bucket/results.
set -euo pipefail
source "$(dirname "$0")/_env.sh"
gcloud dataproc clusters delete "$CLUSTER" --project "$PROJECT_ID" --region "$REGION"

