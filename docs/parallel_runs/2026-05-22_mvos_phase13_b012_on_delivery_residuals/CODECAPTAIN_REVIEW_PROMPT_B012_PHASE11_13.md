# CodeCaptain Review Prompt: B012 Phase11-13 Current Boundary

Please review the current Autonomous_business B012 copied-temp boundary before we continue toward any default-route, repeated-run, production-preflight, or production-apply conversation.

## Scope

This pack adds the May 22 B012 Phase11-13 evidence on top of the current MVOS retained-blocker board.

It is review-only and non-authorizing. It does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, Kaspi/API/WebUI writes, external writes, ad-platform writes, ad spend, stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, production apply, git commits, staging, resets, or reverts.

## Owner Truth To Preserve

- The owner-confirmed Universal offer identity remains authoritative for copied-temp proof planning only:
  - offer `132822924_328581041`
  - product id `MTE3MDQ5MjU1`
  - decoded product code `117049255`
  - name `Леггинсы PRO COMBAT 2010 белый XL / Леггинсы PRO COMBAT белый`
  - category `Мужское термобелье`
  - SKU family `CL_NEW-CLO_MEN_LEG_WHITE`
  - price seen `1500 KZT`
  - warehouse `30000001_PP1`
- The owner confirmed no fresher physical stock data exists than the last physical stock source already used.
- Merchant Cabinet / offer availability must not be retold as physical stock truth.
- `LINE-31-LS` must not inherit COGS from LINE51 or `LINE-31-TS` unless an explicit owner/source/CodeCaptain-reviewed copied-temp authority exists.

## Current B012 Result

Phase 11:

- Reduced May 21 drift-pack COGS from `CRITICAL` to `WARN` in an evidence-local copied-temp pack.
- `validate_cogs_integrity.py` unresolved rows became `0` using accepted copied-temp unit COGS evidence for `SUIT-31-TS=5567.22 KZT`.
- `validate_drift_pack_slo.py --strict` passed, but the pack stayed `WARN` due to DIM_SKU and on-delivery residual warnings.

Phase 12:

- Fixed the `DIM_SKU_light_v7` parser/schema error by supporting the current one-column markdown pipe-table workbook shape.
- Existing guarded `sync_dim_sku_from_dim_sku_light.py` updated `10` weight rows on a copied DB only.
- `validate_dim_sku_light_alignment.py` passed on copied DB with `weight_mismatches=0`; `base_mismatches=11` remained warning-only.
- Retained: `DIM_SKU_light_v7` self-labels as fallback planning anchor, so source-authority/default-route review remains needed.

Phase 13:

- Reduced `validate_on_delivery_freeze.py` failures from `133` to `1` on copied DB only.
- Sequence used:
  - settlement-only pass: `133 -> 69`;
  - existing order-to-cashflow translator plus post-translation settlement: `69 -> 3`;
  - branch with already-accepted copied-temp parent-unit COGS for `LINE-31-TS`, `SUIT-21-TS`, `SUIT-31-LS`, and `SUIT-31-TS`: `3 -> 1`.
- Final retained row:

| order_id | store | status | kaspi_status | sku_key | sku_id | reason |
| --- | --- | --- | --- | --- | --- | --- |
| `929183530` | `ACMEWEAR` | `SHIPPED` | `KASPI_DELIVERY` | `LINE-31-LS` | `LINE-31-LS_2XL` | `LINE-31-LS` has no accepted copied-temp COGS authority |

## Current Board Decision

`B012_may21_drift_pack_critical` remains `STOP for current daily autonomy`.

The blocker is now narrower:

- copied-temp COGS-critical row is repairable;
- copied-temp DIM_SKU alignment can pass after guarded sync;
- copied-temp on-delivery residuals are narrowed to one retained `LINE-31-LS` row;
- default/repeated-run autonomy is not proven;
- production/final route is not authorized.

## Questions

1. Is Phase 11 acceptable as copied-temp evidence that the original B012 COGS-critical row can be closed without silently relaxing COGS integrity?
2. Is Phase 12 acceptable as copied-temp evidence that the `DIM_SKU_light_v7` parser/alignment subgate is closed, while retaining source-authority review because the workbook self-labels as fallback planning anchor?
3. Is Phase 13 acceptable as copied-temp evidence that on-delivery residuals are narrowed from `133` to `1`, while preserving the final `LINE-31-LS` row as a hard retained blocker?
4. Should `LINE-31-LS` be kept quarantined until explicit COGS authority is provided, or is there an existing source/contract route we should apply in copied-temp only?
5. Is the order-to-cashflow translator plus settlement sequence acceptable as the route to propose for a future reviewed default/repeated-run matrix, or does it need a narrower validator-specific materializer?
6. What exact next autonomous phase should run before any production-preflight conversation: `LINE-31-LS` COGS authority packet, default repeated-run B012 matrix, status-ledger current-window route, ads retained-spend route, dirty repo cleanup grouping, or another bounded lane?
7. Are the retained blockers in `CURRENT_BLOCKER_BOARD.tsv` classified correctly after Phase13?
8. What additional validator, test, contract field, or owner approval phrase is required before B012 can move from `YELLOW` to copied-temp/default-route `GREEN`?

## Expected Answer

Please provide:

- gate color: `GREEN`, `YELLOW`, or `RED` for the B012 Phase11-13 copied-temp boundary;
- exact blockers that must remain visible;
- whether the final `LINE-31-LS` row requires owner truth, source evidence, or CodeCaptain decision;
- whether the DIM_SKU copied-temp route is acceptable despite the fallback-anchor/source-authority nuance;
- whether the order-to-cashflow plus settlement route is acceptable for the next default/repeated-run proof;
- exact next autonomous steps allowed before production preflight;
- any required owner approval phrase only if a new authority boundary is needed.
