#!/bin/bash
# Full automated waybill workflow:
# 1. Ship orders (set package count via API)
# 2. Download waybills (via API)
# 3. Build waybill bundles
#
# Phase 12: Automated Kaspi shipping workflow
#
# Prerequisites:
#   1. Run import script first (run_import_orders.command)
#   2. Fill MY_SIZE column in SALES_KSP_CRM_V3.xlsx
#   3. Set ENABLE_KASPI_WRITE=1 in .env for shipping

cd ~/Docs/Autonomous_business
source .venv/bin/activate 2>/dev/null || true

if [ -z "${AB_DATA_DIR:-}" ] && [ -z "${DATA_DIR:-}" ]; then
    export DATA_DIR="~/Docs/Autonomous_business"
fi
DATA_ROOT="${AB_DATA_DIR:-${DATA_DIR:-~/Docs/Autonomous_business}}"

echo "========================================"
echo "  Full Waybill Workflow"
echo "========================================"
echo ""
echo "Data root: ${DATA_ROOT}"
echo ""

# Preflight checks (CRM exists, backups, columns, shipping guard)
echo "Preflight: checking CRM + environment..."
echo "----------------------------------------"
python scripts/ops_preflight.py --shipping

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Preflight failed. Fix issues above and retry."
    echo "Press Enter to close..."
    read
    exit 1
fi

echo ""

# Sync CRM manual sizes into DB (safe to re-run)
echo "Sync: CRM manual sizes -> DB..."
echo "----------------------------------------"
python scripts/sync_crm_sizes_to_db.py

if [ $? -ne 0 ]; then
    echo ""
    echo "WARNING: CRM size sync failed (see above)."
    echo "Continuing to shipping step..."
fi

echo ""

# Step 1: Ship orders (set package count)
echo "Step 1: Shipping orders (setting package count)..."
echo "----------------------------------------"
python scripts/ship_orders_api.py --verbose

if [ $? -ne 0 ]; then
    echo ""
    echo "WARNING: Ship orders encountered errors (see above)"
    echo "Continuing to next step..."
fi

echo ""

# Step 2: Download waybills
echo "Step 2: Downloading waybills via API..."
echo "----------------------------------------"
python scripts/download_waybills_api.py --verbose

if [ $? -ne 0 ]; then
    echo ""
    echo "WARNING: Download waybills encountered errors (see above)"
    echo "Continuing to next step..."
fi

echo ""

# Step 3: Build waybill bundles
echo "Step 3: Building waybill bundles..."
echo "----------------------------------------"
python scripts/build_daily_waybills.py --verbose

echo ""
echo "========================================"
echo "  Workflow Complete!"
echo "========================================"
echo "Output folder: excel_ui/Kaspi_orders/Today/"
echo "Output folder (resolved): ${DATA_ROOT}/excel_ui/Kaspi_orders/Today/"
echo ""
echo "Press Enter to close..."
read
