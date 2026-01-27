# PLAN_G32_G35_CASHFLOW_DECISION_GRADE_RECONCILIATION_AND_PO_PAYMENT_PLANNING.md

Phase: G32–G35 (Cashflow becomes decision-grade)
Focus: Convert cashflow calendar from accrual-only to cash-real + reconciled + usable for PO payment decisions

Repo: ~/Docs/Autonomous_business
Today date (truth): 2026-01-22
Known cash on hand: 5,000,000 KZT
Monthly OPEX: 2,300,000 KZT
Unpaid: PO-4.1, PO-4.2, PO-5 (payments will be gradual)

## Why this matters (physics)
- Cash is oxygen. Accrual profit does not prevent cash death.
- Kaspi sales create receivables; cash arrives later via payouts.
- A cashflow calendar must be derived from an append-only event spine + commitments, reconciled to real balances.

## Current state (observed)
- Dashboard shows cash_open/cash_close = 0 and payouts/expenses/po_payments = 0.
- This indicates accrual-only events exist, but cash events/commitments are missing.
- Therefore the dashboard is not decision-grade yet.

## Goals
### G32 — Cashflow truth baseline (opening balances + reconciliation)
Deliver:
1) Ability to set an opening balance anchor for CASH/RECEIVABLES/INVENTORY_COST at a chosen date.
2) Reconciliation report that proves cash_close on anchor date matches reality (5,000,000 KZT on 2026-01-22).

### G33 — Event imports (payouts, expenses, PO payments) + commitments
Deliver:
1) Import payouts (PAYOUT_RECEIVED) from manual CSV export (bank or Kaspi settlement).
2) Import expenses (EXPENSE) from CSV.
3) Model planned PO payments + OPEX as commitments (fact_cashflow_commitments) for forward-looking planning.

### G34 — Forecast engine + cash floor
Deliver:
1) Forecast next 120 days:
   - sales forecast (simple run-rate MVP)
   - payout lag model (parameterized)
   - apply commitments (OPEX + planned PO payments)
2) Compute min projected cash date/amount and “days-to-floor”.

### G35 — Owner-grade dashboard output
Deliver:
1) exports/cashflow_calendar.csv: last 90 days + next 120 forecast rows
2) exports/cashflow_dashboard.html:
   - summary panel: current cash, receivables, inventory_cost, capital
   - min cash date/amount + breach indicator
   - charts (Plotly ok) for cash/receivables/inventory/capital
   - table with filters (not a 500-row dump by default)

## Non-negotiables / guardrails
- Append-only events are source of truth.
- Derived daily table is rebuildable/deterministic.
- ALL write scripts default to DRY RUN.
- Apply requires both:
  - ENABLE_CASHFLOW_WRITE=1
  - explicit --apply flag
- DB backup before any write (use existing backup script).
- Stop at first gate failure and log issue.

## Implementation tasks
### Task 1 — Opening balance anchor
- Add support for OPENING_BALANCE events (or a dedicated opening balance table) for accounts:
  CASH, RECEIVABLES, INVENTORY_COST.
- Provide a template CSV:
  data/cashflow/opening_balances.csv
  Columns:
    as_of_date, account, amount_kzt, notes, source
- Add script:
  scripts/import_cashflow_opening_balances.py
  - idempotent via event_hash
  - dry-run default
  - emits exports/opening_balance_import_report.txt

### Task 2 — Payout import
- Create template:
  data/cashflow/payouts_import.csv
  Columns (minimum):
    event_date, amount_kzt, ref_id(optional), notes(optional)
- Extend scripts/import_cashflow_events.py or add a payout-specific importer.
- Emit:
  exports/payout_import_report.txt

### Task 3 — Expenses + recurring OPEX
- Create template:
  data/cashflow/expenses_import.csv
- ALSO implement a recurring commitment generator:
  scripts/generate_recurring_commitments.py
  - e.g., monthly OPEX 2,300,000 KZT from 2026-01-22 onward
  - writes to fact_cashflow_commitments (guarded)

### Task 4 — PO payment commitments (PO-4.1/4.2/5)
- Create template:
  data/cashflow/po_payment_plan.csv
  Columns:
    commit_date, amount_kzt, po_id/name, supplier, scenario_tag
- Load into fact_cashflow_commitments (guarded)
- Emit:
  exports/po_commitment_import_report.txt

### Task 5 — Reconciliation report (decision-grade gate)
- Add:
  scripts/reconcile_cashflow_to_known_cash.py
  Inputs:
    --as-of YYYY-MM-DD
    --known-cash-kzt 5000000
  Output:
    exports/cashflow_reconciliation_YYYYMMDD.md
  Behavior:
    - FAIL if mismatch > tolerance unless an ADJUSTMENT event exists.

### Task 6 — Forecast + dashboard UI
- Update scripts/update_cashflow_dashboard.py:
  - default range: last 90d history + next 120d forecast
  - compute min-cash + breach
  - render charts + compact table

### Task 7 — Gates + evidence
Run:
- python3 scripts/validate_cashflow_invariants.py
- python3 scripts/run_end_of_day.py --verbose
- pytest -q
- scripts/check_no_db_tracked.sh
- scripts/lint_docs.sh (if docs touched)

Evidence outputs required:
- exports/cashflow_calendar.csv
- exports/cashflow_dashboard.html
- exports/cashflow_reconciliation_20260122.md (or current date)
- exports/min_cash_summary.txt
- Oracle pack path with:
  - changed files
  - templates
  - sample outputs
  - DB backup path

## Definition of Done
- Cashflow dashboard shows CASH close = 5,000,000 KZT on 2026-01-22 after opening balance import.
- Payouts imported for recent period; receivables decreases on payout days.
- OPEX and PO payment plans appear in forecast and affect min cash.
- UI shows min cash date/amount and is readable in <30 seconds.
- All gates green.

## Next Actions
1) Implement Tasks 1–5 first (truth + reconciliation) before UI polish.
2) Only after reconciliation passes, trust projections for PO payments.
# SUPERSEDED (Truth Contract 2026-01-26)
This plan assumes receivables + payout lag. Current truth contract uses **D1 cash-in at DELIVERED** (no receivables model).  
Use for historical context only. See: `docs/CASHFLOW_TRUTH_CONTRACT_2026-01-26.md`.
