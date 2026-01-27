# Cashflow Q&A Document
## Phase: Discovery | Focus: Decision-Grade Cashflow Anchor

```
+==============================================================================+
|  OBJECTIVE: Define a decision-grade cashflow anchor (cash + receivables +    |
|  inventory at cost + commitments) with rules that won't break in practice.   |
|                                                                              |
|  Below is the exact clarifying-questions checklist I need you to answer so   |
|  we can lock a single, accurate anchor and stop "nonsense" cashflow outputs. |
+==============================================================================+
```

---

## A) Anchor Semantics (Date/Time + What "Anchor" Means)

### Anchor Timestamp Choice (Pick 1)

| Option | Description                                                                                      |
|--------|--------------------------------------------------------------------------------------------------|
| A1     | **(Recommended)** Anchor at end-of-day statement close for the last statement day (per account) |
| A2     | Anchor at your manual balance snapshot time (e.g., 2026-01-24 13:49 GMT+5), then treat the rest of that day as "post-anchor" |
| A3     | Anchor at start of day (00:00) of a chosen date                                                  |

**Question:** Which one do you want as the official "cashflow starts here"?

**Answer:** `A1`

---

### Timezone & Day Boundary

**Question:** Confirm the cashflow calendar day boundary is Asia/Almaty (GMT+5). Yes/no?

**Answer:** `Yes`

---

### Decision-Grade Horizon

**Question:** From what date should we label the calendar DECISION-GRADE (trustable for PO gating)?

| Option                              | Description                   |
|-------------------------------------|-------------------------------|
| from 2024-08-01                     | full MT940 history            |
| from last 90 days                   | recent history                |
| from last statement day             | fastest to stabilize          |

**Answer:** `From last statement day`

---

## B) Cash Scope: Which "Cash" Counts for PO Affordability

```
+--------------------------------------------------------------------------+
|  Context: You gave balances (as_of 2026-01-24 13:49 GMT+5) across many   |
|  accounts/currencies. Which accounts are "business-usable cash" for PO   |
|  payments?                                                               |
+--------------------------------------------------------------------------+
```

### Account Classification

**Question:** For each account type below, answer INCLUDE / EXCLUDE / INCLUDE WITH HAIRCUT:

- Kaspi Pay (per store)
- Kaspi Gold (per store)
- BCC / Freedom (per store)
- Physical cash KZT
- Binance USDT
- Cash USD / RUB

### Liquidity Haircuts

**Question:** (Recommended to avoid false affordability) If included, what haircut should apply to:

- USDT (e.g., count only 80-90% as usable)
- USD/RUB cash (count 0% unless you explicitly plan conversion)

Provide your haircuts or say "no haircuts".

**Answer:**

> We receive cash from Kaspi sales to each Pay store account, transfer to Kaspi Gold accounts (per respective store), transfer all to Universal Kaspi Gold (GOLD) account, transfer from Universal Gold for PO payment to Binance, convert to USDT, exchange Binance USDT (TRC20 network) to pay supplier on WeChat via certified exchange brokers (USDT to CNY WeChat).
>
> All money of all accounts is for business, it can fully be deployed for business (yes we can create some gates like min on hand always = 500,000 KZT).

---

### Internal Transfers

**Question:** Do you frequently move money between these accounts (Gold <-> Pay <-> bank)?

If yes, do we want to:
- **TRACK** transfers explicitly (recommended)
- **IGNORE** (will cause drift unless statements are updated)

**Answer:** `TRACK`

---

## C) MT940 Backfill: "One-Time Ingest" Rules

```
+--------------------------------------------------------------------------+
|  Context: You said statements will be ingested once from                 |
|  2024-08-01 -> yesterday.                                                |
+--------------------------------------------------------------------------+
```

### Statement Coverage

**Question:** Confirm we have MT940 files for each store account listed in `config/kaspi_pay_accounts.yaml` (UNIVERSAL, ACMEWEAR, 11KZ, MELVIS, STOREB). Any missing?

**Answer:** `All in place. Already ingested into DB (as agent said).`

---

### Backfill Reconciliation Target

**Question:** When statements exist, do we enforce:

| Option | Description              |
|--------|--------------------------|
| HARD   | Closing cash must match statement close within tolerance |
| SOFT   | Warn only                |

**Answer:** `HARD`

---

### Reconciliation Tolerance

**Question:** What tolerance is acceptable for "statement close vs computed close"? (e.g., +/-25,000 KZT or +/-0.2%)

**Answer:** `+/-5%`

---

## D) Orders -> Cash Timing Rules (CRITICAL)

```
+==============================================================================+
|  CRITICAL SECTION                                                            |
|                                                                              |
|  Context: You stated: "after customer receives the order, within 30 minutes  |
|  we receive it to Kaspi Pay."                                                |
|                                                                              |
|  This drives whether we even need a payout-lag receivables model for Kaspi.  |
+==============================================================================+
```

### Cash Recognition Moment

**Question:** For Kaspi orders, when do we record CASH_IN?

