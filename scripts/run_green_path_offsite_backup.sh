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
MOUNT_RETRIES="${GREEN_PATH_OFFSITE_MOUNT_RETRIES:-3}"
MOUNT_RETRY_DELAY_SECONDS="${GREEN_PATH_OFFSITE_MOUNT_RETRY_DELAY_SECONDS:-20}"
EXCLUDED_LATEST_PATTERN="*_LATEST.xlsx"
TMP_FILES=""

timestamp_utc() {
  date -u "+%Y-%m-%dT%H:%M:%SZ"
}

append_status() {
  local status="$1"
  local detail="${2:-}"
  mkdir -p "$LOG_DIR"
  printf "%s label=%s status=%s %s\n" "$(timestamp_utc)" "$LABEL" "$status" "$detail" >> "$LOG_FILE"
}

make_tmp_file() {
  local tmp_file
  tmp_file="$(mktemp "${TMPDIR:-/tmp}/green_path_offsite.XXXXXX")"
  TMP_FILES="${TMP_FILES} ${tmp_file}"
  printf "%s" "$tmp_file"
}

cleanup_tmp_files() {
  local tmp_file
  for tmp_file in $TMP_FILES; do
    [[ -n "$tmp_file" ]] && rm -f "$tmp_file"
  done
}

trap cleanup_tmp_files EXIT

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

volume_is_mounted() {
  local info

  [[ -d "$VOLUME" ]] || return 1
  info="$(diskutil info "$VOLUME" 2>/dev/null)" || return 1
  printf "%s\n" "$info" | grep -Eq "^[[:space:]]*Mounted:[[:space:]]*Yes$" || return 1
  printf "%s\n" "$info" | grep -Eq "^[[:space:]]*Mount Point:[[:space:]]*${VOLUME}$" || return 1
}

wait_for_volume() {
  local attempt=1

  [[ "$MOUNT_RETRIES" =~ ^[0-9]+$ ]] || MOUNT_RETRIES=3
  [[ "$MOUNT_RETRY_DELAY_SECONDS" =~ ^[0-9]+$ ]] || MOUNT_RETRY_DELAY_SECONDS=20
  [[ "$MOUNT_RETRIES" -ge 1 ]] || MOUNT_RETRIES=1

  while [[ "$attempt" -le "$MOUNT_RETRIES" ]]; do
    if volume_is_mounted; then
      return 0
    fi

    append_status "WAIT" "reason=volume_not_mounted attempt=${attempt}/${MOUNT_RETRIES} volume=${VOLUME}"
    if [[ "$attempt" -lt "$MOUNT_RETRIES" ]]; then
      sleep "$MOUNT_RETRY_DELAY_SECONDS"
    fi
    attempt=$((attempt + 1))
  done

  return 1
}

ensure_dest_writable() {
  local probe_dir

  mkdir -p "$DEST" || return 1
  probe_dir="${DEST}.green_path_write_probe_$$"
  mkdir "$probe_dir" || return 1
  if ! : > "${probe_dir}/probe"; then
    rm -rf "$probe_dir"
    return 1
  fi
  rm -rf "$probe_dir"
}

count_find_results() {
  find "$@" | wc -l | tr -d '[:space:]'
}

rsync_output_has_only_expected_skips() {
  local stdout_file="$1"
  local stderr_file="$2"

  [[ -s "$stdout_file" || -s "$stderr_file" ]] || return 1
  awk '
    NF == 0 { next }
    /^skipping non-regular file ".*_LATEST\.xlsx"$/ { next }
    { bad = 1 }
    END { exit bad ? 1 : 0 }
  ' "$stdout_file" "$stderr_file"
}

emit_rsync_output() {
  local stdout_file="$1"
  local stderr_file="$2"

  [[ -s "$stdout_file" ]] && cat "$stdout_file"
  [[ -s "$stderr_file" ]] && cat "$stderr_file" >&2
}

