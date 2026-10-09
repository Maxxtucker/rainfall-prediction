#!/usr/bin/env bash
# Local Spark semantic checks. On Dataproc submit jobs/smoke_test.py
# with --py-files dist/rainfall.zip.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export PYTHONPATH="$ROOT/src:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export SPARK_LOCAL_MASTER="${SPARK_LOCAL_MASTER:-local[2]}"
python3 "$ROOT/jobs/smoke_test.py"
