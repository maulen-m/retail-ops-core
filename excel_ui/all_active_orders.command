#!/bin/bash
# ALL Active Orders Import: API → Excel → CRM
# Downloads pending orders with planned ship date >= today (not just exact match)
# Use this when you need to ship orders that were planned for today or earlier
# Double-click to run

cd ~/Docs/Autonomous_business
source .venv/bin/activate 2>/dev/null || true

echo "========================================"
echo "  ALL Active Orders Import"
echo "  (planned ship date >= today)"
echo "========================================"
echo ""

# Step 1: Download pending orders with planned date >= today (14-day lookback)
echo "Step 1: Downloading orders with planned ship date >= today..."
echo "        (includes today + any past due orders)"
echo "----------------------------------------"
python scripts/export_api_orders.py --all-stores --state KASPI_DELIVERY --days 14 --planned-date-gte --no-archive --verbose

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: API export failed!"
    echo "Press Enter to close..."
    [[ -t 0 ]] && read
    exit 1
fi

# Step 2: Import new orders to CRM (skip date filter, stamp all as today)
echo ""
echo "Step 2: Importing new orders to CRM..."
echo "        (all dates, appended as today)"
echo "----------------------------------------"
python scripts/import_orders_to_crm.py --all-dates --verbose

echo ""
echo "========================================"
echo "  Done! Press Enter to close..."
echo "========================================"
echo ""
echo "This imported orders with planned ship date >= today (all appended as today)."
echo "For today-only orders: run_full_import.command"
echo "For status updates: run_status_update.command"
[[ -t 0 ]] && read
