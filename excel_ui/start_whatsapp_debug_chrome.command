#!/bin/bash

set -euo pipefail

CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CDP_ENDPOINT_IPV4="http://127.0.0.1:9222/json/version"
CDP_ENDPOINT_IPV6="http://[::1]:9222/json/version"
SOURCE_USER_DATA_DIR="${HOME}/Library/Application Support/Google/Chrome"
DEBUG_USER_DATA_DIR="${HOME}/Library/Application Support/Google/Chrome-WhatsAppDebug"
PROFILE_NAME="Universal"
PROFILE_DIR="Profile 2"
WHATSAPP_URL="https://web.whatsapp.com"
MAX_WAIT_SECONDS=60
SHUTDOWN_WAIT_SECONDS=20

cdp_live() {
  curl -fsS "${CDP_ENDPOINT_IPV4}" 2>/dev/null | grep -q 'webSocketDebuggerUrl' \
    || curl -g -fsS "${CDP_ENDPOINT_IPV6}" 2>/dev/null | grep -q 'webSocketDebuggerUrl'
}

debug_proc_live() {
  pgrep -f -- '--remote-debugging-port=9222' >/dev/null 2>&1
}

wait_for_debug_shutdown() {
  for _ in $(seq 1 "${SHUTDOWN_WAIT_SECONDS}"); do
    if ! debug_proc_live; then
      return 0
    fi
    sleep 1
  done
  return 1
}

echo "========================================"
echo "  WhatsApp Debug Chrome"
echo "========================================"
echo ""
echo "Profile name: ${PROFILE_NAME}"
echo "Profile dir: ${PROFILE_DIR}"
echo "CDP endpoints:"
echo "  ${CDP_ENDPOINT_IPV4}"
echo "  ${CDP_ENDPOINT_IPV6}"
echo "Source user data dir: ${SOURCE_USER_DATA_DIR}"
echo "Debug user data dir: ${DEBUG_USER_DATA_DIR}"
echo ""

if [ ! -x "${CHROME_BIN}" ]; then
  echo "Google Chrome binary not found: ${CHROME_BIN}"
  exit 1
fi

if cdp_live; then
  echo "Chrome debug endpoint is already live."
  echo "You can run the WhatsApp sender now."
  exit 0
fi

if [ ! -d "${SOURCE_USER_DATA_DIR}/${PROFILE_DIR}" ]; then
  echo "Source Chrome profile not found: ${SOURCE_USER_DATA_DIR}/${PROFILE_DIR}"
  exit 1
fi

echo "Preparing dedicated debug profile..."
mkdir -p "${DEBUG_USER_DATA_DIR}"
if [ ! -d "${DEBUG_USER_DATA_DIR}/${PROFILE_DIR}" ]; then
  if [ -f "${SOURCE_USER_DATA_DIR}/Local State" ]; then
    cp -f "${SOURCE_USER_DATA_DIR}/Local State" "${DEBUG_USER_DATA_DIR}/Local State"
  fi
  rsync -a --delete \
    --exclude='Cache/' \
    --exclude='Code Cache/' \
    --exclude='GPUCache/' \
    --exclude='GrShaderCache/' \
    --exclude='GraphiteDawnCache/' \
    --exclude='Dawn*' \
    --exclude='ShaderCache/' \
    --exclude='Crashpad/' \
    --exclude='BrowserMetrics*' \
    --exclude='Safe Browsing*' \
    "${SOURCE_USER_DATA_DIR}/${PROFILE_DIR}/" \
    "${DEBUG_USER_DATA_DIR}/${PROFILE_DIR}/"
else
  echo "Existing dedicated debug profile found; preserving it."
fi

if debug_proc_live; then
  echo "Stopping stale debug Chrome session on port 9222..."
  pkill -f -- '--remote-debugging-port=9222' || true
  if ! wait_for_debug_shutdown; then
    echo "Timed out waiting for the old debug Chrome session to fully exit."
    echo "Close the debug Chrome window and retry."
    exit 1
  fi
fi

open -na "Google Chrome" --args \
  --remote-debugging-port=9222 \
  --remote-allow-origins=* \
  --user-data-dir="${DEBUG_USER_DATA_DIR}" \
  --profile-directory="${PROFILE_DIR}" \
  "${WHATSAPP_URL}"

echo "Launching Chrome..."
for _ in $(seq 1 "${MAX_WAIT_SECONDS}"); do
  if cdp_live; then
    echo "Chrome debug endpoint is live."
    echo "Open WhatsApp Web in the ${PROFILE_NAME} profile and keep that window open."
    exit 0
  fi
  sleep 1
done

echo "Chrome launched, but the debug endpoint is still unavailable."
echo "CDP bootstrap is still pending or blocked. This does not by itself mean WhatsApp is logged out."
echo "Check that Chrome opened in profile ${PROFILE_NAME} (${PROFILE_DIR}) under:"
echo "  ${DEBUG_USER_DATA_DIR}"
echo "If WhatsApp login is missing, complete login once in this dedicated debug profile and retry."
exit 1
