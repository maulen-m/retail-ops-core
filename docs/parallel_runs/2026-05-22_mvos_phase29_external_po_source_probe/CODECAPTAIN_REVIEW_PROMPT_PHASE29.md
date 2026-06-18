# CodeCaptain Review Prompt: Phase29 External PO Source Rows Added To Current Boundary

Please review this amended current-boundary MVOS packet after Phase28 and Phase29.

The local orchestrator is asking for review only. This packet does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, external writes, WebUI/API mutations, ad-platform writes, cash movement, supplier payment, PO commitment, stock or price changes, owner publication, production preflight, or production apply.

## What Changed Since Phase28

Phase29 ran a source-filtered hinted scan and copied-temp materialization for two C3 source rows that were previously retained as missing because broad external-root scans were intentionally avoided.

Copied-temp result:

- `src_ecommerce_po_artifacts`: `FRESH`, max observed `2026-05-18T13:11:57+05:00`, row_count `2256`, `blocks_publication=0`.
- `src_sourcing_research_supplier_routes`: `FRESH`, max observed `2026-05-21T12:47:12+05:00`, row_count `82741`, `blocks_publication=0`.

Strict source freshness now has four retained errors instead of six:

- `src_ab_db_operational_truth`: `BLOCKED`.
- `src_bank_manual_ingest`: `STALE`.
- `src_facebook_ads_external_ads`: `STALE`.
- `src_web_automation_kaspi_marketing_directapi`: `BLOCKED`.

Strict policy gates remain unchanged at four blockers:

- `ads_source_truth`
- `cashflow_source_truth`
- `source_freshness`
- `stock_source_truth`

## Questions

1. Do you accept Phase29 as copied-temp closure for `src_ecommerce_po_artifacts` and `src_sourcing_research_supplier_routes`?
2. Do you agree the current remaining C3 source-freshness blocker list is now exactly the four retained source rows above?
3. Do you agree the policy gate stopline remains YELLOW until ads, bank/manual cash, operational rollup, Kaspi Marketing DirectAPI, and physical-stock/substitute contract issues are resolved or reviewed?
4. What is the safest next non-production lane: cash `Cash_Balances` route adoption review, ads source truth, status-ledger continuity, or operational-rollup/stock contract review?

## Known Stoplines

- Do not mark MVOS green.
- Do not begin production preflight/apply.
- Do not update source pointers from this packet.
- Do not turn copied-temp source-freshness proof into production truth.
- Do not zero missing ads spend.
- Do not treat payment evidence or Cash_Balances packet generation as full cashflow truth until reviewed and strict gates pass.
- Do not treat offer availability as physical stock truth.
