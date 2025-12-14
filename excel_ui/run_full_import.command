#!/bin/bash
# FAST Kaspi import: API → Excel → CRM (no status updates)
# Downloads TODAY's pending orders from Kaspi API, imports to CRM
# For status updates, use run_status_update.command separately
# Double-click to run

cd ~/Docs/Autonomous_business
source .venv/bin/activate 2>/dev/null || true

echo "========================================"
echo "  FAST Kaspi Order Import"
echo "  (no archive fetch, no status updates)"
echo "========================================"
echo ""

# Step 1: Download pending orders for TODAY (no archive for speed)
echo "Step 1: Downloading TODAY's pending orders from Kaspi API..."
echo "----------------------------------------"
python scripts/export_api_orders.py --all-stores --state KASPI_DELIVERY --days 2 --no-archive --verbose

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: API export failed!"
    echo "Press Enter to close..."
    [[ -t 0 ]] && read
    exit 1
fi

# Step 2: Import new orders to CRM (also updates existing order status columns)
echo ""
echo "Step 2: Importing new orders to CRM..."
echo "----------------------------------------"
python scripts/import_orders_to_crm.py --verbose

# Step 3: Google Drive sync (handled automatically within import_orders_to_crm.py)
echo ""
echo "Step 3: Google Drive sync was performed during import (if rows were added)"
echo "----------------------------------------"
echo "Note: New rows synced to 'sales_kaspi_drive' sheet, 'drive' table"

echo ""
echo "========================================"
echo "  Done! Press Enter to close..."
echo "========================================"
echo ""
echo "For status updates (Завершен, Отменен, Возвращен):"
echo "  Run: run_status_update.command"
[[ -t 0 ]] && read
