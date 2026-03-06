#!/bin/bash
# WhatsApp PDF Sender for Kaspi Waybills
# Double-click to run

cd ~/Docs/Autonomous_business
source .venv/bin/activate 2>/dev/null || true

echo "========================================"
echo "  WhatsApp PDF Sender"
echo "========================================"
echo ""
echo "This will send waybill PDFs to WhatsApp chat: Заказы."
echo "Safety gate blocks chat: order 2."
echo "Make sure WhatsApp Web is logged in before proceeding."
echo "Starting immediately..."
echo ""

python scripts/send_waybills_whatsapp.py \
  --bundle-source merged \
  --chat-title "Заказы" \
  --forbid-chat "order 2" \
  --status-messages \
  --verbose

echo ""
echo "========================================"
echo "  Done!"
echo "========================================"
