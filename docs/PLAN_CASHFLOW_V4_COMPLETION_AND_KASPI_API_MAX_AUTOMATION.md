# PLAN — Cashflow V4 Completion + Kaspi API Max Automation (Full Scope)
**Date:** 2026-01-27  
**Owner:** Autonomous agent  
**Status:** Ready for execution after `/docs/PLAN_CASHFLOW_V4_COMPLETION_AND_KASPI_API_MAX_AUTOMATION.md` is finalized  
**Prime directive:** Protect capital; only declare success after all gates pass.

## 0) References (must-read)
- `/docs/194118_TASK-000_cashflow_truth_full_scope.md` (truth contract + phased acceptance gates)
- `/docs/KASPI_API_WORKFLOW_UPDATE_2026-01-26.md` (already added order fields + migration)
- `/docs/KASPI_API_INTEGRATION_GAP_PLAN.md` (line-item + dim cache plan)
- `/docs/KASPI_API_INTEGRATION.md` (API constraints + conventions)
- `/docs/KASPI_ORDER_CASHFLOW_TRACKING.md` (orders → cashflow mapping rules)

---

## 1) Non-negotiable execution rule (TEST-FIRST)
For every phase below:

1) **Write or update tests first** (unit/integration)  
2) Implement code + migrations  
3) Run **ALL phase gates** (below)  
4) Only then proceed to the next phase  
5) If any gate fails → fix immediately (no “we’ll patch later”)

### Global gates (run every phase)
- `pytest -q`
- `scripts/lint_docs.sh`
- `scripts/check_no_db_tracked.sh`

### Cashflow gates (when cashflow touched)
- `python3 scripts/validate_cashflow_invariants.py`
- `python3 scripts/validate_inventory_cost_drift.py`
- `ENABLE_CASHFLOW_WRITE=1 python3 scripts/run_end_of_day.py --verbose`

### Kaspi sync gates (when sync touched)
- `pytest -q tests/test_kaspi_api_client.py`
- `pytest -q tests/test_order_sync.py`

---

## 2) North Star (best-case “decision grade”)
A single, conservative Treasury + Capital system that:

- Anchors to statement truth: end-of-day MT940 closing balances are the official cashflow “start here”
- Maintains an append-only, event-sourced ledger for:
  - cash movements (per account + currency)
  - inventory-at-cost movements (on-hand + inbound + on-delivery)
  - commitments (PO schedule + OPEX schedule + taxes/other)
- Produces:
  - daily cashflow calendar
  - strict PO preflight gate that blocks any PO that breaches:
    - cash floor (X months of OPEX + absolute min cash)
    - near-term commitments
    - worst-case return exposure
- Runs with minimal manual work:
  - Daily: Kaspi API sync (rolling 14-day), cashflow rebuild, preflight, dashboard exports
  - Periodic: MT940 ingestion as reconciliation backbone + manual snapshot only when needed
- Cashflow engine reads DB only (deterministic); API sync writes DB.

---

## 3) Phase plan (fastest safe path)

### Phase A — Stabilize “truth contract” + determinism (close remaining V4 items)
**Goal:** daily rebuild is deterministic, idempotent, and produces decision-grade post-anchor days.

Deliverables:
- Trust banner logic: STATEMENT_ACTUAL vs MANUAL vs ORDER_MODELLED vs FORECAST_MODEL
- Drift report respects 14-day API window (no fake drift)

Acceptance gates:
- run_end_of_day passes twice in a row on same DB (no double counting)
- drift report labels insufficient coverage when expected is structurally impossible
- invariants + inventory drift validations pass

Tests required:
- `test_drift_report_respects_api_window()`
- `test_cashflow_rebuild_idempotent()`

---

### Phase B — Commitments engine (OPEX + PO schedule) feeds preflight
**Goal:** preflight uses real commitments and a configurable cash floor.

Deliverables:
- `fact_commitments` (or equivalent) is the single source for:
  - OPEX schedule (from OPEX protocol)
  - PO payment schedule (base + landed)
  - conservative vs base scenario dates
- Cash floor config:
  - `cash_floor_months_base`
  - `cash_floor_months_conservative`
  - `cash_floor_absolute_min_kzt` (e.g., 500_000)

Acceptance gates:
- Preflight fails if conservative cash dips below (months×OPEX + abs min)
- Commitments table shows “next payments” clearly (OPEX + PO)
- No magic numbers in preflight logic

Tests required:
- `test_preflight_floor_is_configurable()`
- `test_commitments_roll_forward_dates()`

