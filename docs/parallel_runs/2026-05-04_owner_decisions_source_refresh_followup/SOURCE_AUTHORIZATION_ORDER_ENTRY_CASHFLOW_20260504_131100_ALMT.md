# Source Authorization For Order Entry And Cashflow Recovery

Recorded: `2026-05-04 13:11:00 +0500`

Status: owner authorization captured. No DB, workbook, or statement files were modified by this document.

## Purpose

This document captures the owner-approved source scope for clearing the remaining order-entry and cashflow blockers from the `2026-05-03_c3-source-refresh-owner-review-wave`.

It supersedes the previous unresolved-owner-question state for these two blockers:

- `ORDER_ENTRY_MISSING=15046`
- `CASHFLOW_D1_CASH_IN_MISSING=20945`
- `CASHFLOW_D1_RECEIVABLES_MODELED=2187`

## Order-Entry Recovery Authorization

Owner-approved recovery hierarchy for `ORDER_ENTRY_MISSING=15046`:

1. Use the current CRM workbook first if it contains sufficient item-level data:

   `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`

2. Use existing closer-to-truth sources next where they can be tied to real order IDs, stores, dates, products, sizes, and quantities. Valid examples include Kaspi API entry fetches, existing DB tables, archive exports, source backups, and prior verified ingestion artifacts.

3. Use the archive workbook only as a reserve fallback:

   `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Sales_archive/SALES_KSP_CRM_GPT_Sales_archive.xlsx`

4. Never synthesize order entries from headers, totals, product-name guesses, or expected stock movement.

5. Any order still not recoverable from real evidence must remain quarantined from product-level stock, COGS, and profit publication.

## Cashflow Anchor Authorization

Owner provided a one-time full update from all stores' Kaspi Pay bank statements and sales reports.

New source root:

`~/Docs/agent_handoffs/kaspi_pay/20260504_131100/Statements/kaspi_stores`

Prior January raw backup if needed for reconciliation:

`~/Documents/External_database/snapshots.nosync/20260213_211004/External_database/kaspi_pay/statements/kaspi_stores`

Business meaning:

- Kaspi Pay is the exclusive bank ecosystem synced to the Kaspi merchant stores.
- Kaspi store sales transactions happen through this Kaspi Pay ecosystem.
- The provided statement/report package should be used to establish or repair a latest trusted cash anchor.
- Coverage source period is from `2026-01-01` through `2026-05-04 13:11:00 +0500`.
- Decision-grade cutoff should be through `2026-05-03` because `2026-05-04` was incomplete at extraction time.

## Future Cashflow Operating Rule

Owner-approved rule going forward:

- Do not rely on recurring manual bank statement downloads as the daily operating source.
- Treat the latest properly ingested statement/report package as a cash anchor/backfill input.
- After that anchor is ingested, daily cashflow should be computed deterministically from internal Kaspi API order and sales fetches plus the latest confirmed cash balance anchor.
- Actual cash must stay separate from modeled receivables.
- Bank or account balance snapshots can anchor/reconcile cash, but must not be converted into fake cash-in events.
- If API fetches, order lifecycle, payout timing, or reconciliation coverage are missing/stale, the cashflow gate must fail closed instead of silently publishing green.

## Source Inventory Verified

Read-only inspection found store folders for:

- `11KZ`
- `MELVIS`
- `STOREB`
- `ACMEWEAR`
- `Universal`

Each store folder contains one Kaspi Pay sales report workbook and one statement text file.

Sales report workbook inspection:

| Store | Workbook sheet | Max rows | Max columns |
|---|---:|---:|---:|
| `11KZ` | `Sheet1` | 70 | 39 |
| `MELVIS` | `Sheet1` | 100 | 39 |
| `STOREB` | `Sheet1` | 2321 | 39 |
| `ACMEWEAR` | `Sheet1` | 1484 | 39 |
| `Universal` | `Sheet1` | 3680 | 39 |

Statement text inspection:

| Store | Format observed | Line count |
|---|---:|---:|
| `11KZ` | MT940-like text | 1227 |
| `MELVIS` | MT940-like text | 904 |
| `STOREB` | MT940-like text | 9559 |
| `ACMEWEAR` | MT940-like text | 11923 |
| `Universal` | MT940-like text | 11488 |

Workbook source inspection:

| Source | Sheet | Max rows | Max columns | Use |
|---|---:|---:|---:|---|
| `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx` | `SALES_KSP_CRM_1` | 7954 | 66 | Primary CRM item-level recovery candidate |
| `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Sales_archive/SALES_KSP_CRM_GPT_Sales_archive.xlsx` | `Archive_sales` | 19131 | 52 | Reserve fallback recovery candidate |

## Required Next Execution Behavior

Order-entry lane:

- Build the missing-order list from current DB/gates.
- Attempt recovery from current CRM first.
- Attempt API/archive/source backup recovery next.
- Attempt the reserve archive workbook only after stronger sources are exhausted.
- Produce recovered, unrecovered, and quarantined counts by store and date.
- Do not apply DB writes without a backup, dry-run output, explicit apply gate, and post-apply validators.

Cashflow lane:

- Parse the provided statement/report package in read-only mode first.
- Establish coverage by store and date through `2026-05-03`.
- Determine the latest reliable cash anchor per store.
- Reconcile anchor totals against existing DB cashflow state without writing.
- Specify how deterministic daily API-derived cashflow will run after the anchor.
- Keep `ACTUAL` cash, `MODELED` receivables, and `UNKNOWN/UNRECONCILED` cash states separate.

## Stoplines

Stop if:

- an agent proposes synthetic order entries;
- cash balance is converted into fake cash-in events;
- current-day partial data is treated as complete through `2026-05-04`;
- statement downloads are designed as a recurring manual daily requirement;
- actual cash and modeled receivables are merged;
- a DB apply is attempted without backup and explicit write gate.
