# PLAN_G28_G31_CASHFLOW_CALENDAR_CAPITAL_CONTROL_PLANE

Owner: Adil  
Repo: ~/Docs/Autonomous_business  
Status: DRAFT → READY FOR IMPLEMENTATION  
Priority: 🔥 Highest (cash = oxygen)

## 0) The physics (why this exists)
A PO can be “correct” on inventory math and still bankrupt the business.

Reason: **Kaspi sales are not instant cash.**
Sales create **Receivables**, which later convert to **Cash** via payouts.
If we ignore payout lag, we overestimate cash and place POs that create a future cash crash.

So we build a cashflow calendar as a deterministic daily state ledger derived from events.

## 1) Target outcome
A daily cashflow calendar that:
1) Reconciles past: shows what really happened (cash, receivables, inventory at cost).
2) Forecasts future: projects cash valleys for 60–120 days.
3) Constrains PO decisions: blocks/warns when a PO would violate a cash floor.

This is not tax accounting. It’s a **decision safety system**.

## 2) Non‑negotiables (contracts)
- **Append-only events** are the single source of truth.
- The daily calendar is **derived**, never manually edited.
- Receivables are first‑class (no “sales = cash” shortcut).
- Inventory is tracked at **COST**, not retail value.
- Deterministic rebuild: same inputs → same daily ledger.
- Auditable: every derived row traces back to event sources + run_id.

## 3) Scope and phases
### G28 — Cashflow event spine + daily rollup (MVP)
Deliver:
- DB schema:
  - fact_cashflow_events (append-only)
  - fact_cashflow_daily (derived roll-forward)
- Script:
  - scripts/rebuild_cashflow_calendar.py
- Exports:
  - exports/cashflow_calendar.csv (daily table)
- Tests + invariants for roll-forward identities.

### G29 — Forecast engine (MVP projections)
Deliver:
- Base forecast 60–120 days:
  - sales forecast (run-rate or demand-model-backed)
  - payout lag model (parameterized)
  - expenses + commitments included
- Scenario bands:
  - conservative / base / aggressive

### G30 — PO preflight cash gate (capital safety)
Deliver:
- A validator that evaluates a plan’s PO payment schedule against projected cash.
- Warn/block if projected cash < cash_floor inside horizon.
- Must be runnable from CLI and integrated into run_end_of_day.

### G31 — Web UI (owner-grade)
Deliver:
- Minimal internal webapp (FastAPI + lightweight UI OR Streamlit first, product UI later)
- Must be fast, robust, and low-friction (calendar view + charts + what-if PO).

## 4) Data model

### 4.1 fact_cashflow_events (canonical event spine)
A single table for all “capital moving” events.

Columns (proposed):
- id (PK)
- event_date (DATE)
- event_ts (optional)
- event_type (ENUM string):
  - SALE_ACCRUED
  - PAYOUT_RECEIVED
  - REFUND
  - PO_PAYMENT
  - PO_RECEIPT (optional; inventory location change)
  - COGS_RECOGNIZED
  - EXPENSE
  - OWNER_INJECTION / OWNER_WITHDRAWAL
  - ADJUSTMENT
- account (ENUM string):
  - CASH
  - RECEIVABLES
  - INVENTORY_COST
  - REVENUE (optional helper)
  - COGS (optional helper)
  - EXPENSE (optional helper)
- amount_kzt (REAL, signed)
- store_code (nullable)
- sku_key (nullable)
- sku_id (nullable)
- ref_type (order_id / po_id / payout_id / expense_id)
- ref_id
- notes
- source (KASPI / BANK_IMPORT / MANUAL / SYSTEM)
- run_id (ties to pipeline run)
- event_hash (unique for idempotent imports)
- created_at

Rules:
- CASH increases are +, decreases are -.
- RECEIVABLES increases are + (sale accrued), decreases are - (payout, refund).
- INVENTORY_COST increases are + (PO payment / capitalized freight), decreases are - (COGS/writeoff).

### 4.2 fact_cashflow_daily (derived)
Columns:
- date
- cash_open, cash_close
- receivables_open, receivables_close
- inventory_cost_open, inventory_cost_close
- capital_close = cash_close + receivables_close + inventory_cost_close
- daily flows:
  - sales_accrued_kzt
  - payouts_received_kzt
  - refunds_kzt
  - po_payments_kzt
  - expenses_kzt
  - cogs_kzt
- computed:
  - profit_accrual_kzt = sales_accrued - cogs - expenses

Roll-forward identity (must hold daily):
cash_close = cash_open + cash_in - cash_out
(and same pattern for receivables and inventory_cost with their respective flows)

### 4.3 commitments (optional but recommended for forecast)
Table:
- fact_cashflow_commitments
  - commit_date
  - commit_type (PO_PLANNED_PAYMENT, RENT, PAYROLL, etc.)
  - amount_kzt
  - probability / scenario_tag
  - ref_id (po_id)
Used only for forecast & what-if.

## 5) Event sourcing: where events come from (MVP mapping)

### 5.1 Sales → SALE_ACCRUED (+RECEIVABLES)
Source options:
- Prefer: fact_sales (has economics: line_net_rev, cogs_line) if populated.
- Fallback: sales_fact_v2 (has net_rev) + cogs_unit from dim_sku.cogs_kzt.

