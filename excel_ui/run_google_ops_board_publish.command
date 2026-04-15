#!/bin/bash
# Publish the Google Ops Board from current DB truth.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"
source .venv/bin/activate 2>/dev/null || true

SERVICE_JSON="${AB_GOOGLE_SERVICE_ACCOUNT_JSON:-~/Docs/Business/S/ab-ops-board-sync-key.json}"

echo "========================================"
echo "  Google Ops Board Publish"
echo "========================================"
echo ""

python3 scripts/check_local_app_db.py --db-path "${PROJECT_ROOT}/db/app.db"
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: local DB preflight failed."
    echo "Press Enter to close..."
    [[ -t 0 ]] && read
    exit 1
fi

if [ ! -f "excel_ui/ActiveOrders/ActiveOrders.xlsx" ]; then
    echo "WARNING: ActiveOrders export missing; publish will use current DB state only."
else
    echo "Refreshing DB order identities from ActiveOrders export..."
    ENABLE_KASPI_ACTIVEORDERS_DB_WRITE=1 \
    AB_GOOGLE_SERVICE_ACCOUNT_JSON="${SERVICE_JSON}" \
    PYTHONUNBUFFERED=1 \
    python3 -u scripts/enrich_kaspi_orders_from_activeorders.py \
        --apply \
        --file "excel_ui/ActiveOrders/ActiveOrders.xlsx" \
        --target-date "$(date +%Y-%m-%d)"
    if [ $? -ne 0 ]; then
        echo ""
        echo "ERROR: ActiveOrders DB enrichment failed."
        echo "Press Enter to close..."
        [[ -t 0 ]] && read
        exit 1
    fi
fi

if [ ! -f "${SERVICE_JSON}" ]; then
    echo ""
    echo "ERROR: Google service-account JSON missing: ${SERVICE_JSON}"
    echo "Press Enter to close..."
    [[ -t 0 ]] && read
    exit 1
fi

ENABLE_GOOGLE_OPS_BOARD_WRITE=1 \
AB_GOOGLE_SERVICE_ACCOUNT_JSON="${SERVICE_JSON}" \
PYTHONUNBUFFERED=1 \
python3 -u scripts/sync_google_ops_board.py \
    --apply \
    --target-date "$(date +%Y-%m-%d)" \
    --service-account-json "${SERVICE_JSON}"
RC=$?

echo ""
if [ ${RC} -ne 0 ]; then
    echo "ERROR: Google Ops Board publish failed."
else
    echo "Google Ops Board publish complete."
fi
echo ""
echo "Press Enter to close..."
[[ -t 0 ]] && read
exit ${RC}
