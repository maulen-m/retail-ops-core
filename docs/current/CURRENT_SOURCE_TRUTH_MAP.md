# CURRENT_SOURCE_TRUTH_MAP

Status: ACTIVE_PHASE42_CODECAPTAIN_REVIEW_PACK_REFRESH
Created: 2026-05-21
Last aligned: 2026-05-22 Phase 42 CodeCaptain review pack refresh

This file routes source truth. It does not authorize source-pointer writes, production DB writes, external writes, WebUI/API mutations, ad-platform writes, cash movement, PO commitment, stock changes, price changes, owner publication, production preflight, or production apply.

Current review surface:
`~/Docs/Oracle/Autonomous_business/2026-05-22/062954_TASK-000_mvos-phase42-codecaptain-review-pack-refresh`

## Source Truth Rules

- Do not clear physical stock from Merchant Cabinet offer availability.
- Do not zero missing ads spend.
- Do not claim owner publication from copied-temp source bridges.
- Do not use parent operational truth rollups to clear child source rows.
- Do not promote copied-temp proof to production truth.
- Do not promote scoped proof to full-scope proof.
- Do not infer source freshness from old plans or mutable `.claude/*` logs.
- Use `docs/contracts/mvos_source_contracts/PHASE20_OWNER_FACTS_RETAINED_BLOCKER_ADDENDUM_20260522.md`
  to avoid re-asking the owner-confirmed Universal identity and no-fresher-physical-stock facts.

## Current Source Routes

