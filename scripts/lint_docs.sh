#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

if ! command -v rg >/dev/null 2>&1; then
  echo "ERROR: ripgrep (rg) is required for docs lint." >&2
  exit 1
fi

DOCS_GLOBS=(--glob 'docs/**' --glob '!docs/archive/**' --glob '!docs/**/archive/**')
GREEN_PATH_PLAN_NUMERIC_ALLOWLIST=(--glob '!docs/plan/green_path_2026-06/**')

PATTERNS=(
  'VAT\s*3%'
  'VAT\s*0\.03'
  'VAT_rate\s*=\s*0\.03'
  'Master_Inventory_Rules_v5\.3'
  'Master_Inventory_Rules_v6'
  '\bWildberries\b'
  '\bWB\s+export\b'
  '\bWB\b'
  'Autonomous_business 2'
)

LEGACY_NUMERIC_PATTERNS=(
  '\b856\b'
  '\b1259\b'
  '0\s*/\s*856\s*/\s*1259'
)

fail=0
for pat in "${PATTERNS[@]}"; do
  if rg -n "${DOCS_GLOBS[@]}" -e "$pat" docs; then
    echo "ERROR: docs lint found banned pattern: $pat" >&2
    fail=1
  fi
done

for pat in "${LEGACY_NUMERIC_PATTERNS[@]}"; do
  if rg -n "${DOCS_GLOBS[@]}" "${GREEN_PATH_PLAN_NUMERIC_ALLOWLIST[@]}" -e "$pat" docs; then
    echo "ERROR: docs lint found banned pattern: $pat" >&2
    fail=1
  fi
done

ACTIVE_AUTHORITY_DOCS=(
  docs/inventory/Sales_Data_Model_V16.md
  docs/inventory/Automation_Handoff_V16.md
  docs/inventory/Excel_UI_Contract_for_CRM_V1.md
  docs/inventory/Workflow_SOP_V2.md
  docs/validation/SALES_ECONOMICS_TRUTH_CONTRACT.md
)

STALE_ACTIVE_AUTHORITY_PATTERNS=(
  'update v8 first'
  'See v8'
  'v8/V16'
  'Kaspi, v8'
  'Sales_Data_Model_V15'
)

for pat in "${STALE_ACTIVE_AUTHORITY_PATTERNS[@]}"; do
  if rg -n -i -e "$pat" "${ACTIVE_AUTHORITY_DOCS[@]}"; then
    echo "ERROR: docs lint found stale active authority pointer: $pat" >&2
    fail=1
  fi
done

# Ban machine-local absolute paths in active operator-facing docs.
# Exception: config/anchors/README.md may define operator-specific examples.
ACTIVE_PATH_DOCS=(
  docs/00_START_HERE.md
  docs/DAILY_SOP.md
  docs/ARCHITECTURE.md
)
if rg -n -e '~/' "${ACTIVE_PATH_DOCS[@]}"; then
  echo "ERROR: docs lint found user-specific absolute path (~/) in active docs; use config/anchors/README.md for path authority" >&2
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  echo "Docs lint failed. Remove legacy references in non-archive docs." >&2
  exit 1
fi

echo "Docs lint OK."
