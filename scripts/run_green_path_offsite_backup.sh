#!/usr/bin/env bash

set -uo pipefail

ROOT="~/Docs/Autonomous_business"
SRC="~/Backups/green_path/"
VOLUME="/Volumes/Migration_Staging_Overflow"
DEST="${VOLUME}/green_path_backups/"
LOG_DIR="${ROOT}/runtime_logs"
LOG_FILE="${LOG_DIR}/green_path_offsite.log"
LABEL="com.example.green-path-offsite-backup"

timestamp_utc() {
  date -u "+%Y-%m-%dT%H:%M:%SZ"
}

append_status() {
  local status="$1"
  local detail="${2:-}"
  mkdir -p "$LOG_DIR"
  printf "%s label=%s status=%s %s\n" "$(timestamp_utc)" "$LABEL" "$status" "$detail" >> "$LOG_FILE"
}

send_failure_alert() {
  local reason="$1"
  local python_bin="${ROOT}/.venv/bin/python"

  if [[ ! -x "$python_bin" ]]; then
    python_bin="python3"
  fi

  if [[ -f "${ROOT}/scripts/load_dotenv.sh" ]]; then
    # shellcheck source=/dev/null
    source "${ROOT}/scripts/load_dotenv.sh"
    load_dotenv "${ROOT}/.env"
  fi

  (cd "$ROOT" && "$python_bin" - "$reason" <<'PY') >/dev/null 2>&1 || true
import sys
from core.alerts.error_alerts import send_run_failure_alert

reason = sys.argv[1]
send_run_failure_alert(
    error_message=f"green_path offsite backup failed: {reason}",
    script_name="green_path_offsite_backup",
    context="src=~/Backups/green_path/ dest=/Volumes/Migration_Staging_Overflow/green_path_backups/",
)
PY
}

if [[ ! -d "$VOLUME" ]]; then
  append_status "SKIP" "reason=volume_absent volume=${VOLUME}"
  exit 0
fi

if [[ ! -d "$SRC" ]]; then
  append_status "FAIL" "reason=source_absent src=${SRC}"
  send_failure_alert "source_absent src=${SRC}"
  exit 2
fi

mkdir -p "$DEST"
mkdir_rc=$?
if [[ "$mkdir_rc" -ne 0 ]]; then
  append_status "FAIL" "reason=dest_mkdir_failed rc=${mkdir_rc} dest=${DEST}"
  send_failure_alert "dest_mkdir_failed rc=${mkdir_rc} dest=${DEST}"
  exit "$mkdir_rc"
fi

/usr/bin/rsync -a "$SRC" "$DEST"
rsync_rc=$?
if [[ "$rsync_rc" -ne 0 ]]; then
  append_status "FAIL" "reason=rsync_failed rc=${rsync_rc} src=${SRC} dest=${DEST}"
  send_failure_alert "rsync_failed rc=${rsync_rc} src=${SRC} dest=${DEST}"
  exit "$rsync_rc"
fi

append_status "OK" "src=${SRC} dest=${DEST}"
exit 0
