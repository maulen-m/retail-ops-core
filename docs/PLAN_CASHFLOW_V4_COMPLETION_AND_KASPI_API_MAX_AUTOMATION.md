# PLAN — Cashflow V4 Completion + Kaspi API Max-Automation (Post Truth-Contract)

Repo: ~/Docs/Autonomous_business
Owner: Adil
North-star: A single conservative Treasury + Capital control plane that blocks unsafe POs by default.

## 0) Source-of-truth contract (NON-NEGOTIABLE)
**Canonical doc:** docs/CASHFLOW_TRUTH_CONTRACT_2026-01-26.md

Contract summary (must be reflected in code + UI):
- Anchor: A1 = end-of-day MT940 statement close per account (statement truth).
- Timezone/day-boundary: Asia/Almaty (GMT+5).
- Orders→cash: D1 = cash-in at DELIVERED (~30 min), refunds reverse cash later (within 14-day window).
- On-delivery: E1 = stays inventory-at-cost (separate subaccount INVENTORY_ON_DELIVERY_COST).
- Inventory valuation: F3 = cash leaving accounts instantly becomes inventory at cost; landed cost added when paid/known.
- Inventory scope: on-hand + inbound + on-delivery (capital never disappears; it changes state).
- Decision-grade horizon label: from last statement day (ACTUAL), then MODELLED, then FORECAST.

**Rule:** Any doc contradicting this is either edited or marked SUPSERSEDED.

---

## 1) Phase V4.1 — Commitments realism (G45) ✅ capital protection priority
Goal: Preflight blocks based on *real* commitments (PO split payments + OPEX schedule) under conservative scenario.

Deliverables:
1. data/cashflow/po_payment_plan.csv supports:
   - multiple rows per PO (split payments)
   - scenario_tag in {base, conservative}
   - currency + fx_policy fields (if non-KZT)
2. Importer loads commitments with scenario_tag preserved.
3. Preflight computes:
   - min_cash_base (informational)
   - min_cash_conservative (GATING)
   - FAIL if min_cash_conservative < cash_floor_kzt
4. Cash floor parameters are CONFIG-driven (no magic numbers):
   - abs_floor_kzt = 500_000
   - base_floor_mult_months = 1.0
   - cons_floor_mult_months = 1.5

Acceptance:
- A deposit-now + remainder-later schedule visibly creates a cash dip.
- Conservative scenario is what blocks the PO unless explicitly overridden with a logged reason.

Gates:
- python3 scripts/validate_params.py --strict
- ENABLE_CASHFLOW_WRITE=1 python3 scripts/run_end_of_day.py --verbose
- python3 scripts/validate_cashflow_invariants.py
- pytest -q

---

## 2) Phase V4.2 — Returns/refund risk reserve (NEW, required under D1)
Goal: Prevent “cash looks fine” while latent refunds can claw back cash.

Deliverables:
1. Conservative scenario adds a REFUND_RESERVE liability:
   - derived from last 14 days delivered net cash-in × reserve_rate
   - reserve decays as orders exit the 14-day return window
   - reserve_rate configurable (start conservative; tune later)
2. UI shows:
   - reserve balance
   - reserve driver (window + rate)

Acceptance:
- Conservative min cash becomes more conservative immediately after high-volume delivery days.
- Reserve decays deterministically with time (no manual edits).

Gates:
- pytest -q (unit tests for reserve curve + decay)
- validate_cashflow_invariants (no negative/liability sign flips)

---

## 3) Phase V4.3 — On-delivery policy completion (G46)
Goal: Visibility + optional aggressive scenario credit, without contaminating base truth.

Deliverables:
1. Canonical status mapping in ONE place (code + doc):
   - DELIVERED/COMPLETED → CASH_IN (D1)
   - REFUNDED/RETURNED → CASH_REVERSAL + commission reversal; delivery cost stays expense
   - ON_DELIVERY/SENT → inventory reclass only (INVENTORY_ON_DELIVERY_COST)
2. Dashboard shows on-delivery counts and net value by store.
3. Aggressive scenario (optional) uses on_delivery_credit_rate (configurable).

Acceptance:
- Base scenario remains cash-safe.
- Aggressive scenario is clearly labeled “non-gating”.

---

## 4) Phase V4.4 — Trust banner V4 + drift report (G47–G48)
Goal: Make drift and trust auditable without daily statements.

Deliverables:
1. Trust report includes:
   - last_statement_date
   - last_balance_check_date
   - per-store last_orders_sync_ts and age hours
   - counts: statement_backed_days, manual_balance_days, modelled_days
2. Drift report must respect coverage:
   - drift window = overlap(statement_window, api_order_coverage_window)
   - outputs coverage_pct; if insufficient, says “INSUFFICIENT COVERAGE”
3. EOD gate behavior:
   - if any must-be-green store stale beyond threshold → BLOCK (per owner policy)
   - must-be-green: UNIVERSAL, STOREB, ACMEWEAR

Acceptance:
- Banner always states ACTUAL/MODELLED boundary dates and why.
- Drift report is actionable (not dominated by days with no API coverage).

---

## 5) Phase V4.5 — Governance + evidence pack (G49)
Goal: Prevent regression and “doc drift”.

Deliverables:
1. Remove/mark superseded any doc that models receivables/payout lag for Kaspi if D1 is active.
2. Tests:
   - commitment scenario split import
   - trust banner derivation
   - refund reserve calculation
   - on-delivery classification
3. Oracle pack (full scope, exclude /exports):
   - changed files list
   - commands executed
   - DB backup path
   - migration notes

Required gates (do not claim done without ALL):
- python3 scripts/validate_params.py --strict
- ENABLE_CASHFLOW_WRITE=1 python3 scripts/run_end_of_day.py --verbose
- python3 scripts/validate_cashflow_invariants.py
- pytest -q
- scripts/check_no_db_tracked.sh
- scripts/lint_docs.sh (if docs changed)

Rollback:
- Always DB-backup before writes.
- If regression: git revert + restore backup.

---

## 6) Phase API.1 — Kaspi API enrichment (Q7/Q8/Q9/Q11) “maximum potential”
Goal: Eliminate Excel dependency + enable correct multi-item orders and partial cancels.

Deliverables:
1. Add read-only endpoints:
   - GET /orderentries/{id}
   - GET /orderentries/{id}/product
   - GET /masterproducts/{id}/merchantProduct
   - GET /pointofservices/{id}
2. Add cache/dim tables to avoid repeated calls:
   - dim_point_of_service
   - dim_masterproduct
   - dim_merchantproduct
3. Add fact table:
   - fact_order_entries_kaspi (line items linked to order_id)
4. Optional enrichment stage (default OFF):
   - only for new/changed orders
   - fail-open (log warning, continue)
   - rate-limited / cached

Acceptance:
- Multi-item orders no longer misrepresented as qty=1.
- Partial cancel support becomes feasible and auditable (write endpoints remain gated behind ENABLE_KASPI_WRITE=1).

---

## Definition of Done (80–90% “autonomous-ready”)
- Daily pipeline runs: Kaspi sync → deterministic cashflow rebuild → preflight gating → dashboards.
- Conservative scenario blocks unsafe POs (floor + commitments + refund reserve).
- Trust banner makes “what is real” explicit.
- API enrichment can be enabled safely without breaking core pipeline.
