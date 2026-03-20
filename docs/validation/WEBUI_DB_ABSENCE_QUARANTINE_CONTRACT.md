# WEBUI_DB_ABSENCE_QUARANTINE_CONTRACT

## Purpose
Define the fail-closed quarantine path for residual WebUI-vs-DB orders that are fully explained but not safely materializable into DB sales truth during the current migration window.

## Allowed Residual Buckets
- `DB_QUARANTINE_NO_FACT_ORDER_ENTRIES`
- `DB_ONLY_NO_WEBUI_LINEAGE`

Under the separate chronology authority contract, the following comparison classifier is diagnostic-only and must not block the DB coverage gate:
- `DATE_MISMATCH` when `shipped_day_authority_decision.json` is `CRM_REMAINS_CHRONOLOGY_AUTHORITY`

These residuals may remain only when they are emitted by the current read-only classification flow and recorded in a documented quarantine candidate file.

## Required Preconditions
- The frozen WebUI full-parse source is still the active baseline.
- `fact_orders_kaspi` contains the order for `DB_QUARANTINE_NO_FACT_ORDER_ENTRIES`.
- The order cannot be safely materialized through the existing `fact_order_entries_kaspi -> sales_fact_v2` rebuild path.
- The residual is listed in `db_quarantine_candidates.csv` with a concrete explanation.

## Validator Behavior
- Quarantined orders are treated as documented quarantine, not unexplained DB misses.
- When `CRM_REMAINS_CHRONOLOGY_AUTHORITY` is active, exact WebUI-vs-DB date mismatches remain reportable evidence but do not count as hard DB coverage failures.
- Quarantine does not permit raw WebUI publication.
- Quarantine does not bypass workbook chronology authority or any owner publication gates.

## Fail-Closed Rules
- Any residual outside the allowed buckets remains a hard failure.
- `DATE_MISMATCH` remains a hard failure unless the shipped-day authority decision is explicitly `CRM_REMAINS_CHRONOLOGY_AUTHORITY`.
- Quarantine must be explicit, file-backed, and reviewable.
- If the underlying entry/identity issue is later fixed, the order must leave quarantine and pass the normal DB validator path.

## Rationale
The current migration can safely backfill entry-backed orders into `sales_fact_v2`, but some residuals still lack the line-item evidence needed for a defensible DB sales record. Those orders stay in documented quarantine until the missing entry lineage is repaired.