---

### Phase C — Inventory-at-cost ledger (E1 + F3) with 3 inventory subaccounts
**Goal:** inventory becomes a balance-sheet engine, not fragile snapshots.

Deliverables:
- Inventory accounts:
  - `INVENTORY_ON_HAND_COST`
  - `INVENTORY_INBOUND_COST`
  - `INVENTORY_ON_DELIVERY_COST`
- Post-anchor movements:
  - PO payment => cash ↓, inbound inventory ↑ (F3)
  - Landed payment => inventory cost ↑ when paid/known (F3)
  - Arrival => inbound → on-hand (no cash)
  - Shipped => on-hand → on-delivery
  - Delivered => on-delivery → COGS (cash-in handled by orders)
  - Return => reverse cash-in; reverse COGS → on-hand; delivery fee stays expense

Acceptance gates:
- Inventory accounts never negative
- Sum inventory reconciles to snapshot within tolerance on statement-backed days

Tests required:
- `test_inventory_accounts_never_negative()`
- `test_inbound_to_onhand_transfer_no_cash_effect()`

---

### Phase D — Transfer ledger integration (Kaspi → Gold → Universal → Binance → Supplier)
**Goal:** eliminate manual cash drift by translating transfer ledger entries into cashflow events.

Deliverables:
- translator: `transfer_ledger_entries -> fact_cashflow_events`
- internal transfers become “reclass” events (no net cash change across global cash)
- Binance conversions + supplier payments become cash-out + inventory inbound increase (linked to PO IDs)

Acceptance gates:
- Idempotent imports (safe re-run)
- No double counting between MT940 statements and transfer ledger
- Every supplier payment can be traced to a PO ID (audit)

Tests required:
- `test_transfer_import_idempotent()`
- `test_no_double_count_statement_vs_transfer_ledger()`

---

### Phase E — Kaspi API enrichment (line-item truth) behind a feature flag (default OFF)
**Goal:** add line-item and product metadata without destabilizing base sync.

Deliverables:
- New read-only client endpoints:
  - Q7/Q8/Q9/Q11
- DB tables:
  - `fact_order_entries_kaspi`
  - `dim_masterproduct`, `dim_merchantproduct`, `dim_point_of_service`
- Optional enrichment stage:
  - flag `ENABLE_KASPI_ENRICH_ENTRIES=0/1` (default 0)
  - only enrich new/changed orders (or last N days)
  - fail-open (log warning, continue)
  - rate-limited + cached

Acceptance gates:
- Core sync unaffected when enrichment fails
- Multi-line orders no longer misrepresented as qty=1 at order-level
- Cache hit-rate improves over time; no API call explosion

Tests required:
- `test_enrichment_flag_defaults_off()`
- `test_enrichment_fail_open_does_not_break_sync()`
- `test_multiline_order_entries_sum_matches_order_total()`

---

### Phase F — Generate Fact_Sales (V16) from API order entries (remove Excel dependency)
**Goal:** produce decision-grade sales table at correct grain: OrderID × SKU × Store.

Deliverables:
- deterministic builder producing Fact_Sales V16 from:
  - order entry quantity + price
  - merchantProduct mapping for SKU_key
  - delivery fee logic (matrix vs API cross-check)
- mismatch report (unmapped SKUs, missing master data)

Acceptance gates:
- Fact_Sales schema matches V16
- reconciles to known totals (by store/day) within tolerance

Tests required:
- `test_fact_sales_schema_v16()`
- `test_fact_sales_reconciles_to_orders()`  

---

### Phase G — 10% safety margin upgrades (optional)
Not required for 80–90% completion:
- SLA analytics: planned vs actual transmission/delivery dates
- return risk profiling: `returnedToWarehouse`, `express`, etc.
- Goods API automation (price/stock/product upload) ONLY behind explicit enable flag (higher operational risk)

---

## 4) Daily pipeline order (must remain stable)
1) `sync_kaspi_orders` (rolling 14 days) — BLOCK EOD if mandatory stores stale
2) build/refresh cashflow events (DB -> events)
3) `run_end_of_day` (writes daily ledger + trust labels)
4) `preflight_po` (strict gate)
5) export dashboards (html/csv)

---

## 5) Definition of Done (system-level)
- Daily run can be executed unattended
- Any PO cannot be approved if it violates conservative floor + commitments
- Cashflow calendar is decision-grade from last statement day forward
- Multi-line order correctness is fixed (entries table)
- All tests + gates pass and are runnable in CI-like fashion

