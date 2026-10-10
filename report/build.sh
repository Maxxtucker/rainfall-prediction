#!/usr/bin/env bash
# Assemble saved results and compile the canonical report; no training or cloud calls.
set -euo pipefail
REPORT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 "$REPORT_DIR/../scripts/build_project_report.py"
cd -- "$REPORT_DIR"
for pass in 1 2; do
  xelatex -interaction=nonstopmode -halt-on-error project_report.tex
done
