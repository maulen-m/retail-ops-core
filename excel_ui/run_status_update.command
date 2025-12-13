#!/bin/bash
# Status Update: Fetches latest statuses for last 14 days
# Updates existing orders: Завершен, Отменен, Возвращен
# Run separately from import when you have time (takes ~5-10 min)
# Double-click to run

cd ~/Docs/Autonomous_business
source .venv/bin/activate 2>/dev/null || true

echo "========================================"
echo "  Order Status Update (Last 14 Days)"
echo "========================================"
echo ""
echo "This will fetch and update statuses for:"
echo "  - Завершен (delivered)"
echo "  - Отменен (cancelled)"
echo "  - Возвращен (returned)"
echo ""

# Update order statuses for past 14 days
echo "Updating order statuses..."
echo "----------------------------------------"
python scripts/update_order_statuses.py --days 14 --verbose

if [ $? -ne 0 ]; then
    echo ""
    echo "WARNING: Status update may have failed"
fi

echo ""
echo "========================================"
echo "  Done! Press Enter to close..."
echo "========================================"
[[ -t 0 ]] && read