| source_id | domain | current_status | blocks_publication | next_route |
| --- | --- | --- | --- | --- |
| `src_ab_db_ads_truth` | Ads internal child source | RETAINED: stale child source plus Phase 3 exact blockers; STOREB May 18 keeps `10` source-backed rows with `3837.32 KZT` retained spend, and ACMEWEAR LINE31 Starry Black lacks exact ads packet or zero-spend/no-campaign proof | yes | Acquire exact current ads related-product evidence or zero-spend/no-campaign evidence; retain visible spend and never zero missing spend. |
| `src_ab_db_cashflow_truth` | Cashflow internal child source | COPIED-TEMP PARTIAL CLOSED / STOP FOR PUBLICATION: Phase28 copied DB extends `fact_cashflow_daily` to `2026-05-22`; Phase33 proves manual-bank source route can clear separately; Phase34 applies `3680` copied-temp modeled cashflow events and advances `fact_cashflow_events` from `2026-05-04` to `2026-05-21`, but C3 still marks the event table `TABLE_STALE` for requested as-of `2026-05-22`, so this child source remains `STALE` and cashflow/source-freshness gates still block owner publication | yes | Ask CodeCaptain whether a no-eligible-event-day proof can satisfy `src_ab_db_cashflow_truth` when daily reaches `2026-05-22`, events reach `2026-05-21`, and strict coverage/invariants pass; do not insert fake zero events. |
| `src_ab_db_order_entry_truth` | Order-entry internal child source | COPIED-TEMP CLOSED / STOP FOR PRODUCTION: strict recovery passes with `ORDER_ENTRY_NO_REAL_ENTRY_QUARANTINE_COPIED_TEMP_V1`; Universal `922898360` and `923528055` remain retained no-real-entry quarantine rows with `0` synthetic entries inserted | yes | Package copied-temp no-real-entry quarantine contract for CodeCaptain; do not invent entries or production-apply. |
| `src_ab_db_order_status_truth` | Order status/lifecycle source | RETAINED: Phase35 confirms the scoped local `STOREB` / `ACMEWEAR` / `UNIVERSAL` status ledger passes `2026-05-05..2026-05-17`, but fails `2026-05-05..2026-05-18` with one-day gaps for all three scoped stores; default five-store route fails with `gap_count=5` and `pack_window_provenance_error_count=80`; day-complete rows `844362551` and `861137901` close in copied-temp proof only | yes | Acquire exact same-window status ledger source through `2026-05-18` or request scoped/dated status-ledger contract review; do not production-apply day-complete patch. |
| `src_ab_db_sales_truth` | Sales internal child source | COPIED-TEMP CLOSED / STOP FOR PRODUCTION: Phase 2 owner-confirmed Universal offer `132822924_328581041` to `CL_NEW-CLO_MEN_LEG_WHITE_XL`; strict copied-temp `sales_fact_v2` rebuild passes with `errors_count=0`, but production/source gates remain blocked | yes | Package copied-temp Universal identity decision for CodeCaptain; do not production-apply before retained source/workbook blockers and review clear. |
| `src_ab_db_stock_truth` | Physical stock source | STALE, max observed 2026-05-04; owner confirms no fresher physical stock source currently exists | yes | Keep stock/PO/publication blocked unless a fresh physical stock source appears or CodeCaptain accepts a substitute stock/capital-risk contract. |
| `src_ab_db_operational_truth` | Parent operational rollup | COPIED-TEMP CURRENT-AS-OF BLOCKED: Phase27 copied DB materialized a `2026-05-22` row, but all `9` observed operational tables are stale and the current DB registry still treats this source as publication-blocking | yes in current validator | Keep as retained blocker; if the parent rollup is intended to be debug-only, review registry/source-map alignment with CodeCaptain instead of silently overriding validator truth. |
| `src_web_automation_kaspi_marketing_directapi` | Kaspi Marketing DirectAPI | RETAINED CURRENT-AS-OF BLOCKED: Phase31 found exactly `1` local packet candidate and `0` accepted current candidates; Phase32 prepared a read-only acquisition starter but did not fetch because the Web_automation output boundary needs exact approval or CodeCaptain clearance | yes for current owner publication | After exact Phase32 approval or CodeCaptain clearance, acquire/build an accepted Kaspi Marketing DirectAPI source packet through `2026-05-22`; do not reuse the May4 packet or run Web_automation writes under the current stopline. |
| `src_facebook_ads_external_ads` | Meta/Facebook ads | RETAINED CURRENT-AS-OF STALE: Phase31 audited `7` local Meta candidates and found `0` accepted current candidates; Phase32 prepared a Meta acquisition starter but did not fetch because new Business_3/Facebook_ads run writes are not explicitly opened in the active envelope | yes for current owner publication | After exact Phase32 approval or CodeCaptain clearance, acquire/materialize an accepted current-as-of Meta source packet; keep May19/20 readonly summaries evidence-only and make no ad-platform writes. |
| `src_ecommerce_po_artifacts` | E-commerce PO artifacts | COPIED-TEMP CURRENT-AS-OF FRESH / STOP FOR PRODUCTION: Phase29 source-filtered hinted scan materialized `2026-05-22` copied DB row, max observed `2026-05-18T13:11:57+05:00`, row_count `2256`, `blocks_publication=0` | no for copied-temp proof | Keep as copied-temp closure evidence; no production/source-pointer action without review. |
| `src_sourcing_research_supplier_routes` | Sourcing Research supplier routes | COPIED-TEMP CURRENT-AS-OF FRESH / STOP FOR PRODUCTION: Phase29 source-filtered hinted scan materialized `2026-05-22` copied DB row, max observed `2026-05-21T12:47:12+05:00`, row_count `82741`, `blocks_publication=0` | no for copied-temp proof | Keep as copied-temp closure evidence; no production/source-pointer action without review. |
| `src_bank_manual_ingest` | Bank/manual cash | PRODUCTION CONFIG UPDATED FROM OWNER-CURRENT WORKBOOK: `Cash_Balances` in `Inbound_calendar_V10.002.xlsx` is accepted as the current manual-bank route for this launch lane; `config/bank_accounts.yaml` now points to `2026-06-01 09:06:51 GMT+5`; SHR payment log includes owner-confirmed PO-5 #18 `7,000 CNY` paid on `2026-05-30 21:00:00` even while the final exchanger receipt image remains pending. | no for LINE31 launch cash freshness after 2026-06-01 sync | Preserve workbook-as-source evidence, keep CNY payable primary, and keep the owner-protected reserve minimum at `800,000 KZT`; do not treat the old `1,500,000 KZT` reserve assumption as current. |
| `src_payment_evidence_root` | Payment evidence | COPIED-TEMP CURRENT-AS-OF FRESH / STOP FOR PRODUCTION: Phase27 copied DB materialized a `2026-05-22` row, max observed `2026-05-20`, `blocks_publication=0` | no for copied-temp proof | Keep payment evidence freshness visible, but do not claim full cashflow publication green while bank/manual cash remains stale. |
| `src_inbound_workbook` | Inbound/PO workbook | COPIED-TEMP CURRENT-AS-OF FRESH / STOP FOR PRODUCTION: Phase27 copied DB materialized a `2026-05-22` row, max observed `2026-05-16`, `blocks_publication=0`; copied DB `po_source_truth` gate passes | no for copied-temp proof | Use copied-temp shortage/source evidence for review; do not claim PO money/current publication green while physical-stock drift remains retained. |
| `merchant_cabinet_offer_availability` | Offer availability | Parsed evidence, not physical stock | no | Use only for offer availability proof; cannot clear stock freshness. |
| `order_entry_non_api_local_evidence` | Local non-API order evidence | Active copied-temp contract with quarantine | yes for affected outputs | Repair copied-temp coverage only; no production insert. |
| `sales_vs_workbook_anchor` | Workbook content anchor | COPIED-TEMP CLOSED / STOP FOR PRODUCTION: Phase 3 accepted `8353` workbook-anchor rows into `fact_sales_workbook_anchor` on a copied DB and `validate_sales_vs_workbook_anchor.py` passed for `2026-05-18` and `2026-05-22` | yes for workbook-dependent surfaces | Keep copied-temp sidecar closure visible; production route requires CodeCaptain review and later backup-first owner-approved write gate. |
| `single_truth_dashboard` | PO/dashboard single truth | COPIED-TEMP PARTIAL CLOSED / STOP FOR PO MONEY: evidence-local dashboard from the same copied DB makes `validate_single_truth_system` pass under declared scope, but full alignment still fails physical-stock inventory cost drift and Phase24 C3 current-as-of source freshness is missing for PO source rows | yes for PO/publication | Package copied-temp single-truth closure for CodeCaptain; retain physical-stock drift/current-as-of source freshness and do not claim PO money green. |
| `retained_stock_exceptions` | High stock exception queue | 9 retained exceptions visible | yes for affected stock/PO decisions | Keep visible until warehouse/source proof clears them. |
| `source_contract_registry` | Source contract authority | Valid routing source with warnings/strict requirements | yes if strict final gate fails | Tighten/validate before final green. |

## Current Phase Bias

The fastest safe route is not another broad proof wave. It is a bounded blocker-closure wave:

1. Retain physical stock source truth as blocked unless a new stock source/export appears or CodeCaptain accepts a substitute stock/capital-risk contract.
2. Sales/order-entry identity and strict rebuild route.
3. Cashflow freshness route.
4. PO/single-truth alignment route.
5. Ads retained/source truth route if publication or profit-after-ads remains required.
