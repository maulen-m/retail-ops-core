# Owner Answers And Decisions

Recorded: `2026-05-04 12:54:48 +0500`

Status: owner truth captured, not yet DB/materializer ingested.

## Purpose

This document records the owner answers provided after the `2026-05-03_c3-source-refresh-owner-review-wave` final review. These answers should be used by the next execution wave to convert owner decisions into explicit owner-decision records, exception resolutions, quarantine handling, PO/inbound source truth, and source-refresh scope.

Do not treat this document as evidence that DB/workbook state has already been updated. It is a fresh owner-truth input for the next gated implementation.

## Stock Owner Decisions

### Black T-shirt Owner OOS Hold

Decision: keep active sellable stock at `0` for black T-shirt sizes `S`, `M`, and `L`.

Reason: employees still could not find stock units for these item sizes in the warehouse. Even if stock exists on paper, it cannot be marketed as active sellable stock. If paper stock remains, represent it as quarantine/unknown physical stock and move forward operationally as active sellable `0`.

Business effect: this should not block further business decisions.

### LINE52 Black 4XL Owner OOS Hold

Decision: same as black T-shirt OOS hold. Treat LINE52 black `4XL` as active sellable `0`.

Additional owner note: manual LINE52 product-size stock ingestion around the April 16 period was observed from the real warehouse by the human owner. That observed truth should remain part of stock lineage, but this specific active sellable decision remains `0` if current sellable units cannot be found.

Business effect: this should not block further business decisions.

### Line61 Family No-Double-Reduce

Decision: rebuild Line61 from:

`~/Docs/Oracle/Autonomous_business/2026-04-24/103302_TASK-000_line51-root-cause-external-second-pass-2026-04-24/expert_answer/24.4.2026/second_pass_stock_value_evaluation_2026-04-24.xlsx`

Exception: Line61 `4XL` is active sellable `0`, same quarantine/OOS logic as black T-shirt sizes. Employees could not find 4XL stock in the warehouse. Warehouse space constraints make physical verification hard, so any paper stock should be treated as quarantine/unknown, not sellable.

Business effect: Line61 `4XL` quarantine/OOS should not block further business decisions.

### LINE51 White Family No-Double-Reduce

Decision: rebuild LINE51 white from:

`~/Docs/Oracle/Autonomous_business/2026-04-24/103302_TASK-000_line51-root-cause-external-second-pass-2026-04-24/expert_answer/24.4.2026/second_pass_stock_value_evaluation_2026-04-24.xlsx`

Then proportionally reduce LINE51 stock by `20%` across all sizes.

Reason: human owner manually observed approximate quantities, and a 20% proportional reduction is a reasonable owner-approved haircut while exact physical accuracy is not achievable because of warehouse space constraints.

Business effect: treat LINE51 as 20% lower with timestamped owner-approved lineage. This should not block further business operations.

### Berserk Rush Negative Raw Balances

Decision: same as black T-shirt OOS hold. Treat active sellable stock as `0`.

Reason: returned and cancelled order items are not ingested back into active sellable stock until employee review/QC happens. Returns/cancellations may later explain some zero/OOS decisions, but for now they remain quarantine and should not become active sellable stock.

Business effect: this should not block further business decisions.

## Return And Cancel Quarantine Rule

Owner-confirmed rule: returned and cancelled order items must not be ingested back into active sellable stock until an employee reviews/QCs them. Unprocessed returns/cancellations are quarantine inventory, not sellable inventory.

Operational effect: quarantine can be tracked as possible future stock recovery, but current business decisions should use active sellable stock after owner overrides.

## PO-4.0 / LINE52 Arrived Quantity Truth

Owner answer: confirmed actual arrived quantity is based on the `Actual_qty` column and totals `2367` arrived units for the relevant combined arrived truth.

Read-only workbook check on `2026-05-04` found:

- `Inbounds_sheet` `PO_id=PO-4`, `PO_part_id=PO-4.0`: `Actual_qty=1902`
- `Inbounds_sheet` `PO_id=Line52_PO-9`, `PO_part_id=Line52_PO-9`: `Actual_qty=465`
- Combined: `1902 + 465 = 2367`

Interpretation for next agent: preserve row-level workbook truth and treat `2367` as the owner-confirmed combined arrived basis across PO-4.0 plus LINE52 manual/related arrived stock, not as a reason to collapse the row-level split.

Owner note: there is a difference between actual sent and actual received. The difference is minor, was not discussed with the supplier, and should be noted as an event.

## LINE31 PO1A / Olive Green Preorder

Owner answer: LINE31 PO1A / Olive Green details live in the Sourcing-Research and E-commerce repos and should be ingested into Autonomous Business as planned/inbound PO state, not received/current sellable stock.

Source handoff:

`~/Cowork/Projects/Sourcing-Research/docs/agent_handoffs/LINE31_PO1A_OLIVE_GREEN_PREORDER_AUTONOMOUS_BUSINESS_INGEST_HANDOFF__2026-05-04.md`

Required operational interpretation:

- Preserve the original `450`-set paid PO1A as historical truth.
- Split current operations into `338` non-Olive near-dispatch sets.
- Split Olive Green into `242` exact-color preorder sets.
- Use provisional `15`-day preparation timing.
- Do not mark anything as received/current sellable stock without DB/workbook receipt evidence.
- Append/update inbound workbook only after PO1A and Olive Green preorder details are confirmed according to workbook safety rules.

## Supplier / Cargo Obligations

Owner answer: the `base_payment_SHR_log` sheet in the canonical inbound workbook has been updated with current base payment state: total to pay, amount paid, and remaining amount due.

Canonical workbook:

`~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`

Next agent requirement: read this sheet as the current owner-updated source, but do not publish cashflow green until supplier/cargo obligations are represented in DB/source pointers with amounts, paid/deferred state, due dates, and evidence paths.

## Ads Scope Clarification

Owner answer:

- Meta/Facebook to Kaspi funnel ads drove traffic only to the `ACMEWEAR` Kaspi store and may do so in the future.
- `STOREB` is not involved in Meta/Facebook funnel ads.
- `STOREB` is involved only in internal Kaspi Marketing for generic LINE52 product offers.
- Generic LINE52 offers are not exclusive/owned-brand offers; multiple sellers can sell under those offers.

Next agent implication:

- Meta/Facebook source scope should be ACMEWEAR funnel evidence.
- STOREB ads source scope should be Kaspi internal marketing for generic LINE52 offers.
- Do not require STOREB Meta/Facebook evidence unless the owner later changes scope.

## Order Entry And Cashflow Blockers Still Need Plain-English Review

Owner cannot yet approve order-entry/cashflow recovery until the blockers are explained in plain English. See:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/BLOCKER_PLAIN_ENGLISH_EXPLANATION_20260504.md`
