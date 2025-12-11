#!/bin/bash
# WhatsApp PDF Sender for Kaspi Waybills
# Double-click to run

cd ~/Docs/Autonomous_business
source .venv/bin/activate 2>/dev/null || true

echo "========================================"
echo "  WhatsApp PDF Sender"
echo "========================================"
echo ""
echo "This will send waybill PDFs to WhatsApp."
echo "Make sure WhatsApp Web is logged in before proceeding."
echo ""
echo "Press Enter to start or Ctrl+C to cancel..."
read

python scripts/send_waybills_whatsapp.py --verbose

echo ""
echo "========================================"
echo "  Done! Press Enter to close..."
echo "========================================"
read
