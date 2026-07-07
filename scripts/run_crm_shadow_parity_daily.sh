#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="~/Docs/Autonomous_business"
cd "$REPO_ROOT"

export TZ="Asia/Almaty"

PYTHON="$REPO_ROOT/.venv/bin/python"
DB_PATH="db/app.db"
CRM_FILE="excel_ui/SALES_KSP_CRM_V3.xlsx"
LEDGER="exports/decommission/crm_excel_shadow/WINDOW_LEDGER.csv"

RUN_DATE="$(/bin/date +%F)"
FROM_DATE="$(/bin/date -v-7d +%F)"
TO_DATE="$(/bin/date +%F)"
RUN_ID="daily_$(/bin/date +%Y%m%d_%H%M%S)"
RUN_DIR="exports/decommission/crm_excel_shadow/${RUN_DATE}/${RUN_ID}"

append_ledger_line() {
  local run_date="$1"
  local verdict="$2"
  local matched="$3"
  local classified="$4"
  local unexplained="$5"

  mkdir -p "$(dirname "$LEDGER")"
  if [[ ! -f "$LEDGER" ]]; then
    printf 'date,verdict,matched,classified,unexplained\n' > "$LEDGER"
  fi
  printf '%s,%s,%s,%s,%s\n' "$run_date" "$verdict" "$matched" "$classified" "$unexplained" >> "$LEDGER"
}

check_excel_workbook_open() {
  /usr/bin/osascript - "$REPO_ROOT/$CRM_FILE" "$(basename "$CRM_FILE")" <<'APPLESCRIPT'
on run argv
  set targetPath to item 1 of argv
  set targetName to item 2 of argv

  tell application "System Events"
    if not (exists process "Microsoft Excel") then return "CLOSED"
  end tell

  tell application "Microsoft Excel"
    repeat with wb in workbooks
      set wbName to ""
      try
        set wbName to name of wb as text
      end try

      if wbName is targetName then
        try
          set wbFullName to full name of wb as text
          try
            set wbPosix to POSIX path of (wbFullName as alias)
            if wbPosix is targetPath then return "OPEN"
          on error
            return "OPEN"
          end try
        on error
          return "OPEN"
        end try
      end if
    end repeat
  end tell

  return "CLOSED"
end run
APPLESCRIPT
}

if ! EXCEL_STATE="$(check_excel_workbook_open 2>&1)"; then
  echo "ERROR: Excel workbook-open check failed: ${EXCEL_STATE}" >&2
  exit 2
fi

if [[ "$EXCEL_STATE" == "OPEN" ]]; then
  append_ledger_line "$RUN_DATE" "SKIPPED_WORKBOOK_OPEN" "0" "0" "0"
  echo "SKIPPED: workbook is open in Excel: $CRM_FILE"
  exit 0
fi

if [[ "$EXCEL_STATE" != "CLOSED" ]]; then
  echo "ERROR: unexpected Excel workbook-open check result: ${EXCEL_STATE}" >&2
  exit 2
fi

mkdir -p "$RUN_DIR"

"$PYTHON" scripts/feed_fact_orders_kaspi_to_sales_fact_v2.py \
  --db "$DB_PATH" \
  --from-date "$FROM_DATE" \
  --to-date "$TO_DATE" \
  --shadow-out "$RUN_DIR/direct_feeder_shadow_rows.csv"

set +e
"$PYTHON" scripts/validate_direct_sales_fact_parity.py \
  --db "$DB_PATH" \
  --crm-file "$CRM_FILE" \
  --direct-shadow "$RUN_DIR/direct_feeder_shadow_rows.csv" \
  --from-date "$FROM_DATE" \
  --to-date "$TO_DATE" \
  --out-dir "$RUN_DIR"
VALIDATOR_STATUS=$?
set -e

if [[ ! -f "$RUN_DIR/summary.json" ]]; then
  echo "ERROR: validator did not produce $RUN_DIR/summary.json" >&2
  exit "$VALIDATOR_STATUS"
fi

LEDGER_LINE="$("$PYTHON" - "$RUN_DATE" "$RUN_DIR/summary.json" <<'PY'
import csv
import json
import sys

run_date, summary_path = sys.argv[1], sys.argv[2]
with open(summary_path, encoding="utf-8") as handle:
    summary = json.load(handle)

classified = int(summary.get("classified_diffs") or 0) + int(summary.get("date_basis_classified") or 0)
unexplained = int(summary.get("unexplained_mismatches", summary.get("true_mismatches", 0)) or 0)
row = [
    run_date,
    summary.get("verdict", "UNKNOWN"),
    int(summary.get("matched") or 0),
    classified,
    unexplained,
]
csv.writer(sys.stdout, lineterminator="\n").writerow(row)
PY
)"

mkdir -p "$(dirname "$LEDGER")"
if [[ ! -f "$LEDGER" ]]; then
  printf 'date,verdict,matched,classified,unexplained\n' > "$LEDGER"
fi
printf '%s\n' "$LEDGER_LINE" >> "$LEDGER"

echo "VERDICT: $(printf '%s' "$LEDGER_LINE" | cut -d, -f2) ($LEDGER_LINE)"
echo "RUN_DIR: $RUN_DIR"

exit "$VALIDATOR_STATUS"
