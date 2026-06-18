# AB_OPERATIONAL_TRUTH_TABLE_SPLIT_V1

Status: active for copied-temp proof and focused C3 source-freshness validation.

Created: 2026-05-18

Owner: business_owner

## Purpose

Split the former monolithic `src_ab_db_operational_truth` freshness claim into table-aware child sources, without making stale operational tables publication-safe.

This contract exists because copied-temp proof can now show that some AB operational tables are fresh while others remain stale. The split improves diagnosis only; it does not weaken source freshness, owner-publication, stock, PO, ads, or profit gates.

## Parent Source

`src_ab_db_operational_truth` remains a roll-up observation for board/debug visibility.

Roll-up rules:
- `src_ab_db_operational_truth` is not owner-publication authority.
- `required_for_publication` must be `0`.
- The roll-up may be `BLOCKED` while children are mixed fresh/stale.
- The roll-up must not be used to clear child-source blockers.
- Validators and proof boards must show child source rows when making publication claims.

## Child Sources

| Source id | Tables | Date columns | Required gate | Publication impact |
| --- | --- | --- | --- | --- |
| `src_ab_db_order_entry_truth` | `fact_order_entries_kaspi` | `updated_at` | `stock_source_truth` | Blocks dependent order/stock publication claims when stale, missing, empty, future, unknown, partial, conflict, or error. |
| `src_ab_db_cashflow_truth` | `fact_cashflow_events`, `fact_cashflow_daily` | `event_date`, `date` | `cashflow_source_truth` | Blocks cashflow publication when stale or otherwise blocking. |
| `src_ab_db_stock_truth` | `fact_inventory_snapshot_size`, `stock_ledger` | `snapshot_date`, `event_date` | `stock_source_truth` | Blocks stock, PO-readiness, PO dashboard, inventory, and owner stock publication claims when stale or otherwise blocking. |
| `src_ab_db_sales_truth` | `sales_fact_v2` | `order_date` | `stock_source_truth` | Blocks sales/profit/stock-dependent publication claims when stale or otherwise blocking. |
| `src_ab_db_order_status_truth` | `order_status_event` | `event_ts` | `stock_source_truth` | Blocks lifecycle/status and stock-dependent publication claims when stale or otherwise blocking. |
| `src_ab_db_ads_truth` | `ads_source_refresh_runs`, `ads_campaign_product_daily` | `date_end`, `date` | `ads_source_truth` | Blocks ads/profit publication claims when stale or otherwise blocking. |

All child sources are required for publication.

## Freshness Rules

For each child source:
- Observe only rows with table timestamps less than or equal to the requested as-of cutoff.
- `FRESH` requires every table in the child source to be fresh under its max-age rule.
- `STALE` is blocking.
- `MISSING`, `EMPTY`, `FUTURE`, `UNKNOWN`, `CONFLICT`, `BLOCKED`, `ERROR`, `PARTIAL`, and `NO_AUTH` are blocking.
- `blocks_publication` must be `1` for every blocking child status.
- A child source may not inherit freshness from the parent roll-up.
- A child source may not inherit freshness from a different child source.
- A copied-temp bridge row may clear a child source only if the bridge input names that exact child source and cites an accepted source packet for that child source.

## Roll-Up Publication Rules

Copied-temp proof:
- May show child statuses and retained blockers.
- May show `src_ab_db_operational_truth` as a non-publication roll-up.
- Must preserve stale child rows as retained blockers.

Owner publication:
- Fails if any required child source for the claimed publication surface is stale or otherwise blocking.
- Fails for stock/PO/dashboard/inventory claims while `src_ab_db_stock_truth` is stale or otherwise blocking.
- Fails for ads/profit claims while `src_ab_db_ads_truth` is stale or otherwise blocking.
- Fails for cashflow claims while `src_ab_db_cashflow_truth` is stale or otherwise blocking.
- Does not become safe merely because `src_ab_db_operational_truth` is renamed, narrowed, or marked informational.

## Validator Expectations

The C3 source registry must include the six child source ids listed in this contract.

The source freshness materializer must:
- materialize child `source_freshness_result` rows by observing the child table set;
- store table-level evidence in `evidence_json.table_observations`;
- store `contract_id=AB_OPERATIONAL_TRUTH_TABLE_SPLIT_V1` in child evidence;
- leave stale child sources as blocking rows.

Policy gate materialization must:
- include child source ids in the dependent gate evidence;
- keep `stock_source_truth` blocked while stock, sales, order-entry, or order-status child sources are stale;
- keep `ads_source_truth` blocked while AB-local ads child source or accepted external ads source rows are stale;
- keep `cashflow_source_truth` blocked while cashflow child source or accepted cash/payment source rows are stale.

## Non-Authorization

This contract does not authorize production DB writes, workbook writes, scheduler changes, source-pointer writes, Web_automation writes, Kaspi/API/WebUI writes, external writes, stock changes, PO commitment, supplier payment, cash movement, price changes, owner publication, production preflight, production apply, or hiding retained blockers.

## Agent9125 Use

Agent9125 may use this split contract in a copied-temp rerun after Agent912 root closeouts are reviewed.

Before source freshness materialization, Agent9125 must promote/refresh the C3 policy registry on the copied DB so the six child `policy_source_registry` rows exist in the copied database. This is copied-temp only and does not authorize production registry writes.

Agent9125 must still fail closed if any child source required for the claimed publication surface is stale or otherwise blocking.
