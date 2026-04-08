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
echo "Attach mode expects Chrome DevTools on http://127.0.0.1:9222."
echo "If needed, start Chrome with: ~/Docs/Autonomous_business/excel_ui/start_whatsapp_debug_chrome.command"
echo "Running WhatsApp smoke check first..."
echo "Starting immediately..."
echo ""

python scripts/send_waybills_whatsapp.py \
  --bundle-source merged \
  --chat-title "Заказы" \
  --forbid-chat "order 2" \
  --smoke-check-only \
  --verbose
SMOKE_RC=$?

if [ "${SMOKE_RC}" -ne 0 ]; then
  echo ""
  echo "========================================"
  echo "  Smoke Check Failed"
  echo "========================================"
  echo "No PDFs were sent."
  echo "If the failure mentions CDP/debug mode, run:"
  echo "  ~/Docs/Autonomous_business/excel_ui/start_whatsapp_debug_chrome.command"
  exit "${SMOKE_RC}"
fi

python scripts/send_waybills_whatsapp.py \
  --bundle-source merged \
  --chat-title "Заказы" \
  --forbid-chat "order 2" \
  --status-messages \
  --fail-fast \
  --verbose
SENDER_RC=$?

echo ""
echo "========================================"
echo "  Done!"
echo "========================================"
exit "${SENDER_RC}"
