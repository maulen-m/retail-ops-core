# Plan: Dim SKU Weight Recovery and Drift Guard (2026-02-09)

## Goal
Restore `dim_sku.weight_kg` from `Dim sku light v5.xlsx`, stop future contamination from duplicate helper rows, and ensure PO dashboard + COGS + cashflow all use one consistent weight truth.

## Scope
- In scope:
  - Canonical parser for `DIM_SKU_light_v5`.
  - Explicit write-gated weight sync into `dim_sku`.
  - Guard rails to prevent inbound PO sync from silently rewriting SKU weights.
  - Strict validator for dim-sku vs workbook weight alignment.
  - Rebuild dependent outputs (PO dashboard, cashflow dashboard, business insides).
- Out of scope:
  - Broad base-cost restatement (cost fields stay reference-only by default).
  - Unrelated unstaged repo changes.

## Root Cause (Validated)
- `scripts/sync_po_parts_from_inbound_calendar.py` reads `DIM_SKU_light_v5` and keeps the last duplicate row per `SKU_key`.
- Workbook contains helper micro rows (for example `CNY=0.19`, `Wt=0.07`) after canonical rows (`CNY=47`, `Wt=0.95`).
- Last-row-wins behavior overwrote `dim_sku.weight_kg` for many active SKUs, shrinking delivery COGS and distorting PO/cashflow economics.

## Execution Phases

### Phase 0: Governance + Safety
1. Update `.claude` memory docs (task claim, progress target, decision log, session evidence).
2. Create DB backup before code edits.

### Phase 1: Tests First (Fail First)
1. Add parser tests:
   - `tests/test_dim_sku_light_parser.py`
2. Add sync tests:
   - `tests/test_sync_dim_sku_from_dim_sku_light.py`
3. Add inbound parser guard test:
   - `tests/test_sync_po_parts_parser_guard.py`
4. Add alignment validator tests:
   - `tests/test_validate_dim_sku_light_alignment.py`
5. Extend business-insides strictness coverage for landed COGS output transparency.
6. Capture fail-first evidence in `.claude/SESSION_LOG.md`.

### Phase 2: Implementation
1. Add canonical parser module:
   - `core/excel/dim_sku_light_parser.py`
2. Add explicit restore script:
   - `scripts/sync_dim_sku_from_dim_sku_light.py`
   - dry-run default, apply requires `ENABLE_DIM_SKU_SYNC_WRITE=1` + `--apply`
   - default updates `weight_kg` only
3. Harden:
   - `scripts/sync_po_parts_from_inbound_calendar.py`
   - prevent implicit dim-sku weight overwrite by default
4. Add strict validator:
   - `scripts/validate_dim_sku_light_alignment.py`
5. Wire validator into strict chain:
   - `scripts/validate_params.py`

### Phase 3: Restore + Recompute
1. Dry-run sync from:
   - `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inventory/Dim sku light v5.xlsx`
2. Apply sync with env-gate + flag.
3. Regenerate:
   - PO dashboard data
   - cashflow dashboard
   - business-insides snapshot

### Phase 4: Verification
1. Targeted tests pass.
2. Validators pass:
   - `validate_dim_sku_light_alignment.py`
   - `validate_cogs_integrity.py`
   - `validate_params.py --strict`
3. Full gate chain pass.

### Phase 5: Docs + Prevention
1. Add runbook:
   - `docs/inventory/DIM_SKU_LIGHT_WEIGHT_SYNC_SINGLE_TRUTH_2026-02-09.md`
2. Update architecture/contracts:
   - `docs/ARCHITECTURE.md`
   - `docs/validation/DASHBOARD_CONTRACT.md`
   - `docs/db_data_ingetrity_fix_plan.md`
3. Prevention controls:
   - Duplicate-row quality filtering
   - explicit sync-only write path for weights
   - strict alignment gate in validation chain
   - source fingerprint and anomaly alerts in sync output

## Verification Commands
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q \
  tests/test_dim_sku_light_parser.py \
  tests/test_sync_dim_sku_from_dim_sku_light.py \
  tests/test_sync_po_parts_parser_guard.py \
  tests/test_validate_dim_sku_light_alignment.py \
  tests/test_business_insides_cogs_strictness.py

python3 scripts/sync_dim_sku_from_dim_sku_light.py \
  --xlsx "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inventory/Dim sku light v5.xlsx"

ENABLE_DIM_SKU_SYNC_WRITE=1 python3 scripts/sync_dim_sku_from_dim_sku_light.py \
  --xlsx "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inventory/Dim sku light v5.xlsx" \
  --apply

python3 scripts/validate_dim_sku_light_alignment.py \
  --xlsx "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inventory/Dim sku light v5.xlsx"

python3 scripts/validate_cogs_integrity.py
python3 scripts/validate_params.py --strict
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
python3 scripts/run_contract_suite.py --fixture small
python3 scripts/validate_po_dashboard_invariants.py
python3 scripts/validate_single_truth_alignment.py
python3 scripts/validate_cashflow_invariants.py
python3 scripts/validate_inventory_cost_drift.py
scripts/lint_docs.sh
scripts/check_no_db_tracked.sh
```

## Rollback
1. Code rollback:
   - `git revert <newest> ... <oldest>`
2. DB rollback:
   - restore backup created in Phase 0 to `db/app.db`
3. Re-run minimum gates:
   - `python3 scripts/validate_params.py --strict`
   - `python3 scripts/validate_cogs_integrity.py`

