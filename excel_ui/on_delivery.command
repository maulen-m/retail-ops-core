#!/bin/bash
# Export orders currently on delivery (shipped, awaiting customer receipt)
# For accounting: shows items shipped but not yet paid (payment on receipt)
# Double-click to run

cd ~/Docs/Autonomous_business
source .venv/bin/activate 2>/dev/null || true

echo "========================================"
echo "  Export On-Delivery Orders"
echo "  (shipped, awaiting customer receipt)"
echo "========================================"
echo ""

python scripts/export_on_delivery_orders.py --verbose

echo ""
echo "========================================"
echo "  Done! Press Enter to close..."
echo "========================================"
[[ -t 0 ]] && read
