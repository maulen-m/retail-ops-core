# Plain-English Explanation Of Remaining Blockers

Recorded: `2026-05-04`

Purpose: explain the remaining blockers in language a business owner can act on. This is not a DB change and does not authorize green publication.

## What `ORDER_ENTRY_MISSING=15046` Means

Plain English: the system knows many orders exist, but it does not have reliable line-item proof for those orders.

An order header usually tells us:

- order number;
- store;
- date;
- status;
- total amount.

An order entry tells us the actual item-level truth:

- which product/article was sold;
- which internal SKU it maps to;
- which size/color;
- quantity;
- item price;
- item-level status/evidence.

Why this matters:

- Stock cannot be reduced accurately by item/size without item-level entries.
- COGS cannot be assigned confidently without knowing the exact SKU/size.
- Profit by product can be wrong if the sale is mapped from a guessed product.
- The system must not invent these entries because that would create false stock/profit truth.

What the owner needs to do:

- You do not need to manually solve 15,046 orders one by one.
- You need to approve a recovery lane that fetches or rebuilds real order-entry evidence from trusted sources.

Trusted source options:

- Kaspi API order-entry endpoint for each order.
- Kaspi archive/order exports if they contain item/article/size data.
- Existing CRM workbook backups if they preserve item-level order rows.
- Existing DB/archive tables if they can be linked to the order IDs.

What not to do:

- Do not let an agent synthesize missing entries from product names, totals, or guesses.
- Do not treat order headers as sufficient item-level stock truth.

Owner approval wording that would unblock the next lane:

`I approve a read-only/live-read recovery lane to fetch or reconstruct missing order-entry evidence from Kaspi API/archive/CRM backups. Do not synthesize entries. If entries cannot be recovered from real evidence, quarantine those orders from product-level stock/profit publication.`

## What `CASHFLOW_D1_CASH_IN_MISSING=20945` Means

Plain English: the system has many sales/orders where it expects money should have come in, but it does not yet have matching actual cash-in evidence in the cashflow tables.

This is not saying the money is definitely missing from the bank. It means the operating database cannot prove the cash receipt yet.

Why this happens:

- Cashflow tables are stale or incomplete.
- Kaspi Pay/bank statements were not fully ingested for the period.
- The system modeled expected cash but did not match it to bank/account evidence.
- Some store payouts may exist in bank/account records but are not linked to the order/day in DB.

Why this matters:

- Revenue and profit may look correct by sales, but cash availability may be wrong.
- Cashflow forecasting can overstate cash on hand.
- Purchase/cargo decisions can become unsafe if expected cash is treated as received cash.

What the owner needs to do:

- You do not need to identify 20,945 items manually.
- You need to authorize the system to refresh actual cash-in evidence from Kaspi Pay/bank statements and reconcile it to orders.

Important rule:

- A bank balance snapshot is useful reconciliation evidence.
- A bank balance snapshot is not the same thing as a cash-in event.
- We should not create fake cash-in events just because the bank balance is high enough.

Owner approval wording that would unblock the next lane:

`I approve a cashflow source-refresh lane to ingest/reconcile real Kaspi Pay/bank cash-in evidence and keep ACTUAL cash separate from MODELLED receivables. Do not convert bank balance snapshots into cashflow events.`

## What `CASHFLOW_D1_RECEIVABLES_MODELED=2187` Means

Plain English: the system has modeled receivables for some orders, meaning it expects money to arrive or be receivable, but has not yet confirmed the actual cash-in evidence.

This can be normal for timing, but it must be labeled correctly.

Examples:

- Order is delivered and payout should happen soon, but actual bank/Kaspi Pay receipt is not ingested yet.
- Order cash-in was modeled from the order lifecycle but not confirmed from a statement.
- Statement coverage is missing or stale, so the system cannot say whether it is actual cash or only expected cash.

Why this matters:

- Modeled receivable can help forecast.
- It should not be counted as actual cash received.
- Profit/cashflow dashboards must clearly label this distinction.

Owner approval wording that would unblock the next lane:

`I approve keeping modeled receivables separate from actual cash. Actual cash must require statement/Kaspi Pay evidence; modeled receivables can be shown only as forecast/expected cash, not confirmed cash.`

## Practical Next Step

The next source-refresh wave should not ask the owner to manually solve thousands of rows. It should:

1. Build a list of missing order IDs and stores.
2. Try recovery from Kaspi API/archive/CRM backups.
3. Record which entries were recovered from real evidence.
4. Quarantine unrecovered orders from decision-grade product-level stock/profit.
5. Refresh actual cash-in evidence separately from modeled receivables.
6. Keep owner publication blocked until validators show the evidence is sufficient.
