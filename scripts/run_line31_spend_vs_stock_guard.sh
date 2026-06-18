#!/usr/bin/env bash

set -euo pipefail

ROOT="~/Docs/Autonomous_business"
PYTHON_BIN="${ROOT}/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

RUN_ID="${LINE31_SPEND_STOCK_RUN_ID:-$(date '+%Y%m%d_%H%M%S')_scheduled}"

cd "$ROOT"
exec "$PYTHON_BIN" scripts/report_line31_spend_vs_stock_guard.py \
  --strict \
  --json \
  --run-id "$RUN_ID"
