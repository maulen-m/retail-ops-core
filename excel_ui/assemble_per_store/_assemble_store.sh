#!/bin/bash
# Shared assemble logic for per-store commands.

if [ -z "${STORE_NAME:-}" ] || [ -z "${STORE_CODE:-}" ]; then
    echo "ERROR: STORE_NAME/STORE_CODE not set."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"
source .venv/bin/activate 2>/dev/null || true
if [ -f ".env" ]; then
    set -a
    # Skip GMAIL_* entries (contain spaces/parentheses that break `source`)
    source <(grep -v '^GMAIL_' .env)
    set +a
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

# Store-specific fallback if env/config missing
if [ -n "${MERCHANT_UID:-}" ]; then
    VAR_NAME="KASPI_MERCHANT_UID_${STORE_CODE}"
    eval "CURRENT_VAL=\"\${${VAR_NAME}:-}\""
    if [ -z "${CURRENT_VAL}" ]; then
        eval "export ${VAR_NAME}=\"${MERCHANT_UID}\""
    fi
fi

if [ "${ENABLE_KASPI_WRITE}" != "1" ]; then
    echo "ERROR: ENABLE_KASPI_WRITE is not set to 1. Refusing to assemble."
    if [ "${SKIP_WAIT:-0}" != "1" ] && [ -t 0 ]; then
        echo "Press Enter to close..."
        read
    fi
    exit 1
fi

LOOKBACK_DAYS="${KASPI_LOOKBACK_DAYS:-4}"

echo "========================================"
echo "  Kaspi Assemble (${STORE_NAME})"
echo "========================================"
echo ""
echo "Data root: ${DATA_ROOT}"
echo "Lookback days: ${LOOKBACK_DAYS}"
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
python scripts/ship_orders_api.py --verbose --since-days "${LOOKBACK_DAYS}" --store "${STORE_NAME}"

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
