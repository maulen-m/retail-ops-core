#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" scripts/validate_daily_shipping_runtime.py --json

test_files=()
while IFS= read -r test_file; do
  test_files+=("$test_file")
done < <(
  find tests -maxdepth 1 -type f \( \
    -name 'test_google_ops_board*.py' -o \
    -name 'test_*waybill*.py' -o \
    -name 'test_send_waybills_telegram.py' -o \
    -name 'test_waybill_telegram_control_bot.py' -o \
    -name 'test_ship_orders_api.py' -o \
    -name 'test_delivery*.py' -o \
    -name 'test_kaspi_import_scheduler_contract.py' -o \
    -name 'test_run_kaspi_import_scheduler.py' -o \
    -name 'test_kaspi_api_call_ledger.py' -o \
    -name 'test_kaspi_shipped*.py' -o \
    -name 'test_kaspi_daily_ops_workflow_contract_doc.py' -o \
    -name 'test_manage_business_automation.py' -o \
    -name 'test_daily_shipping_runtime_contract.py' -o \
    -name 'test_compact_runtime_backups.py' -o \
    -name 'test_manage_daily_shipping_recovery.py' -o \
    -name 'test_run_m5_daily_shipping_shadow.py' -o \
    -name 'test_rotate_daily_shipping_credential.py' -o \
    -name 'test_verify_daily_shipping_closeout.py' -o \
    -name 'test_monitor_daily_shipping_health.py' -o \
    -name 'test_rotate_daily_shipping_logs.py' -o \
    -name 'test_archive_cold_evidence.py' -o \
    -name 'test_download_kaspi_archive_webui.py' \
  \) | sort
)

if [[ "${#test_files[@]}" -eq 0 ]]; then
  echo "ERROR: no daily shipping tests discovered" >&2
  exit 2
fi

"$PYTHON_BIN" -m pytest -q "${test_files[@]}"
scripts/lint_docs.sh
scripts/check_no_db_tracked.sh
