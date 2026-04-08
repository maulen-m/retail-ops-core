#!/bin/bash

set -euo pipefail

CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CDP_ENDPOINT="http://127.0.0.1:9222/json/version"
USER_DATA_DIR="${HOME}/Library/Application Support/Google/Chrome"
PROFILE_NAME="Universal"
PROFILE_DIR="Profile 2"
WHATSAPP_URL="https://web.whatsapp.com"

echo "========================================"
echo "  WhatsApp Debug Chrome"
echo "========================================"
echo ""
echo "Profile name: ${PROFILE_NAME}"
echo "Profile dir: ${PROFILE_DIR}"
echo "CDP endpoint: ${CDP_ENDPOINT}"
echo ""

if [ ! -x "${CHROME_BIN}" ]; then
  echo "Google Chrome binary not found: ${CHROME_BIN}"
  exit 1
fi

if curl -fsS "${CDP_ENDPOINT}" >/dev/null 2>&1; then
  echo "Chrome debug endpoint is already live."
  echo "You can run the WhatsApp sender now."
  exit 0
fi

if pgrep -x "Google Chrome" >/dev/null 2>&1; then
  echo "Google Chrome is already running without the debug endpoint."
  echo "Close the normal Chrome session first, then rerun this helper."
  echo ""
  echo "After Chrome is closed, this helper will relaunch it with:"
  echo "  --remote-debugging-port=9222"
  echo "  --profile-directory=${PROFILE_DIR}"
  exit 1
fi

open -na "Google Chrome" --args \
  --remote-debugging-port=9222 \
  --user-data-dir="${USER_DATA_DIR}" \
  --profile-directory="${PROFILE_DIR}" \
  "${WHATSAPP_URL}"

echo "Launching Chrome..."
sleep 3

if curl -fsS "${CDP_ENDPOINT}" >/dev/null 2>&1; then
  echo "Chrome debug endpoint is live."
  echo "Open WhatsApp Web in the ${PROFILE_NAME} profile and keep that window open."
  exit 0
fi

echo "Chrome launched, but the debug endpoint is still unavailable."
echo "Check that Chrome opened in profile ${PROFILE_NAME} (${PROFILE_DIR}) and retry."
exit 1
