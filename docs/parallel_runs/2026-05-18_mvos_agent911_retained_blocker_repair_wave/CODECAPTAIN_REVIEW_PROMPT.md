# CodeCaptain Review Prompt - MVOS Agent911 Retained-Blocker Board Proof

Please review the attached Autonomous_business Agent911 retained-blocker repair wave.

## Requested Decision

We need an independent decision on the next safest and fastest route after Agent9115 closed:

`YELLOW_RETAINED_BLOCKER_BOARD_PROOF`

Do not treat this as a green proof unless the attached evidence truly supports it.

## What Improved

Agent9115 copied-temp synthesis made these lanes green on the copied DB:

- order-entry freshness now passes after Agent905 `164` accepted rows plus Agent911A `15` STOREB identity-bearing API rows;
- day-complete passes;
- COGS completeness passes with Agent873 copied-temp unit evidence;
- exception queue validator passes while retaining visible exceptions;
- cashflow invariants pass;
- order-cashflow coverage passes;
- ads offer-universe coverage passes;
- ads spend reality passes;
- Agent911D `To_pay_BASE_KZT (live)` and `To_pay_DLV_KZT (live)` parser/schema correction is active and focused tests pass.

## What Still Blocks Green

Required validators still fail:

- `src_ab_db_operational_truth` remains `BLOCKED`;
- policy gates `ads_source_truth`, `source_freshness`, and `stock_source_truth` remain blocked;
- PO dashboard still fails because stock snapshot is stale: `2026-05-04` vs cutoff `2026-05-17`;
- PO money gate still fails `inbound_sheet_consistency`, `single_truth_system`, `cogs_integrity`, and `single_truth_alignment`;
- sync dry-run still fails on an existing `DIM_SKU_light` header parser issue;
- single-truth validator still fails retained DB/workbook part-history, PO-4.0 totals, and base-payment mismatches.

## Owner Truth To Preserve

Please preserve these owner-confirmed facts:

- PO-4.0 Line61 ordered/cargo `115`, actual received `92`, shortage `23` is real business truth;
- known Line61 shortages are XL `7`, 2XL `5`, 3XL `6`, 4XL `5`;
- no fresher stock source exists yet;
- the `15` STOREB rows now have identity-bearing API evidence for copied-temp proof, but no production apply is authorized by this packet.

## Questions For CodeCaptain

1. Should we authorize a new copied-temp AB operational source refresh packet for:
   - `fact_inventory_snapshot_size`;
   - `stock_ledger`;
   - `sales_fact_v2`;
   - `order_status_event`;
   - `ads_source_refresh_runs`;
   - `ads_campaign_product_daily`?

2. Or should the C3 source contract be split/changed so `src_ab_db_operational_truth` no longer blocks publication as one monolithic source when only specific operational tables are stale?

3. Should the PO money gate add a narrow accepted-shortage classification for the exact PO-4.0 Line61 `23` delta while still failing other non-schema PO/COGS/alignment issues?

4. Should we run a separate narrow code lane to repair the `DIM_SKU_light` header parser required by `sync_po_parts_from_inbound_calendar.py` dry-run?

5. What is the most efficient next implementation sequence that preserves fail-closed truth and avoids fake green?

## Requested Output

Please return:

- gate color: `GREEN`, `YELLOW`, or `RED`;
- accepted facts;
- rejected or unsafe claims;
- minimum next execution plan;
- any exact owner approval phrase required before the next lane;
- whether this packet is sufficient to continue without production writes.

## Boundaries

This packet does not authorize production DB writes, workbook writes, scheduler/LaunchAgent/cron changes, source-pointer writes, Web_automation writes, external writes, Kaspi/API/WebUI writes, ad-platform writes, cash movement, supplier payment, PO commitment, stock changes, price changes, owner publication, production preflight, or production apply.
