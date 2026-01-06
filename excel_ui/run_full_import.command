#!/bin/bash
# FAST Kaspi import: API → Excel → CRM (no status updates)
# Downloads TODAY's pending orders from Kaspi API, imports to CRM
# For status updates, use run_status_update.command separately
# Double-click to run

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"
source .venv/bin/activate 2>/dev/null || true
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

if [ -z "${AB_DATA_DIR:-}" ] && [ -z "${DATA_DIR:-}" ]; then
    export DATA_DIR="${PROJECT_ROOT}"
fi
DATA_ROOT="${AB_DATA_DIR:-${DATA_DIR:-${PROJECT_ROOT}}}"

if [ -z "${AB_GDRIVE_KASPI_SALES_PATH:-}" ]; then
    export AB_GDRIVE_KASPI_SALES_PATH="${HOME}/Library/CloudStorage/GoogleDrive-maintainer@example.com/My Drive/Business/Shared/Kaspi/Kaspi orders/Kaspi_drive_sales_v1.xlsx"
fi

DEFAULT_LOOKBACK_DAYS=5
LONG_LOOKBACK_DAYS="${KASPI_LOOKBACK_DAYS_LONG:-14}"
LOOKBACK_DAYS="${KASPI_LOOKBACK_DAYS:-}"
if [ -z "${LOOKBACK_DAYS}" ]; then
    CURRENT_HOUR=$(TZ=Asia/Almaty date +%H)
    CURRENT_MIN=$(TZ=Asia/Almaty date +%M)
    CURRENT_HOUR=$((10#${CURRENT_HOUR}))
    CURRENT_MIN=$((10#${CURRENT_MIN}))
    if [ "${CURRENT_HOUR}" -gt 20 ] || { [ "${CURRENT_HOUR}" -eq 20 ] && [ "${CURRENT_MIN}" -ge 30 ]; }; then
        LOOKBACK_DAYS="${LONG_LOOKBACK_DAYS}"
    else
        LOOKBACK_DAYS="${DEFAULT_LOOKBACK_DAYS}"
    fi
fi

WARNINGS=()

echo "========================================"
echo "  FAST Kaspi Order Import"
echo "  (no archive fetch, no status updates)"
echo "========================================"
echo ""
echo "Lookback days: ${LOOKBACK_DAYS}"
echo ""

# Step 1: Download pending orders for TODAY (no archive for speed)
echo "Step 1: Downloading TODAY's pending orders from Kaspi API..."
echo "----------------------------------------"
python scripts/export_api_orders.py --all-stores --state KASPI_DELIVERY --days "${LOOKBACK_DAYS}" --refetch-missing-costs --verbose --no-archive

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: API export failed!"
    echo "Press Enter to close..."
    [[ -t 0 ]] && read
    exit 1
fi

# Quick sanity check on exported ActiveOrders
if [ -f "excel_ui/ActiveOrders/ActiveOrders.xlsx" ]; then
    python - <<'PY'
import pandas as pd
from pathlib import Path
p = Path("excel_ui/ActiveOrders/ActiveOrders.xlsx")
try:
    df = pd.read_excel(p)
    print(f"ActiveOrders rows: {len(df)}")
    if len(df) == 0:
        raise SystemExit(2)
except Exception:
    raise SystemExit(3)
PY
    RC=$?
    if [ $RC -eq 2 ]; then
        echo "WARNING: ActiveOrders.xlsx has 0 rows after export."
        WARNINGS+=("ActiveOrders export returned 0 rows. Fix: check Kaspi planned date filter or API connectivity.")
    elif [ $RC -eq 3 ]; then
        echo "WARNING: ActiveOrders.xlsx could not be read."
        WARNINGS+=("ActiveOrders.xlsx unreadable. Fix: re-export or open/save the file.")
    fi
fi

# Step 1b: Sync DB from API + ActiveOrders (order lifecycle + line items)
echo ""
echo "Step 1b: Syncing DB from API + ActiveOrders..."
echo "----------------------------------------"
SINCE_DATE=$(date -v-"${LOOKBACK_DAYS}"d +%Y-%m-%d)
python scripts/sync_kaspi_orders.py --all --since "$SINCE_DATE"
if [ $? -ne 0 ]; then
    echo "WARNING: API -> DB sync failed (see above)."
    WARNINGS+=("API -> DB sync failed. Fix: check tokens/network, then re-run.")
fi
if [ -f "excel_ui/ActiveOrders/ActiveOrders.xlsx" ]; then
    echo "Preflight: checking ActiveOrders columns..."
    python scripts/validate_activeorders_columns.py excel_ui/ActiveOrders/ActiveOrders.xlsx
    if [ $? -ne 0 ]; then
        echo "WARNING: ActiveOrders columns mismatch (see above)."
        WARNINGS+=("ActiveOrders columns mismatch. Fix: re-export ActiveOrders from Kaspi.")
    fi
    python scripts/ingest_kaspi_export.py excel_ui/ActiveOrders/ActiveOrders.xlsx
    if [ $? -ne 0 ]; then
        echo "WARNING: ActiveOrders -> DB ingest failed (see above)."
        WARNINGS+=("ActiveOrders ingest failed. Fix: check ActiveOrders columns or re-export.")
    fi
else
    echo "WARNING: ActiveOrders.xlsx not found; skipping ActiveOrders -> DB ingest."
    WARNINGS+=("ActiveOrders.xlsx missing. Fix: re-run export_api_orders step.")
fi

# Step 2: Import new orders to CRM (also updates existing order status columns)
echo ""
echo "Step 2: Importing new orders to CRM..."
echo "----------------------------------------"
python scripts/import_orders_to_crm.py --verbose
if [ $? -ne 0 ]; then
    echo "WARNING: CRM import reported errors (see above)."
    WARNINGS+=("CRM import errors. Fix: open CRM and re-run import_orders_to_crm.py --verbose.")
fi

# Step 2b: Validate pending orders alignment (CRM vs DB/ActiveOrders)
echo ""
echo "Step 2b: Validating pending orders..."
echo "----------------------------------------"
python scripts/validate_pending_orders.py
if [ $? -ne 0 ]; then
    echo "WARNING: Pending order validation reported mismatches (see above)"
    WARNINGS+=("Pending order validation mismatches. Fix: check ActiveOrders export + CRM planned date column.")
fi

# Post-import health report (API vs CRM vs DB)
echo ""
echo "Post-import health report..."
echo "----------------------------------------"
python scripts/report_import_status.py --since-days "${LOOKBACK_DAYS}"

# Step 3: Google Drive sync (handled automatically within import_orders_to_crm.py)
echo ""
echo "Step 3: Google Drive sync was performed during import (if rows were added)"
echo "----------------------------------------"
echo "Note: New rows synced to 'sales_kaspi_drive' sheet, 'drive' table"

echo ""
echo "========================================"
echo "  Done!"
echo "========================================"
echo ""
echo "For status updates (Завершен, Отменен, Возвращен):"
echo "  Run: run_status_update.command"
if [ ${#WARNINGS[@]} -ne 0 ]; then
    echo ""
    echo "Warnings summary:"
    for w in "${WARNINGS[@]}"; do
        echo "  - ${w}"
    done
fi
echo ""
echo "Press Enter to close..."
[[ -t 0 ]] && read
exit 0