| Option | Description                                                |
|--------|------------------------------------------------------------|
| D1     | At DELIVERED (near immediate, ~30 minutes) - likely based on your note |
| D2     | At CLOSED (after return window ends)                       |
| D3     | At separate PAYOUT_RECEIVED events (if Kaspi batches settlements) |

**Answer:** `D1 (but with an option of return/refund within full 14 days for each order)`

---

### Receivables Necessity

**Question:** If you pick D1 (cash at delivered), do you still want to track RECEIVABLES at all?

> Yes if there's any meaningful delay/batching between "delivered" and cash actually usable.

**Answer:** `No`

---

### Return Window Rule

**Question:** Previously: "14 days after delivery; day 15 closes." Here you also mention "within 30 minutes cash received." That implies returns cause cash reversal later.

Confirm: return window = 14 days after delivered?

**Answer:** `Confirm, return window = 14 days after delivered.`

---

### Commission and Delivery Fee Rules on Refund

**Question:** Confirm your policy (you already stated it, I want it locked as a contract):

1. Commission previously taken returns to seller when refunded/cancelled (YES/NO)
2. Delivery fee is not refunded to seller (YES/NO)
3. Partial refunds exist? (YES/NO) and if yes: do we pro-rate commission reversal?

**Answer:**

Kaspi's Partner Guide states that the **sales commission is returned** to the seller when a return is processed, and that **Kaspi Delivery cost is not refunded** to the seller if the item was issued and then returned (the seller pays the full delivery cost).

#### YES/NO Confirmation

| Policy                                                           | Answer  |
|------------------------------------------------------------------|---------|
| Commission previously taken returns to seller when refunded/cancelled | **YES** (commission is automatically returned after you process the return in the seller cabinet) [^1] |
| Delivery fee is not refunded to seller                           | **YES** (for returns after issuance, the partner pays the full delivery cost) [^2] |

#### What Happens by Scenario

| Scenario | Commission | Kaspi Delivery Fee |
|:---------|:-----------|:-------------------|
| Buyer cancels before order is issued ("Issued") | No completed sale; commission is tied to "successful sale / issued" status, so it should not be charged. [^3][^4] | Delivery cost is deducted only for issued orders; on cancellation "money is not deducted". [^2] |
| Buyer received order ("Issued") and then returns it | Commission is automatically returned to your Kaspi Pay account after you process return in the seller cabinet. [^1] | Partner pays the full delivery cost (i.e., it is not refunded); Kaspi covers the reverse shipment back to the acceptance point. [^2][^5] |

> Also: Here's what statuses orders can have (attached as docs and API statuses).

---

## E) On-Delivery Inventory and Risk Exposure

```
+--------------------------------------------------------------------------+
|  Context: You provided on-delivery totals                                |
|  (161 units, Net Rev 894,476, COGS 544,403).                             |
+--------------------------------------------------------------------------+
```

### How to Treat ON_DELIVERY in the Cashflow Anchor

**Question:** Pick one:

| Option | Description                                                              |
|--------|--------------------------------------------------------------------------|
| E1     | **(Recommended)** ON_DELIVERY stays in inventory at cost (still your asset), and is shown as On-delivery exposure (not cash, not revenue) |
| E2     | Treat ON_DELIVERY as receivable (more aggressive)                        |
| E3     | Treat ON_DELIVERY as sold (not recommended; too optimistic)              |

**Answer:** `E1`

---

### Inventory Classification

**Question:** If E1: do you want ON_DELIVERY tracked as:

| Option                                | Description              |
|---------------------------------------|--------------------------|
| INVENTORY_COST                        | Same account             |
| INVENTORY_ON_DELIVERY_COST            | Separate sub-account (recommended for clarity) |

**Answer:** `Separate sub-account INVENTORY_ON_DELIVERY_COST`

---

### Cancelled/Returned Report Valuation

**Question:** You said: "include Cancelled/Returned as just COGS."

Confirm the cancelled/returned "value" should be:
- COGS only (ignore delivery fee)
- COGS - delivery fee (older method)

**Answer:**

> `COGS only (ignore delivery fee)`
>
> If 1 item goes 100 times for new orders and 100 times cancels it will not mean that the order is negative COGS. Underlying value of the item is not lost - we should just append delivery as an operating expense type. COGS never loses value unless damaged during shipping/defected.

---

## F) Inventory Valuation Rule (Base Cost vs Landed Cost, Partial Payment)

```
+==============================================================================+
|  MOST IMPORTANT "PHYSICS" PIECE                                              |
|                                                                              |
|  This is the most important "physics" piece you highlighted.                 |
+==============================================================================+
```

### When Does Inventory Cost Increase?

**Question:** Choose primary rule:

| Option | Description                                                                |
|--------|----------------------------------------------------------------------------|
| F1     | On PO payment (capital spent -> inventory asset increases)                 |
| F2     | On PO arrival (inventory exists physically/in system -> increases)         |
| F3     | **(Hybrid)** Base cost on supplier payment; delivery/extra landed costs when paid/known (this matches your example) |

