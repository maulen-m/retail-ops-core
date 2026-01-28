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

### B) Commission + delivery fees
- Commission is refunded on returns.
- Delivery fee charged to seller is **always a cost**, even on refunds.

### C) Refund / return
- Trigger: order becomes RETURNED (or CANCELLED after delivery).
- Event: **reverse cash-in**.
- Delivery fee **remains a cost** (not refunded).

### D) Cash payout
- In D1 mode, **cash is recognized at delivery**; no payout lag model is used for Kaspi Pay.
- Statements are used for **anchor + reconciliation**, not daily payouts.

### E) On-delivery policy (inventory-on-delivery)
- Orders with internal status **SHIPPED** (Kaspi: “Передан курьеру”) are treated as **ON_DELIVERY**.
- ON_DELIVERY is **inventory-at-cost**, tracked in `INVENTORY_ON_DELIVERY_COST`.
- No cash is recognized for ON_DELIVERY in base cashflow.

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
   - Export `exports/cashflow_calendar.csv` and `exports/cashflow_dashboard.html`.

4) **Recon if statements exist**
   - If Kaspi Pay statements are available, treat them as reconciliation
     (not required for daily operations).

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