if ! wait_for_volume; then
  append_status "SKIP" "reason=volume_absent_after_retries retries=${MOUNT_RETRIES} volume=${VOLUME}"
  send_failure_alert "volume_absent_after_retries retries=${MOUNT_RETRIES} volume=${VOLUME}"
  exit 0
fi

if [[ ! -d "$SRC" ]]; then
  append_status "FAIL" "reason=source_absent src=${SRC}"
  send_failure_alert "source_absent src=${SRC}"
  exit 2
fi

if ! ensure_dest_writable; then
  append_status "FAIL" "reason=dest_not_writable dest=${DEST}"
  send_failure_alert "dest_not_writable dest=${DEST}"
  exit 3
fi

cycle_count=0
failure_count=0
last_rsync_rc=0
verified_count=0
skip_only_count=0
latest_symlink_count="$(count_find_results "$SRC" -type l -name "$EXCLUDED_LATEST_PATTERN")"
top_level_symlink_count="$(count_find_results "$SRC" -mindepth 1 -maxdepth 1 -type l)"

while IFS= read -r -d '' cycle_dir; do
  cycle_name="$(basename "$cycle_dir")"
  rsync_stdout="$(make_tmp_file)"
  rsync_stderr="$(make_tmp_file)"
  verify_stdout="$(make_tmp_file)"
  verify_stderr="$(make_tmp_file)"

  if [[ ! "$cycle_name" =~ ^[0-9]{8}_[0-9]{6}$ ]]; then
    continue
  fi

  cycle_count=$((cycle_count + 1))
  "$RSYNC_BIN" -aO --no-links --exclude "$EXCLUDED_LATEST_PATTERN" "$cycle_dir/" "${DEST}${cycle_name}/" >"$rsync_stdout" 2>"$rsync_stderr"
  rsync_rc=$?
  if [[ "$rsync_rc" -ne 0 ]]; then
    if [[ "$rsync_rc" -eq 23 ]] && rsync_output_has_only_expected_skips "$rsync_stdout" "$rsync_stderr"; then
      skip_only_count=$((skip_only_count + 1))
      append_status "WARN" "reason=rsync_skip_only rc=23 cycle=${cycle_name} excluded_pattern=${EXCLUDED_LATEST_PATTERN}"
      continue
    fi

    emit_rsync_output "$rsync_stdout" "$rsync_stderr"
    failure_count=$((failure_count + 1))
    last_rsync_rc="$rsync_rc"
    append_status "FAIL" "reason=rsync_failed rc=${rsync_rc} cycle=${cycle_name} src=${cycle_dir} dest=${DEST}${cycle_name}/"
    continue
  fi

  "$RSYNC_BIN" -aO --no-links --exclude "$EXCLUDED_LATEST_PATTERN" --dry-run "$cycle_dir/" "${DEST}${cycle_name}/" >"$verify_stdout" 2>"$verify_stderr"
  verify_rc=$?
  if [[ "$verify_rc" -ne 0 || -s "$verify_stdout" || -s "$verify_stderr" ]]; then
    emit_rsync_output "$verify_stdout" "$verify_stderr"
    failure_count=$((failure_count + 1))
    if [[ "$verify_rc" -eq 0 ]]; then
      last_rsync_rc=4
    else
      last_rsync_rc="$verify_rc"
    fi
    append_status "FAIL" "reason=verify_failed rc=${verify_rc} cycle=${cycle_name} src=${cycle_dir} dest=${DEST}${cycle_name}/"
    continue
  fi

  verified_count=$((verified_count + 1))
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

append_status "OK" "result=MIRRORED cycles=${cycle_count} verified=${verified_count} skip_only=${skip_only_count} excluded_latest_symlinks=${latest_symlink_count} top_level_symlinks_ignored=${top_level_symlink_count} src=${SRC} dest=${DEST}"
printf "MIRRORED cycles=%s verified=%s excluded_latest_symlinks=%s top_level_symlinks_ignored=%s src=%s dest=%s\n" "$cycle_count" "$verified_count" "$latest_symlink_count" "$top_level_symlink_count" "$SRC" "$DEST"
exit 0
