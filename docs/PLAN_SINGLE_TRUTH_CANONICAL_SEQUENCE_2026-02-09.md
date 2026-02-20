# Single-Truth Canonical Sequence (2026-02-09)

## Objective
- Fix chronology corruption first, then enforce one canonical sales-truth interface, then add ads sidecar attribution.
- Keep PO schedule invariants untouched unless a failing invariant proves a required change.
- Tests-first on every phase with fail-first evidence recorded before implementation.

## Locked Corrections
1. Do not introduce another parallel daily-sales truth table.
2. Use canonical interfaces for all consumers:
   - `view_sales_line_truth`
   - `view_sales_daily_truth`
3. Treat `sales_fact_v2` and `fact_sales` as staging sources until parity is proven by validator evidence.
4. Fix `status_updated_at` restamping first in isolation:
   - status timestamp changes only on material status change
   - `synced_at` is updated on every sync.

## Phase 1 (Highest ROI): Chronology Stop-The-Bleeding

### Scope
- Patch `~/Docs/Autonomous_business/core/sync/order_sync_engine.py` so updates no longer restamp status-change time when status is unchanged.
- Persist `synced_at` independently from lifecycle status timestamp.

### Tests First (must fail before code edits)
- Add/extend tests to prove:
  - no restamp on same-status refresh
  - status timestamp changes only when status transitions
  - `synced_at` always moves forward on sync.

### Acceptance
- Targeted tests pass.
- No downstream daily event spikes caused by mass restamping.

## Phase 2: Canonical Sales-Truth Interface + Reconciliation

### Scope
- Add canonical views:
  - `~/Docs/Autonomous_business/db/views/view_sales_line_truth.sql`
  - `~/Docs/Autonomous_business/db/views/view_sales_daily_truth.sql`
- Update consumers to read these views only (business-insides, cashflow read paths, validators).
- Add reconciliation validator comparing staging sources over last `N` days:
  - orders
  - units
  - net revenue
  - COGS coverage.

### Tests First
- View contract tests (columns/types and deterministic aggregation).
- Reconciliation tests with fixtures that detect mismatches and coverage gaps.

### Acceptance
- All consumer entry points use canonical views.
- Reconciliation report identifies chosen staging primary source with evidence.

## Phase 3: Ads Spend Sidecar

### Scope
- Sync external ads DB into app DB as mapped and unmapped spend buckets.
- Compute and report `profit_after_ads` and ads mapping coverage.
- Keep cash-close statement-driven (ads must not overwrite bank-cash truth).

### Tests First
- Mapping coverage tests.
- Profit-after-ads computation tests.
- Guard test proving cash-close is unaffected by ads sidecar calculations.

### Acceptance
- Ads cost is visible and traceable per day/SKU where mapping exists.
- Unmapped ads spend is explicitly reported.

## Execution Order and Commits
1. Chronology fix commit.
2. Canonical views + reconciliation commit.
3. Ads sidecar commit.

Each commit requires:
- fail-first test evidence
- green targeted tests for the phase
- `.claude` memory updates.

## Required Gates (after all 3 phases)
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_po_dashboard_invariants.py`
- `python3 scripts/validate_single_truth_alignment.py`
- `python3 scripts/validate_single_truth_system.py`
- `python3 scripts/validate_on_delivery_freeze.py`
- `python3 scripts/validate_cashflow_invariants.py`
- `python3 scripts/validate_inventory_cost_drift.py`
- `scripts/lint_docs.sh`
- `scripts/check_no_db_tracked.sh`

## Out of Scope
- Rewriting PO schedule logic.
- Additional cashflow translator changes unless a failing invariant forces it.

## Rollback
1. `git revert <newest_commit> ... <oldest_commit>`
2. Restore DB backup created before apply steps.
