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

echo "========================================"
echo "  Full Waybill Workflow"
echo "========================================"
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
echo ""
echo "Press Enter to close..."
read
