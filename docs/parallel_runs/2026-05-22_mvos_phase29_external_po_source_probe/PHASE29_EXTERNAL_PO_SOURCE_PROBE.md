# PHASE29_EXTERNAL_PO_SOURCE_PROBE

Status: `YELLOW_SOURCE_FRESHNESS_ERRORS_REDUCED_TO_FOUR`
Created: `2026-05-22`

This probe is copied-temp/evidence-only. It does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, external writes, WebUI/API mutations, ad-platform writes, cash movement, PO commitment, stock or price changes, owner publication, production preflight, or production apply.

## Boundary

- Source DB: Phase28 copied DB.
- Probe DB: `exports/validation/mvos_phase29_external_po_source_probe/20260522_0440/app_phase29_external_po_probe.sqlite`
- Evidence root: `exports/validation/mvos_phase29_external_po_source_probe/20260522_0440`
- Source rows materialized: `src_ecommerce_po_artifacts`, `src_sourcing_research_supplier_routes`.
- Protected production DB SHA stayed `726a6bc45a4811423390e28698a63e39f5d9400057fb2671ca68c255468371b5`.

## Result

The two retained missing external PO source rows are now copied-temp fresh:

| source_id | status | max_observed_at | row_count | blocks_publication |
| --- | --- | --- | ---: | ---: |
| `src_ecommerce_po_artifacts` | `FRESH` | `2026-05-18T13:11:57+05:00` | `2256` | `0` |
| `src_sourcing_research_supplier_routes` | `FRESH` | `2026-05-21T12:47:12+05:00` | `82741` | `0` |

Strict source freshness improved from the Phase27/Phase28 retained six-source error shape to four retained errors:

- `src_ab_db_operational_truth` remains `BLOCKED`.
- `src_bank_manual_ingest` remains `STALE`.
- `src_facebook_ads_external_ads` remains `STALE`.
- `src_web_automation_kaspi_marketing_directapi` remains `BLOCKED`.

Policy gates remain unchanged at four blockers:

- `ads_source_truth`
- `cashflow_source_truth`
- `source_freshness`
- `stock_source_truth`

## Evidence

- `materialize_external_po_sources_dryrun.json`: two source rows dry-run as `FRESH`.
- `materialize_external_po_sources_apply.json`: copied-temp apply inserted/replaced two source rows.
- `external_po_source_rows_after_apply.csv`: applied source rows with evidence JSON.
- `validate_policy_source_freshness_20260522_after_external_po_sources.json`: strict source freshness now has four errors.
- `validate_policy_gate_results_strict_after_external_po_sources.json`: strict policy gates still block four gates.
- `v_source_freshness_current_after_external_po_sources.csv`: current source freshness view after copied-temp apply.
- `v_policy_gate_latest_after_external_po_sources.csv`: current gate view after copied-temp apply.

## Route Decision

This is a real copied-temp closure for the two external PO source rows, but not a business-green result. It should be added to the next CodeCaptain packet as a precise improvement:

- `src_ecommerce_po_artifacts` no longer needs to be listed as missing after Phase29 copied-temp proof.
- `src_sourcing_research_supplier_routes` no longer needs to be listed as missing after Phase29 copied-temp proof.
- The remaining C3 blocker count is now four exact sources plus four policy gates.

No production or source-pointer action should follow from this probe without later review.
