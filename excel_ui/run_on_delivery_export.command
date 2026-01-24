#!/bin/bash
# Export on-delivery Kaspi orders (raw + economics)
# - Fetches shipped-but-not-delivered orders from all stores
# - Writes *_raw.xlsx and *_econ.xlsx to excel_ui/ActiveOrders/on_delivery

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

source .venv/bin/activate 2>/dev/null || true
if [ -f ".env" ]; then
    ENV_EXPORTS=$(python3 - <<'PY'
import shlex
from pathlib import Path

p = Path(".env")
if not p.exists():
    raise SystemExit(0)

for raw in p.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("GMAIL_"):
        continue
    if "=" not in line:
        continue
    key, val = line.split("=", 1)
    key = key.strip()
    if not key:
        continue
    print(f"export {key}={shlex.quote(val.strip())}")
PY
)
    if [ -n "${ENV_EXPORTS}" ]; then
        eval "${ENV_EXPORTS}"
    fi
fi

if [ -z "${AB_DATA_DIR:-}" ] && [ -z "${DATA_DIR:-}" ]; then
    export DATA_DIR="${PROJECT_ROOT}"
fi
DATA_ROOT="${AB_DATA_DIR:-${DATA_DIR:-${PROJECT_ROOT}}}"

LOOKBACK_DAYS="${KASPI_ON_DELIVERY_LOOKBACK_DAYS:-${KASPI_LOOKBACK_DAYS_LONG:-14}}"

echo "========================================"
echo "  On-Delivery Orders Export"
echo "========================================"
echo ""
echo "Lookback days: ${LOOKBACK_DAYS}"
echo "Output dir: ${DATA_ROOT}/excel_ui/ActiveOrders/on_delivery"
echo ""

python scripts/export_on_delivery_with_econ.py \
    --days "${LOOKBACK_DAYS}" \
    --output-dir "${DATA_ROOT}/excel_ui/ActiveOrders/on_delivery" \
    --verbose

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: On-delivery export failed!"
    echo "Press Enter to close..."
    [[ -t 0 ]] && read
    exit 1
fi

echo ""
echo "Done."
