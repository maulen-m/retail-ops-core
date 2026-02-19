#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

if ! command -v rg >/dev/null 2>&1; then
  echo "ERROR: ripgrep (rg) is required for docs lint." >&2
  exit 1
fi

DOCS_GLOBS=(--glob 'docs/**' --glob '!docs/archive/**' --glob '!docs/**/archive/**')

PATTERNS=(
  'VAT\s*3%'
  'VAT\s*0\.03'
  'VAT_rate\s*=\s*0\.03'
  '\b856\b'
  '\b1259\b'
  '0\s*/\s*856\s*/\s*1259'
  'Master_Inventory_Rules_v5\.3'
  'Master_Inventory_Rules_v6'
  '\bWildberries\b'
  '\bWB\s+export\b'
  '\bWB\b'
  'Autonomous_business 2'
)

fail=0
for pat in "${PATTERNS[@]}"; do
  if rg -n "${DOCS_GLOBS[@]}" -e "$pat" docs; then
    echo "ERROR: docs lint found banned pattern: $pat" >&2
    fail=1
  fi
done

if [[ "$fail" -ne 0 ]]; then
  echo "Docs lint failed. Remove legacy references in non-archive docs." >&2
  exit 1
fi

echo "Docs lint OK."
