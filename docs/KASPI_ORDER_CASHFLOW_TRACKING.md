# Kaspi Orders → Cashflow Tracking (API-First)

**Goal:** track cashflow daily from Kaspi order status data with minimal manual bank downloads.
This is intentionally **API-first**: we accept small deviations from bank statements in exchange
for autonomous, always-on maintenance.

---

## 1) Why API-first is acceptable for cashflow

**Kaspi Pay statements are the highest fidelity**, but they require manual downloads
and are fragile (human-in-the-loop). This system prioritizes reliability and continuity:
- API data is available daily, consistently, across all stores.
- If we capture full 14‑day windows **every day**, we never lose status changes.
- Cash is recognized **at delivery (D1)**; no receivables model is used for Kaspi Pay.

**Trade-off (explicit):** minor deviations vs bank statements are acceptable when the
system remains autonomous and deterministic.

---

## 2) Key rules and constraints

1) **Refunds and commissions**
   - When an order is refunded/returned, **Kaspi commission is returned** to the seller.
   - **Delivery fees are NOT refunded** to the seller (they remain a cost).

2) **Refund window**
   - Customer can refund within **14 days after delivery** (Asia/Almaty, GMT+5).
   - On day 15 (00:00+), the order becomes final/closed; no further status updates.

3) **API lookback limit**
   - Kaspi API only allows **max 14 days of history** per request.
   - Therefore: a **daily scheduled full 14‑day sync** is mandatory for completeness.

---

## 3) Lifecycle contract (used for cashflow events)

Use the canonical lifecycle mapping in:

- `docs/KASPI_ORDER_LIFECYCLE_AND_STATUS_CONTRACT.md`

**Important:** API `state` and API `status` are distinct. Cashflow triggers must be derived from StageCode
(state + status + flags), not from a mixed “state table”.

---

## 4) Cashflow event mapping (API-first)

We track **events** and derive daily cashflow calendars. Suggested mapping:

### A) Cash-in at delivered (D1)
- Trigger: order reaches **COMPLETED** (delivered).
- Event: `CASH_IN` to the store’s **Kaspi Pay** cash account.
- **No receivables model for Kaspi Pay** in D1 mode.
- Order-line economics must use an exact unique active
  `dim_kaspi_article_map` identity when the operational order row's
  `kaspi_article` resolves there. That canonical identity supersedes a raw
  alias-shaped `sku_key` for cost lookup. When the exact mapping intentionally
  has no `sku_id`, retain the operational row's exact article identity as the
  line ID; an ambiguous article mapping remains unresolved and must not be
  guessed.

### B) Commission + delivery fees
- Commission is refunded on returns.
- Delivery fee charged to seller is **always a cost**, even on refunds.

### C) Refund / return
- Trigger: order becomes RETURNED (or CANCELLED after delivery).
- Event: **reverse cash-in**.
- Delivery fee **remains a cost** (not refunded).

Returns-economics validation is order-scoped, not a monthly event-presence
proxy:

- A mature returned order that has recognized positive D1 `CASH_IN` must have
  a negative ordinary `CASH_IN` or explicit `REFUND` linked to that same order
  or its exact current entry IDs. An unrelated refund in the same month is not
  evidence for the order.
- A returned order with no recognized positive cash has no cash-in to reverse.
  It must remain excluded from delivered sales truth, but absence of a refund
  event is not itself a ledger gap. The audit reports it separately as
  `NO_RECOGNIZED_CASH_TO_REVERSE` rather than inventing a negative cash row.
- A negative `CASH_IN` created under the exact `ORDER_CASH_REPAIR`
  supersession contract is a correction, not a customer refund, and cannot
  satisfy the return-reversal requirement.
- When the current first-party order row is `RETURNED` but append-only status
  history has not yet captured the terminal observation, the translator may
  reverse an earlier positive `ORDER_ENTRY` cash row only through its exact
  current entry-to-order/store link. The reversal uses the current return
  observation date and the exact positive cash amount/reference; it must not
  require the earlier delivery cash to share the return date or recompute the
  amount from a possibly incomplete product row. Ambiguous entry scope or
  multiple exact positive rows fails closed.
- Monthly return/refund counts remain diagnostics only. The strict gate is the
  exact returned-order/store reference join plus stale-sales exclusion.

### D) Cash payout
- In D1 mode, **cash is recognized at delivery**; no payout lag model is used for Kaspi Pay.
- Statements are used for **anchor + reconciliation**, not daily payouts.

### E) On-delivery policy (inventory-on-delivery)
- Orders with internal status **SHIPPED** (Kaspi: “Передан курьеру”) are treated as **ON_DELIVERY**.
- ON_DELIVERY is **inventory-at-cost**, tracked in `INVENTORY_ON_DELIVERY_COST`.
- No cash is recognized for ON_DELIVERY in base cashflow.
- Historical `INVENTORY_SETTLEMENT` events are surrogate terminal closures, not
  canonical COGS. If canonical completed-order cash and COGS arrive after such a
  settlement has already reduced the exact order/SKU on-delivery balance to
  zero, the translator must append an equal-and-opposite
  `INVENTORY_SETTLEMENT_REVERSAL` linked to that one exact settlement before it
  appends canonical `COGS_RECOGNIZED`. The prior settlement must be unique for
  the exact order/SKU, have a valid event hash, and equal the canonical line
  cost; otherwise translation fails closed. A canonical replay must leave the
  order/SKU on-delivery balance at zero and a second replay must emit no event.

