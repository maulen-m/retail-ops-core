# Source Acquisition Approval Request After Agent9135

Created: 2026-05-19 10:29 +05

## Current Decision

Agent9135 closed `YELLOW_RETAINED_SOURCE_ROUTE_BOARD`.

Agent914 should not run a copied-temp green-proof attempt yet because it would only rerun known stale stock, sales, and strict May 18 ads evidence.

## Why Approval Is Needed

No accepted local source packets currently exist for:

- fresh stock truth for `fact_inventory_snapshot_size` and `stock_ledger`;
- strict sales/SKU identity truth for `sales_fact_v2` beyond `2026-05-04`;
- strict same-day May 18 ads truth.

The current local route can only support:

- retained stock/sales blockers;
- copied-temp T-1 ads scope through `2026-05-17`;
- PO/single-truth route planning, not materialized green proof.

## Approval Option A: Full Read-Only Source Acquisition

Use this if the owner wants the fastest route toward a future Agent914 copied-temp green proof.

```text
I approve a read-only live stock source acquisition for the stock source packet lane, limited to STOREB, ACMEWEAR, and UNIVERSAL stock evidence for the declared as-of date, with no WebUI/Kaspi/API mutations, no stock/price/PO/cash changes, no production DB or workbook writes, and local evidence capture only.

OWNER APPROVES READ-ONLY KASPI/API/WEBUI SALES SOURCE FETCH FOR AGENT9132 OR SUCCESSOR: fetch post-2026-05-04 order-entry, order-status, and SKU identity evidence for STOREB, ACMEWEAR, and UNIVERSAL for copied-temp sales_fact_v2 source-packet proof only; no writes, no workbook changes, no production DB changes, no source-pointer changes, no scheduler changes, no publication authority, and no production apply.

APPROVE_READ_ONLY_ADS_SOURCE_FETCH_FOR_MAY18_COVERAGE_ONLY_NO_WRITES_NO_BID_BUDGET_CAMPAIGN_SPEND_CHANGES
```

## Approval Option B: Stock And Sales Only

Use this if the owner accepts copied-temp T-1 ads scope for now and wants to avoid strict May 18 ads acquisition.

```text
I approve a read-only live stock source acquisition for the stock source packet lane, limited to STOREB, ACMEWEAR, and UNIVERSAL stock evidence for the declared as-of date, with no WebUI/Kaspi/API mutations, no stock/price/PO/cash changes, no production DB or workbook writes, and local evidence capture only.

OWNER APPROVES READ-ONLY KASPI/API/WEBUI SALES SOURCE FETCH FOR AGENT9132 OR SUCCESSOR: fetch post-2026-05-04 order-entry, order-status, and SKU identity evidence for STOREB, ACMEWEAR, and UNIVERSAL for copied-temp sales_fact_v2 source-packet proof only; no writes, no workbook changes, no production DB changes, no source-pointer changes, no scheduler changes, no publication authority, and no production apply.
```

## Approval Option C: No Live Reads

Use this if the owner will manually provide local source exports instead.

Required local packets:

- stock source packet with source path, SHA, row count, capture/as-of time, store scope, SKU-size identity, category separation, target-table mapping, non-derived proof, and exception visibility rule;
- sales source packet with post-`2026-05-04` source rows, source-backed SKU identity, store/order/offer/size/quantity/status eligibility, source hash, and unmapped-row policy;
- optional May 18 ads source packet if strict same-day ads green is desired.

## Non-Authorization

These phrases authorize read-only acquisition only if pasted by the owner. They do not authorize production DB writes, workbook writes, scheduler/LaunchAgent/cron changes, source-pointer writes, Web_automation writes, external writes, ad-platform writes, bid/budget/campaign/spend changes, cash movement, supplier payment, PO commitment, stock changes, price changes, owner publication, production preflight, production apply, or treating copied-temp evidence as production truth.