**Answer:** `F3 (pure cash transition, if money leaves bank account, it instantly becomes inventory)`

---

### Landed Cost Components

**Question:** If F3:
- When PO is only paid for product: record BASE_COST only (CNY -> KZT)
- When PO arrives to Astana and delivery is paid: add DELIVERY/LANDED cost

**Answer:** `Confirm`

---

### Inbound vs On-Hand in "Inventory Value"

**Question:** For cashflow anchor, do you want INVENTORY_COST to include:

| Option                     | Description                |
|----------------------------|----------------------------|
| on-hand only               | warehouse stock only       |
| on-hand + inbound          | POs in transit included    |

**Answer:** `On-hand + inbound (POs in transit), since money never disappears, it flows from one state (bank account) to another state (inventory).`

---

### Anchor Inventory Date

**Question:** Which snapshot date should be used as INVENTORY_OPEN?

| Option                                      | Description                     |
|---------------------------------------------|---------------------------------|
| latest snapshot on/before anchor date       | (Recommended)                   |
| a specific "trusted" date you choose        | e.g., 2026-01-14                |

**Answer:** `Latest snapshot on/before anchor date (recommended)`

---

## G) PO Payment Schedule Truth (Commitments)

```
+--------------------------------------------------------------------------+
|  Your preflight only becomes "real" if commitments match reality.        |
+--------------------------------------------------------------------------+
```

### PO Payment Schedule for PO-4.1 / PO-4.2 / PO-5

**Question:** For each PO, provide:

- Supplier base cost total (CNY)
- Amount already paid (CNY) + date(s)
- Remaining payment dates/amounts (CNY)
- Delivery/forwarder payments (USD/KZT), dates

You already said: PO-4.1 paid 20,500 CNY.

Confirm:
- Payment date(s) for that 20,500
- Whether PO-4.1 is shipped/arrived and which costs are still pending

**Answer:**

> PO-4.1 paid 20,500 CNY at 22.01.2026.
>
> For all inbound data, see attached XLSX file.
>
> **Note:** If `cargo_send_date > today` - it's an estimate date.

---

### CNY Holiday Deferral Policy

**Question:** You said supplier allows delay until 2026-03-01.

Is this:
- A hard commitment date (must pay by 03-01)
- Flexible window (pay between 02-15 and 03-10)
- Partial payments before 03-01

Choose and specify.

**Answer:** `Flexible window, between today and 10.03.2026.`

---

## H) OPEX and Cash Floor (Capital Safety)

### OPEX Schedule

**Question:** Monthly OPEX = 2,300,000 KZT.

What is the timing?
- Paid on the 1st?
- Spread across month?
- Rent date + payroll date(s)?

Give a simple schedule.

**Answer:**

> Full monthly OPEX is **2,652,000 KZT** as of today.
>
> Attached full list of payments and their day of the month payment schedule. All Gold loans end after 25.07.2026.
>
> **Reference:** Read `OPEX_protocol_26.01.2026.xlsx` for complete info.
>
> Path: `~/Docs/kaspi_etl/docs/ops/kaspi/Backups/OPEX_protocol_26.01.2026.xlsx`

---

### Cash Floor Rule

**Question:** What is the minimum cash buffer that must never be breached (downside scenario)?

| Option                | Example                        |
|-----------------------|--------------------------------|
| fixed KZT             | e.g., 2,000,000                |
| X months of OPEX      | e.g., 1.0x or 1.5x monthly     |

**Answer:** `X months of OPEX (e.g., 1.0x or 1.5x monthly)`

---

## I) Data Freshness and Trust Labels (Operating Model)

```
+--------------------------------------------------------------------------+
|  Context: You don't want daily bank statement ingest; you want API       |
|  order tracking.                                                         |
+--------------------------------------------------------------------------+
```

### Balance-Check Cadence

**Question:** If we don't ingest statements daily, how often can you provide a manual balance snapshot (from app or accounts)?

- daily
- weekly
- only when needed

**Answer:** `Only when needed. Mostly we need to build automatically from API order tracking.`

---

### Stale API Gate Strictness

**Question:** If the daily 14-day rolling Kaspi sync fails for any store:

| Option     | Risk Level |
|------------|------------|
| block EOD  | strict     |
| warn only  | riskier    |

**Answer:** `Block EOD`

---

### Which Stores Are "Must Be Green" for Decision-Grade

**Question:** UNIVERSAL, 11KZ, STOREB, ACMEWEAR, MELVIS: all must be fresh?

List which are mandatory.

**Answer:** `UNIVERSAL; STOREB, ACMEWEAR`

---

```
+==============================================================================+
|                           END OF Q&A DOCUMENT                                |
+==============================================================================+
```

---

## Footnotes

[^1]: Commission return policy reference
[^2]: Delivery fee policy reference
[^3]: Commission timing reference
[^4]: Order status reference
[^5]: Reverse shipment policy reference
