# CodeCaptain Review Prompt: Current MVOS Boundary After Phases 4-7

Please review the current Autonomous_business MVOS copied-temp boundary before we continue toward any production-preflight planning.

## Scope

This pack combines the latest non-production lanes:

- Phase 4 PO single-truth local route: evidence-local PO dashboard generation, copied DB validation, and retained physical-stock inventory drift.
- Phase 5 order-entry no-real-entry quarantine route: explicit copied-temp retention for Universal `922898360` and `923528055` with zero synthetic order-entry inserts.
- Phase 6 board tightening: `B005_workbook_content_lag` relabeled as copied-temp closed / stop for production after Agent8/Agent12 workbook-anchor proof.
- Phase 7 offer-linkage optional narrowing: `fact_offer_stock_mapper_current` materialized on a copied DB only, converting optional `offer_linkage` from missing-table failure into exact retained defects.

This request does not authorize production DB writes, workbook writes, scheduler/LaunchAgent/cron changes, source-pointer writes, Web_automation writes, Kaspi/API/WebUI writes, external writes, ad-platform writes, ad spend, stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, or production apply.

## Owner Truth To Preserve

- Owner-confirmed Universal offer identity is authoritative for copied-temp proof planning only:
  - offer `132822924_328581041`
  - product id `MTE3MDQ5MjU1`
  - decoded product code `117049255`
  - name `Леггинсы PRO COMBAT 2010 белый XL / Леггинсы PRO COMBAT белый`
  - category `Мужское термобелье`
  - SKU family `CL_NEW-CLO_MEN_LEG_WHITE`
  - price seen `1500 KZT`
  - warehouse `30000001_PP1`
- Owner confirmed no fresher physical stock data exists than the last physical stock source already used.
- Merchant Cabinet / offer availability must not be retold as physical stock truth.

## Current Board Summary

Copied-temp closed / stop for production:

- `B001c_child_source_order_entry`
- `B004_universal_storeb_order_entry_identity`
- `B005_workbook_content_lag`
- `B006_single_truth_system`

Still retained stoplines:

- physical-stock source truth and stock snapshot staleness;
- C3 source freshness and policy gates;
- current-window status-ledger continuity through `2026-05-18`;
- STOREB ads retained spend/current-source mapping and ACMEWEAR LINE31 Starry Black coverage;
- single-truth alignment physical-stock inventory cost drift;
- PO money gate required failure via `single_truth_alignment`;
- optional offer-linkage strict defects if CodeCaptain requires strict offer-linkage before preflight;
- high-stock exceptions, dirty repo production readiness, paused automation, and May 21 drift-pack criticality.

## Exact Phase 7 Offer-Linkage Result

`build_offer_stock_mapper.py` on the Agent16 copied DB only:

- rows total: `2640`
- resolved rows accepted by `validate_offer_linkage.py`: `2462`
- unresolved rows: `91`
- ambiguous rows: `87`
- missing bidirectional rows: `4`

`validate_po_money_gate.py --json` after mapper materialization still returns:

- `ok=false`
- required failed: `single_truth_alignment`
- optional failed: `offer_linkage`

So PO money remains `STOP`. Phase 7 narrowed an optional failure; it did not clear the required physical-stock drift.

## Questions

1. Is the Phase 4 evidence-local PO single-truth route acceptable as copied-temp closure for `B006_single_truth_system` while keeping `B007_single_truth_alignment` and `B008_po_money_gate` blocked by physical-stock inventory drift?
2. Is `ORDER_ENTRY_NO_REAL_ENTRY_QUARANTINE_COPIED_TEMP_V1` acceptable as copied-temp closure for `B001c` and `B004`, given that it inserts zero rows and keeps the two Universal no-real-entry rows visible?
3. Is the Phase 6 board tightening correct: `B005_workbook_content_lag` copied-temp closed / stop for production, not broad production green?
4. Is the Phase 7 offer-linkage treatment correct: optional `offer_linkage` is now exact retained defects, while PO money remains stopped by required `single_truth_alignment`?
5. Are the current retained blockers classified correctly in `CURRENT_BLOCKER_BOARD.tsv`?
6. What is the safest next phase after this review: substitute stock/capital-risk contract review, status-ledger current-window route, ads retained-spend route, strict offer-linkage repair, or clean repo/packaging route?
7. Should any added contract field, validator, or test be required before any later production-preflight conversation?

## Expected Answer

Please give:

- gate color: `GREEN`, `YELLOW`, or `RED` for this copied-temp boundary;
- exact blockers that must remain stoplines;
- exact autonomous next steps allowed before production preflight;
- whether strict offer-linkage repair should be done before or after the physical-stock/single-truth alignment decision;
- any required owner approval phrase only if a new authority boundary is needed.
