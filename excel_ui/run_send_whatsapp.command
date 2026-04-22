#!/bin/bash
# WhatsApp PDF Sender for Kaspi Waybills
# Double-click to run

set -euo pipefail

SCRIPT_SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

cd ~/Docs/Autonomous_business
source .venv/bin/activate 2>/dev/null || true

if [ "${AB_GOOGLE_OPS_BOARD_LOCK_HELD:-}" != "1" ]; then
  exec python3 scripts/google_ops_board_lock_exec.py -- "${SCRIPT_SELF}" "$@"
fi

BROWSER_MODE="attach"
CHROME_USER_DATA_DIR="${HOME}/Library/Application Support/Google/Chrome-WhatsAppDebug"
DEBUG_HELPER="~/Docs/Autonomous_business/excel_ui/start_whatsapp_debug_chrome.command"
STOPLINE_PATH="excel_ui/Kaspi_orders/Today/whatsapp_send_stopline.json"
PRE_STATUS_PROBE_PATTERN="Pre-send delivery probe failed"
CDP_ENDPOINT_IPV4="http://127.0.0.1:9222/json/version"
CDP_ENDPOINT_IPV6="http://[::1]:9222/json/version"
RESOLVED_CDP_ENDPOINT="http://127.0.0.1:9222"
CDP_WAIT_SECONDS=45

cdp_live() {
  if curl -fsS "${CDP_ENDPOINT_IPV4}" 2>/dev/null | grep -q 'webSocketDebuggerUrl'; then
    RESOLVED_CDP_ENDPOINT="http://127.0.0.1:9222"
    return 0
  fi
  if curl -g -fsS "${CDP_ENDPOINT_IPV6}" 2>/dev/null | grep -q 'webSocketDebuggerUrl'; then
    RESOLVED_CDP_ENDPOINT="http://[::1]:9222"
    return 0
  fi
  return 1
}

wait_for_cdp() {
  for _ in $(seq 1 "${CDP_WAIT_SECONDS}"); do
    if cdp_live; then
      return 0
    fi
    sleep 1
  done
  return 1
}

echo "========================================"
echo "  WhatsApp PDF Sender"
echo "========================================"
echo ""
echo "This will send waybill PDFs to WhatsApp chat: Заказы."
echo "Safety gate blocks chat: order 2."
echo "Make sure WhatsApp Web is logged in before proceeding."
echo "Production mode: dedicated automation Chrome attach."
echo "Auto-starting automation Chrome with:"
echo "  ${DEBUG_HELPER}"
echo "Running WhatsApp smoke check first..."
echo "Starting immediately..."
echo ""

if ! "${DEBUG_HELPER}"; then
  echo ""
  echo "WARNING: Chrome helper did not confirm DevTools readiness yet."
  echo "Checking the DevTools endpoint directly before failing..."
fi

if ! wait_for_cdp; then
  echo ""
  echo "========================================"
  echo "  Chrome DevTools Bootstrap Failed"
  echo "========================================"
  echo "WhatsApp may still be visibly logged in, but the automation endpoints are not ready:"
  echo "  ${CDP_ENDPOINT_IPV4}"
  echo "  ${CDP_ENDPOINT_IPV6}"
  echo "No PDFs were sent."
  echo "If WhatsApp shows a QR/login screen in the dedicated automation profile, complete login once."
  echo "If WhatsApp is already open and logged in, this is a DevTools/CDP bootstrap problem, not a login problem."
  exit 1
fi

python scripts/send_waybills_whatsapp.py \
  --bundle-source merged \
  --browser-mode "${BROWSER_MODE}" \
  --chrome-user-data-dir "${CHROME_USER_DATA_DIR}" \
  --cdp-endpoint "${RESOLVED_CDP_ENDPOINT}" \
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
  echo "If the failure mentions QR/login screen, complete WhatsApp login once in the dedicated automation profile."
  echo "If the failure mentions DevTools/CDP unavailability, the browser session may still be logged in and the problem is the automation endpoint."
  echo "Helper:"
  echo "  ${DEBUG_HELPER}"
  exit "${SMOKE_RC}"
fi

rm -f "${STOPLINE_PATH}"

python scripts/send_waybills_whatsapp.py \
  --bundle-source merged \
  --browser-mode "${BROWSER_MODE}" \
  --chrome-user-data-dir "${CHROME_USER_DATA_DIR}" \
  --cdp-endpoint "${RESOLVED_CDP_ENDPOINT}" \
  --chat-title "Заказы" \
  --forbid-chat "order 2" \
  --linger-seconds 120 \
  --status-messages \
  --fail-fast \
  --verbose
SENDER_RC=$?

if [ "${SENDER_RC}" -ne 0 ] && [ -f "${STOPLINE_PATH}" ] && grep -q "${PRE_STATUS_PROBE_PATTERN}" "${STOPLINE_PATH}"; then
  echo ""
  echo "WARNING: Pre-send status probe drifted. Retrying live send without status messages..."
  rm -f "${STOPLINE_PATH}"

  python scripts/send_waybills_whatsapp.py \
    --bundle-source merged \
    --browser-mode "${BROWSER_MODE}" \
    --chrome-user-data-dir "${CHROME_USER_DATA_DIR}" \
    --cdp-endpoint "${RESOLVED_CDP_ENDPOINT}" \
    --chat-title "Заказы" \
    --forbid-chat "order 2" \
    --linger-seconds 180 \
    --no-status-messages \
    --fail-fast \
    --verbose
  SENDER_RC=$?
fi

echo ""
echo "========================================"
echo "  Done!"
echo "========================================"
exit "${SENDER_RC}"
