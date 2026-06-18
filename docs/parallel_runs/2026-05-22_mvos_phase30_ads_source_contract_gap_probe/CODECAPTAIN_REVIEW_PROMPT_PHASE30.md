# CodeCaptain Review Prompt - Phase30 Ads Source Contract Gap

Please review the current MVOS copied-temp boundary after Phase29 and Phase30.

We have not requested or performed production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, external writes, Web_automation writes, Kaspi/API/WebUI writes, ad-platform writes, ad spend, cash movement, PO commitment, stock changes, price changes, owner publication, production preflight, or production apply.

## What improved

Phase29 copied-temp source-filtered materialization closed the two previously missing external PO source rows:

- `src_ecommerce_po_artifacts`: `FRESH`, max observed `2026-05-18T13:11:57+05:00`, row_count `2256`, blocks_publication `0`.
- `src_sourcing_research_supplier_routes`: `FRESH`, max observed `2026-05-21T12:47:12+05:00`, row_count `82741`, blocks_publication `0`.

## What remains yellow

Phase30 copied-temp ads-source probe retained the ads source gap:

- `src_facebook_ads_external_ads`: `STALE`, max observed `2026-05-04T23:59:59+05:00`, row_count `18`, blocks_publication `1`.
- `src_web_automation_kaspi_marketing_directapi`: `BLOCKED`, max observed `2026-05-04T23:59:59+05:00`, row_count `15`, blocks_publication `1`.

The accepted Kaspi Marketing DirectAPI packet has packet gate `GREEN` for the old boundary, but fails current `2026-05-22` coverage with:

- `DATE_COVERAGE_BEFORE_AS_OF:2026-05-04`
- `DATE_COVERAGE_FLAG_NOT_TRUE:date_coverage_through_2026_05_22`
- `PACKET_AS_OF_MISMATCH:2026-05-04`
- store-level coverage-before-as-of and missing coverage flags for `STOREB` and `ACMEWEAR`

The accepted Meta packet is structurally clean for its old requested dates, but only covers through `2026-05-04`. Local May19/20 readonly Meta summaries exist under `Business_3/Facebook_ads/exports`, but are not accepted Autonomous Business source-freshness packets for `2026-05-22`.

Strict validators still retain:

- Source freshness errors: `src_ab_db_operational_truth`, `src_bank_manual_ingest`, `src_facebook_ads_external_ads`, `src_web_automation_kaspi_marketing_directapi`.
- Policy gate blockers: `ads_source_truth`, `cashflow_source_truth`, `source_freshness`, `stock_source_truth`.

## Review Questions

1. Is Phase29 sufficient to treat `src_ecommerce_po_artifacts` and `src_sourcing_research_supplier_routes` as copied-temp closed for review, with no production/source-pointer authority?
2. Is Phase30 correct to retain `ads_source_truth` as yellow until an accepted current-as-of Meta packet and Kaspi Marketing DirectAPI packet exist?
3. What is the minimum acceptable packet contract to transform the local May19/20 Meta readonly summaries into accepted `src_facebook_ads_external_ads` source-freshness evidence?
4. What is the minimum acceptable packet contract for Kaspi Marketing DirectAPI through `2026-05-22`, especially for `STOREB` via Universal login/switcher and `ACMEWEAR`?
5. Should the next autonomous lane be limited to read-only packet construction plus copied-temp rerun, or is CodeCaptain review required before packet adapter work?
