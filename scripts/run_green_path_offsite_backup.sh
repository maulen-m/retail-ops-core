#!/usr/bin/env bash

set -uo pipefail

ROOT="~/Docs/Autonomous_business"
SRC="~/Backups/green_path/"
VOLUME="/Volumes/Migration_Staging_Overflow"
DEST="${VOLUME}/green_path_backups/"
LOG_DIR="${ROOT}/runtime_logs"
LOG_FILE="${LOG_DIR}/green_path_offsite.log"
LABEL="com.example.green-path-offsite-backup"
RSYNC_BIN="/usr/bin/rsync"

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

  if [[ "${GREEN_PATH_OFFSITE_SUPPRESS_ALERTS:-0}" == "1" ]]; then
    return 0
  fi

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

cycle_count=0
failure_count=0
last_rsync_rc=0

while IFS= read -r -d '' cycle_dir; do
  cycle_name="$(basename "$cycle_dir")"
  if [[ ! "$cycle_name" =~ ^[0-9]{8}_[0-9]{6}$ ]]; then
    continue
  fi

  cycle_count=$((cycle_count + 1))
  "$RSYNC_BIN" -aO --no-links "$cycle_dir/" "${DEST}${cycle_name}/"
  rsync_rc=$?
  if [[ "$rsync_rc" -ne 0 ]]; then
    failure_count=$((failure_count + 1))
    last_rsync_rc="$rsync_rc"
    append_status "FAIL" "reason=rsync_failed rc=${rsync_rc} cycle=${cycle_name} src=${cycle_dir} dest=${DEST}${cycle_name}/"
  fi
done < <(find "$SRC" -mindepth 1 -maxdepth 1 -type d -name '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9]' -print0)

if [[ "$cycle_count" -eq 0 ]]; then
  append_status "SKIP" "reason=no_real_cycle_dirs src=${SRC}"
  exit 0
fi

if [[ "$failure_count" -ne 0 ]]; then
  append_status "FAIL" "reason=rsync_failed failures=${failure_count} last_rc=${last_rsync_rc} src=${SRC} dest=${DEST}"
  send_failure_alert "rsync_failed failures=${failure_count} last_rc=${last_rsync_rc} src=${SRC} dest=${DEST}"
  exit "$last_rsync_rc"
fi

append_status "OK" "cycles=${cycle_count} src=${SRC} dest=${DEST}"
exit 0
