# CodeCaptain Review Prompt: Phase 25 Current Boundary Refresh

Please review this Autonomous_business MVOS current-boundary packet after Phase
23 and Phase 24.

## What Changed Since The Previous Pack

- Phase 23 aligned current authority pointers so active `docs/current/*` routing
  points to the latest current-boundary review surface instead of stale
  Phase18/19 paths.
- Phase 24 refreshed the C3/source-freshness blocker on a copied DB only.
  Strict current-as-of validation for `2026-05-22` remains `YELLOW/STOP`, with
  exact missing source rows and blocked policy gates now visible.

## Requested Review

1. Confirm whether the current boundary should remain `YELLOW`, not green.
2. Confirm whether Phase 24 correctly keeps C3/source freshness blocked because
   `validate_policy_source_freshness.py --as-of 2026-05-22 --strict --json`
   fails on the copied DB with missing requested-as-of rows for:
   `src_ab_db_operational_truth`, `src_bank_manual_ingest`,
   `src_ecommerce_po_artifacts`, `src_facebook_ads_external_ads`,
   `src_inbound_workbook`, `src_payment_evidence_root`,
   `src_sourcing_research_supplier_routes`, and
   `src_web_automation_kaspi_marketing_directapi`.
3. Confirm whether the six blocked C3 policy gates are correctly retained:
   `ads_source_truth`, `cashflow_source_truth`, `exception_queue`,
   `po_source_truth`, `source_freshness`, and `stock_source_truth`.
4. Confirm that older May4/May18 source-freshness bridge rows must not be
   reused as `2026-05-22` current source freshness.
5. Confirm whether the current next route should be accepted current-as-of
   source acquisition/materialization on copied DB only, or whether any source
   rows should remain retained for review rather than repaired locally.

## Owner Facts To Preserve

- Universal offer `132822924_328581041`, product id `MTE3MDQ5MjU1`, decoded
  product code `117049255`, name `Леггинсы PRO COMBAT 2010 белый XL /
  Леггинсы PRO COMBAT белый`, category `Мужское термобелье`, SKU family
  `CL_NEW-CLO_MEN_LEG_WHITE`, price seen `1500 KZT`, warehouse
  `30000001_PP1`, is authoritative for copied-temp proof planning only.
- No fresher physical stock data exists than the last physical stock source
  already used.

## Boundary

This packet is non-production and review-only. It does not authorize production
DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron
changes, Web_automation writes, Kaspi/API/WebUI mutations, external writes,
ad-platform writes, ad spend, stock changes, price changes, cash movement,
supplier payment, PO commitment, owner publication, production preflight, or
production apply.

## Expected Stopline

If the Phase 24 diagnosis is correct, please call this boundary `YELLOW`: the
review pack is cleaner, but current-as-of source freshness and policy gates
still block owner publication and production-preflight discussion.
