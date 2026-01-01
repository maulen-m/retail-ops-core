#!/bin/bash
# Import Kaspi ActiveOrders to CRM (xlwings version)
# Double-click to run

cd ~/Docs/Autonomous_business
source .venv/bin/activate 2>/dev/null || true

echo "========================================"
echo "  Kaspi Order Import"
echo "========================================"
echo ""

python scripts/import_orders_to_crm.py --verbose

echo ""
echo "========================================"
echo "  Done! Press Enter to close..."
echo "========================================"
read