Note:
- sales ingestion already writes net_rev into sales_fact_v2. We should reuse that to avoid re-parsing Excel. 

### 5.2 Payouts → PAYOUT_RECEIVED (+CASH, -RECEIVABLES)
MVP input:
- Manual CSV import (bank/Kaspi settlement export) into events table.

Later automation:
- Kaspi payout API integration or settlement file ingestion.

### 5.3 PO payments → PO_PAYMENT (-CASH, +INVENTORY_COST)
MVP input:
- Manual CSV import (date, amount, po_id, supplier).

Later automation:
- tie to PO status in fact_po_lines and payment terms table.

### 5.4 Expenses → EXPENSE (-CASH)
MVP input:
- Manual CSV import (rent, payroll, ads, logistics not capitalized).

### 5.5 COGS → COGS_RECOGNIZED (-INVENTORY_COST)
Derived daily from sales volume:
- cogs_kzt = units_sold * cogs_unit_kzt (from dim_sku.cogs_kzt or fact_sales)

## 6) Implementation details (how we build it safely)

### 6.1 Schema + migration
- Add schema changes to db/schema.sql
- Add migration script:
  - scripts/migrate_0xx_cashflow_calendar.py
- Migration must be idempotent and safe on existing db/app.db.

### 6.2 Deterministic rebuild script
Create:
- scripts/rebuild_cashflow_calendar.py

Features:
- Args: --start-date, --end-date, --db, --apply
- Default is DRY RUN:
  - prints counts per event_type, date range, totals
- Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply
- Writes:
  - recompute derived daily table by deleting and rebuilding for range
  - events are append-only except for derived/auto-generated event types:
    - For auto-generated events (SALE_ACCRUED, COGS_RECOGNIZED), write them into a separate table OR
      write them into fact_cashflow_events with source=SYSTEM and a deterministic event_hash and
      replace by (date,event_type,source) inside rebuild.

Strong recommendation:
- Keep manual events (payouts/expenses/po_payments) strictly append-only.
- Keep system-derived events rebuildable (replaceable) but only within SYSTEM scope.

### 6.3 Exports
Create:
- scripts/update_cashflow_dashboard.py
Outputs:
- exports/cashflow_calendar.csv
- exports/cashflow_dashboard.html

HTML requirements:
- Owner-grade UI: calendar table + charts:
  - cash
  - receivables
  - inventory_cost
  - total_capital
- Show min cash date/amount for forecast horizon.

### 6.4 Integrate into run_end_of_day
Add step after sales+ledger snapshot are updated:
- rebuild cashflow (past window + forecast forward)
- export CSV + HTML

### 6.5 Validators / invariants
Create:
- scripts/validate_cashflow_invariants.py
Checks:
- Roll-forward identities hold for every day.
- No negative “impossible” states unless explicitly allowed (configurable):
  - cash_close >= -tolerance (default tolerance 0)
- Receivables never go negative beyond tolerance.

Add as optional gate to EOD first, then promote to hard gate.

## 7) PO cash preflight gate (G30)
Goal: prevent “cash-to-zero” events.

Implement:
- scripts/preflight_po_cash_gate.py

Inputs:
- Proposed PO payments schedule:
  - from plan export totals (kzt) and assumed payment timing (config)
  - OR from manual commitments table
- cash_floor_kzt (config)
- horizon_days default:
  - max(lead_time_days + payout_lag_days + buffer_days)

Output:
- PASS/WARN/FAIL
- min_cash_amount, min_cash_date
- explanation of what drives the crash (expense, payout lag, PO payment)

Integrate:
- When exporting supplier PO:
  - if FAIL, block export unless ENABLE_PO_CASH_OVERRIDE=1

## 8) Acceptance criteria (definition of DONE)

### G28 DONE when:
- Running:
  - python3 scripts/update_cashflow_dashboard.py
Produces:
  - exports/cashflow_calendar.csv
  - exports/cashflow_dashboard.html
- Daily identities validated by:
  - python3 scripts/validate_cashflow_invariants.py
- Tests exist and pass:
  - pytest -q
- End-of-day can run with the new step.

### G29 DONE when:
- Forecast produces 60–120 days with at least 3 scenarios.
- Outputs show min cash date/amount.

### G30 DONE when:
- A PO plan can be blocked for violating cash_floor.
- Override mechanism exists and is logged.

### G31 DONE when:
- Web UI is usable daily without Excel.
- What-if PO is fast (<2s) and reliable.

## 9) Evidence + governance
Every milestone requires:
- DB backup path (before any writes)
- commands run
- exports paths
- oracle pack containing:
  - new scripts
  - schema diffs
  - sample outputs (csv/html)

Keep commits atomic (schema, scripts, UI, gates in separate commits).
# SUPERSEDED (Truth Contract 2026-01-26)
This plan assumes receivables + payout lag. Current truth contract uses **D1 cash-in at DELIVERED** (no receivables model).  
Use for historical context only. See: `docs/CASHFLOW_TRUTH_CONTRACT_2026-01-26.md`.

