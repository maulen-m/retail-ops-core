# PLAN_SINGLE_TRUTH_HARDENING_V1

## Scope
- Repo: `~/Docs/wt_single_truth_stabilization_v1` only.
- Goal: harden single-truth daily operations and prevent silent data drift.
- Non-goal: ads attribution implementation in this pass (explicitly deferred).

## Truth Ladder
- Inventory/cost formulas: `docs/inventory/Master_Inventory_Rules_v8.md`
- Cashflow contract: `docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
- Data model: `docs/inventory/Sales_Data_Model_V16.md`

## Hard Constraints
- Tests first with fail-first evidence before code changes in each phase.
- No write-side without env gate + `--apply`.
- Surgical edits only; do not stage unrelated changes.
- Outputs in `exports/`; never track DB files.

## Phase 0 — Safety Baseline
### Actions
1. Keep execution in stabilization worktree only.
2. Record DB backup path before any apply actions.
3. Lock this plan document as execution contract.

### Done Definition
- Plan file committed and referenced in session evidence.

## Phase 1 — Workbook Anchor Automation
### Goal
- Make workbook-anchored strict validation the canonical daily operator path.

### Implementation
1. Add `scripts/run_strict_daily_preflight.py`:
   - Requires workbook path via `--workbook` or `AB_CRM_WORKBOOK_PATH`.
   - Fails closed when workbook is missing.
   - Executes `python3 scripts/validate_params.py --strict`.
   - Prints one-line PASS/FAIL summary for scheduler use.
   - Optional `--emit-lineage` to generate read-only lineage artifact.
2. Update `docs/DAILY_SOP.md` with one canonical command.

### Tests (fail-first then green)
- `tests/test_run_strict_daily_preflight.py`
  - fails closed when workbook path not set
  - propagates strict gate status
  - emits lineage artifact when requested

## Phase 2 — Recurring On-Delivery Residual Dry-Run
### Goal
- Daily dry-run report for residual `INVENTORY_ON_DELIVERY_COST` gaps, with optional alert.

### Implementation
1. Add `scripts/check_on_delivery_residuals.py`:
   - Read-only by default.
   - Uses settlement gap finder.
   - Writes `exports/on_delivery_residuals/on_delivery_residuals_<asof>.md`.
   - Exit code non-zero if residuals exist.
   - Optional `--send-alert` best-effort Telegram alert.
2. Keep write reconciliation in existing `scripts/reconcile_on_delivery_settlement.py` with existing gates.

### Tests (fail-first then green)
- `tests/test_check_on_delivery_residuals.py`
  - writes report
  - non-zero on residuals
  - zero exit on clean set

## Phase 3 — Hard Weight Write Guard
### Goal
- Block `dim_sku.weight_kg` updates outside canonical sync path.

### Implementation
1. Add migration `scripts/migrate_025_dim_sku_weight_guard.py`:
   - Create guard table `dim_sku_weight_write_guard`.
   - Create trigger blocking `UPDATE OF weight_kg` unless guarded token is active and fresh.
   - Dry-run default, apply requires `ENABLE_SCHEMA_WRITE=1` + `--apply`.
2. Update `scripts/sync_dim_sku_from_dim_sku_light.py`:
   - Enable guard token only within its apply transaction.
   - Disable token on completion/failure.
3. Keep `scripts/sync_po_parts_from_inbound_calendar.py` non-overwriting by default.

### Tests (fail-first then green)
- `tests/test_dim_sku_weight_write_guard.py`
  - update weight without guard fails
  - canonical sync with guard succeeds
  - non-weight updates remain allowed

## Phase 4 — Lineage Artifact per Run
### Goal
- Emit deterministic read-only lineage report for trust/audit per run.

### Implementation
1. Add `scripts/generate_lineage_report.py`:
   - DB path + schema version
   - workbook path + SHA256 (if provided)
   - published sales truth counts/date range
   - cashflow events counts/date range
   - strict gate exit status from caller
2. Integrate via `run_strict_daily_preflight.py --emit-lineage`.

### Tests (fail-first then green)
- `tests/test_generate_lineage_report.py`
  - deterministic output with fixed timestamp
  - handles missing workbook gracefully

## Verification Gates (final)
1. `python3 scripts/validate_params.py --strict`
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q`
3. `python3 scripts/run_contract_suite.py --fixture small`
4. `python3 scripts/validate_single_truth_system.py`
5. `scripts/lint_docs.sh`
6. `scripts/check_no_db_tracked.sh`

## Commit Plan
1. `docs: add single-truth hardening v1 execution plan`
2. `tests: add fail-first coverage for hardening v1 phases`
3. `ops: add strict daily preflight wrapper + sop wiring`
4. `cashflow: add on-delivery residual dry-run report tool`
5. `schema: add dim_sku weight write-guard migration + canonical sync token`
6. `ops: add lineage report artifact and preflight integration`

## Rollback
1. Code:
   - `git revert <newest_commit> ... <oldest_commit>`
2. DB (if any apply was executed):
   - restore pre-apply backup recorded in session log
3. Re-validate:
   - `python3 scripts/validate_params.py --strict`
   - `python3 scripts/check_no_db_tracked.sh`