---

## 5) How to maintain full history with a 14‑day API limit

**Daily rule (no exceptions):**
- Every day, run a full 14‑day API sync for all stores.
- Store all order status changes in `fact_orders_kaspi` (append / upsert).
- This ensures that any order that changes status during its 14‑day window is captured.

**Why this works:**
- Orders can only change status within ~14 days after delivery.
- If we always capture every rolling 14‑day window, we never miss changes.

---

## 6) Inventory valuation scope (F3)

- Inventory value includes **on-hand + inbound**.
- **Base cost** is capitalized when supplier payment is made.
- **Landed costs** are added when paid/known.
- On-delivery inventory is tracked separately via `INVENTORY_ON_DELIVERY_COST`.

---

## 7) Recommended implementation pattern

1) **Orders sync**
   - `scripts/sync_kaspi_orders.py --all --since <cutoff>` (daily in EOD).
   - Maintain `fact_orders_kaspi` as the single truth for lifecycle and state.

2) **Cashflow events**
   - Use a translator that maps order state transitions to `fact_cashflow_events`.
   - Ensure events are **idempotent** (event_hash unique).

3) **Daily calendar**
   - Rebuild `fact_cashflow_daily` deterministically from events.
   - If `cashflow_cash_anchor` contains a reconciled `ACTUAL_ANCHOR`, the latest
     anchor date is a cash re-base point: the opening operating cash for that date
     is the sum of that anchor set's `anchor_closing_balance_kzt` rows. Non-operating
     reserve context recorded in anchor notes stays excluded from operating cash.
   - Cash events dated before the anchor, and same-day events that cannot prove they
     occurred after the anchor timestamp, must not be replayed into the post-anchor
     opening. Only cash events after the anchor timestamp/date may move the curve.
   - Forecast/preflight reports must disclose the anchor date, anchored operating
     opening, and whether modelled inflows are present after the anchor so ACTUAL
     cash and MODELLED movement remain visible.
   - Export `exports/cashflow_calendar.csv` and `exports/cashflow_dashboard.html`.

4) **Recon if statements exist**
   - If Kaspi Pay statements are available, treat them as reconciliation
     (not required for daily operations).

5) **Monthly D1 sales-to-cash reconciliation**
   - Cohort on the sale order from `view_sales_line_truth`, not on the cash
     event's delivery/reversal month.
   - Use positive and negative `CASH_IN` rows for the order. Do not mix the
     obsolete `SALE_ACCRUED + REFUND` convention into current D1 parity.
   - The delivery cost input is the seller fee from
     `fact_orders_kaspi.delivery_cost_for_seller`, allocated exactly once
     across the order's entry lines in proportion to their gross amounts.
     `order_entries.deliveryCost` is buyer-facing evidence and must never be
     substituted for the seller fee. A genuinely missing seller fee remains
     missing and uses the canonical modelled delivery matrix; it must not be
     coerced to zero. When an order header amount covers multiple units, divide
     it by quantity before applying unit economics, then multiply the canonical
     unit net amount by quantity for the line total.
   - Prefer cash linked by `ORDER_ENTRY` through
     `fact_order_entries_kaspi.entry_id -> order_id` only after exact entry-set,
     store, and quantity parity with the sales order. Partial or duplicate entry
     evidence is a stopline. Use `ORDER` cash only when no `ORDER_ENTRY` cash
     exists for that order, and never add both reference types together.
   - Require exact order/store identity and complete per-order coverage before
     treating a closed month/store pair as decision-grade. The detailed contract
     is `docs/validation/SALES_ECONOMICS_TRUTH_CONTRACT.md`.
   - A source-proven mapped order whose historical cash-account events are
     superseded must be repaired append-only. Each stale `CASH_IN` or
     cash-account payout row remains immutable and receives exactly one
     equal-and-opposite row on the same date, event type, account, store, SKU
     identity, and `ORDER` reference. The reversal must use source
     `ORDER_CASH_REPAIR`, a nonblank fixed repair run ID, a valid event hash,
     and notes that bind the numeric `supersedes_cash_id`, the superseded
     64-hex event hash, the exact order ID, and a versioned repair key. A
     complete repair manifest must pin every full preimage and every
     replacement `ORDER_ENTRY` row; partial sets, extra rows, hash drift, or an
     unequal pair are fail-closed.
   - A validated negative `CASH_IN` row with that exact `ORDER_CASH_REPAIR`
     supersession contract is a ledger correction, not a customer refund. It
     still affects the cash-account roll-forward and must net with its
     superseded positive row, but `rebuild_cashflow_calendar.py` excludes it
     from `refunds_kzt`. Ordinary negative `CASH_IN` and explicit `REFUND` rows
     remain refunds. This classification does not authorize cash mutation;
     copied and production application retain their separate write gates and
     approvals.

