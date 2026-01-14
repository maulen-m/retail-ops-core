#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "CI gates starting: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

status=0

run_gate() {
  local label="$1"
  shift
  echo ""
  echo "==> ${label}"
  if "$@"; then
    echo "PASS: ${label}"
  else
    echo "FAIL: ${label}"
    status=1
  fi
}

if [[ -f "db/app.db" ]]; then
  run_gate "validate_params" python3 scripts/validate_params.py --strict
else
  echo "SKIP: validate_params (db/app.db missing)"
fi

if [[ -f "db/app.db" ]]; then
  workbook_path="${TRUTH_WORKBOOK_PATH:-${TRUTH_WORKBOOK:-excel/Inventory_Core_V18.1_V2.xlsx}}"
  if [[ -f "${workbook_path}" ]]; then
    run_gate "run_end_of_day" python3 scripts/run_end_of_day.py --verbose --skip-sync --skip-workbook-sync --dry-run
  else
    echo "SKIP: run_end_of_day (workbook not found at ${workbook_path})"
  fi
else
  echo "SKIP: run_end_of_day (db/app.db missing)"
fi

run_gate "pytest" pytest -q
run_gate "dashboard_invariants" python3 scripts/validate_po_dashboard_invariants.py
run_gate "lint_docs" scripts/lint_docs.sh
run_gate "check_no_db_tracked" scripts/check_no_db_tracked.sh

exit "${status}"
