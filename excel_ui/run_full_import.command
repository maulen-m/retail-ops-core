#!/bin/bash
# Full Kaspi import: API → Excel → CRM
# Downloads orders from Kaspi API and imports to CRM
# Double-click to run

cd ~/Docs/Autonomous_business
source .venv/bin/activate 2>/dev/null || true

echo "========================================"
echo "  Full Kaspi Order Import"
echo "========================================"
echo ""

echo "Step 1: Downloading orders from Kaspi API..."
echo "----------------------------------------"
python scripts/export_api_orders.py --all-stores --state KASPI_DELIVERY --verbose

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: API export failed!"
    echo "Press Enter to close..."
    read
    exit 1
fi

echo ""
echo "Step 2: Importing to CRM..."
echo "----------------------------------------"
python scripts/import_orders_to_crm.py --verbose

# Step 3 is integrated into import script but add fallback sync
# In case import succeeded but sync inside failed
echo ""
echo "Step 3: Verifying Google Drive sync..."
echo "----------------------------------------"
python scripts/sync_to_gdrive.py || echo "WARNING: Google Drive sync may have failed"

echo ""
echo "========================================"
echo "  Done! Press Enter to close..."
echo "========================================"
read
