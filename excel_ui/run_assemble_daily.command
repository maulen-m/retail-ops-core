#!/bin/bash
# Daily assembly for all stores (set package count).

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

# Merchant UID headers (store-specific). Prefer config/kaspi_stores.yaml when available.
MERCHANT_EXPORTS=$(python3 - <<'PY' 2>/dev/null
from pathlib import Path
import sys
try:
    import yaml
except Exception:
    sys.exit(0)

config_path = Path("config/kaspi_stores.yaml")
if not config_path.exists():
    sys.exit(0)

config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
stores = config.get("stores") or {}
for store_code, info in stores.items():
    if not isinstance(info, dict):
        continue
    uid = info.get("merchant_uid") or info.get("account_id")
    if uid:
        print(f'export KASPI_MERCHANT_UID_{store_code.upper()}="{uid}"')
PY
)
if [ -n "${MERCHANT_EXPORTS}" ]; then
    eval "${MERCHANT_EXPORTS}"
fi

if [ "${ENABLE_KASPI_WRITE}" != "1" ]; then
    echo "ERROR: ENABLE_KASPI_WRITE is not set to 1. Refusing to assemble."
    if [ "${SKIP_WAIT:-0}" != "1" ] && [ -t 0 ]; then
        echo "Press Enter to close..."
        read
    fi
    exit 1
fi

ASSEMBLE_EXTRA_ARGS=()
if [ -n "${KASPI_ASSEMBLE_SINCE_DAYS:-}" ]; then
    echo "Using creation-date lookback override: ${KASPI_ASSEMBLE_SINCE_DAYS} days"
    ASSEMBLE_EXTRA_ARGS+=(--since-days "${KASPI_ASSEMBLE_SINCE_DAYS}")
else
    echo "Running in status-first mode (no creation-date lookback filter)."
fi
ASSEMBLE_OVERDUE_LOOKBACK_DAYS="${KASPI_ASSEMBLE_OVERDUE_LOOKBACK_DAYS:-${KASPI_ASSEMBLE_SINCE_DAYS:-5}}"
echo "Carry-forward mode enabled: overdue pending orders stay in queue for ${ASSEMBLE_OVERDUE_LOOKBACK_DAYS} days."
ASSEMBLE_EXTRA_ARGS+=(--include-overdue --overdue-lookback-days "${ASSEMBLE_OVERDUE_LOOKBACK_DAYS}")

echo "========================================"
echo "  Kaspi Assemble (Daily)"
echo "========================================"
echo ""
echo "Data root: ${DATA_ROOT}"
echo ""

if [ "${SKIP_PREFLIGHT:-0}" != "1" ]; then
    echo "Preflight: checking CRM + environment..."
    echo "----------------------------------------"
    python scripts/ops_preflight.py --shipping
    if [ $? -ne 0 ]; then
        echo ""
        echo "ERROR: Preflight failed. Fix issues above and retry."
        if [ "${SKIP_WAIT:-0}" != "1" ] && [ -t 0 ]; then
            echo "Press Enter to close..."
            read
        fi
        exit 1
    fi
    echo ""
fi

echo "Step: Shipping orders (set package count)"
echo "----------------------------------------"
python scripts/ship_orders_api.py --verbose "${ASSEMBLE_EXTRA_ARGS[@]}"

if [ $? -ne 0 ]; then
    echo ""
    echo "WARNING: Ship orders encountered errors (see above)"
fi

echo ""
echo "========================================"
echo "  Assemble Complete!"
echo "========================================"
if [ "${SKIP_WAIT:-0}" != "1" ] && [ -t 0 ]; then
    echo ""
    echo "Press Enter to close..."
    read
fi