---

## 8) Using orders data for cashflow categories

**Credits (inflows):**
- Delivered orders (COMPLETED) → cash (Kaspi Pay account)
- Statement-backed payouts (if available) → reconciliation only

**Debits (outflows):**
- Commission (always)
- Seller delivery fees (always)
- Refund reversals (reverse revenue; commission refunded, delivery fee not refunded)

---

## 9) Reliability notes

- API-first flow is resilient to missing bank statements.
- Minor differences vs bank ledger are acceptable if:
  - the order lifecycle is fully captured daily
  - refunds are applied correctly
  - commissions and delivery fees follow rules above

---

## 10) Source-of-truth files

- docs/KASPI_API_INTEGRATION.md
- docs/Kaspi_API_Official_document_8.12.2025_GP.md
- scripts/sync_kaspi_orders.py
- core/integrations/kaspi_api_client.py
- core/sync/order_sync_engine.py
- docs/DAILY_SOP.md

---

## 11) Paid-Capital Truth (2026-02-08)

Base capital monitoring is anchored to paid truth components:
- `cash_actual_kzt`: from `config/bank_accounts.yaml`
- `inventory_on_hand_paid_kzt`: latest on-hand valuation (Astana treated as fully paid)
- `inventory_inbound_paid_kzt`: `po_part` paid portions only (`is_paid_base`, `is_paid_dlv`, `to_pay_*`)
- `inventory_on_delivery_paid_kzt`: latest `fact_cashflow_daily.inventory_on_delivery_close`

Unpaid inbound obligations are tracked separately and excluded from paid capital:
- `inbound_unpaid_obligations_kzt`

Implementation reference:
- `core/cashflow/paid_capital_truth.py`
- `scripts/update_cashflow_dashboard.py`

---

## 12) Dashboard Lens Contract (2026-02-08)

- Default operator lens is `PAID_TRUTH`:
  - `receivables_close` is forced to `0` in summary/cards/chart/table/statistics.
  - cash and capital are anchored to paid-capital truth (`bank_accounts.yaml` + paid inventory components).
- `MODEL LEDGER` remains available as an explicit UI toggle for diagnostics.
- Legacy `ORDER_MODELLED` receivables are excluded from actual roll-forward in
  `scripts/rebuild_cashflow_calendar.py`.

Validation hooks:
- `scripts/validate_on_delivery_freeze.py`
- `scripts/validate_single_truth_system.py`
- `scripts/validate_inventory_cost_drift.py` defaults to the paid-truth operator lens for the production DB: latest stock snapshot on-hand valuation must match `paid_capital_truth.inventory_on_hand_paid_kzt`; paid inbound obligations stay on the `po_part` paid/unpaid route rather than being inferred from `fact_inventory_snapshot_size.inbound_stock`.
- `scripts/validate_params.py --strict` (includes both checks)

---

## 13) OPEX + Business Insides Single Truth (2026-02-08; updated 2026-07-02)

OPEX commitments are now managed by canonical repo artifacts and synchronized into DB:
- `config/opex/opex_schedule.yaml`
- `config/opex/opex_commitments.csv`
- current Stage-B sync entrypoint: `scripts/apply_opex_owner_input_schedule.py`
- legacy January-protocol sync entrypoint: `scripts/sync_opex_schedule.py`

For commitments dated on or after `2026-07-02`, the upstream source is the owner-input
workbook `exports/opex_owner_input/2026-07-02/OPEX_and_Loans_OWNER_INPUT_MINIMAL_20260702.xlsx`,
normalized by `core/cashflow/opex_owner_input.py` / `scripts/normalize_opex_owner_input.py` and
governed by `config/owner_decisions/opex_loans_floor_refresh_2026_07_02.json`. The prior
`OPEX_protocol_26.01.2026.xlsx` is retired as the source for new OPEX commitments from this
boundary forward; it remains historical context only.

Stage-B OPEX DB writes are date-scoped replacements: delete and reinsert
`fact_cashflow_commitments` rows where `commit_type='OPEX'` and `commit_date >= '2026-07-02'`.
Rows before `2026-07-02` are preserved for historical owner PnL.

Business-insides snapshots are generated from paid-capital truth + delivered sales truth:
- generator: `scripts/generate_business_insides.py`
- snapshot path:
  - `config/business_insides/BUSINESS_INSIDES_<as_of>.md`
  - `config/business_insides/snapshots/BUSINESS_INSIDES_<as_of>.md`

Sales metrics source for business-insides:
- `sales_fact_v2`
- filter: `status='DELIVERED'` and `return_flag=0`
- COGS fallback: `dim_sku.cogs_kzt` (or canonical cost formula if missing)

On-delivery settlement reconciliation:
- `scripts/reconcile_on_delivery_settlement.py`
- validator remains `scripts/validate_on_delivery_freeze.py`
