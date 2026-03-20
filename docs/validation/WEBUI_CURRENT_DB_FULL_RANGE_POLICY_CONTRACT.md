# WebUI Current DB Full-Range Policy Contract

## Purpose

Define how `validate_webui_archive_vs_current_db.py` behaves for full-range owner-truth proving, where the objective is to protect current publication truth without forcing historical cleanup to block the live path.

## Modes

### `window_strict`

- Intended for narrow validation windows such as Jan-Feb promotion checks.
- Missing WebUI orders in DB are hard failures.
- DB-only orders are hard failures.
- Chronology deltas are hard failures unless another contract explicitly removes them.

### `full_range_owner_truth`

- Intended for owner-truth live proving across the broader mapped sales range.
- Historical drift is still measured, but only post-cutover hard absences remain blocking.
- Diagnostic buckets remain visible in the report and must not be hidden.

## Hard-stop vs diagnostic policy

### Hard-stop in `full_range_owner_truth`

- post-cutover WebUI orders that are truly missing in the current DB surface
- any missing order not covered by an explicit diagnostic bucket below

### Diagnostic only in `full_range_owner_truth`

- missing WebUI orders with `sale_date < statusdate_cutover`
- missing WebUI orders that have:
  - workbook-anchor lineage
  - returned/current-state lineage in `sales_fact_v2`
- DB-only rows
- chronology deltas when chronology authority remains workbook/CRM
- prewindow/postwindow drift

## Statusdate cutover

- current cutover: `2026-02-27`
- reason: orders on or after this boundary are treated as live operational truth and must not disappear from the DB-backed publication surface

## Report contract

`validate_webui_archive_vs_current_db.py` must emit, at minimum:

- `range_policy`
- `statusdate_cutover`
- `original_missing_in_db_orders`
- `missing_in_db_orders`
- `post_cutover_hard_missing_orders`
- `historical_diagnostic_missing_orders`
- `current_state_surface_mismatch_orders`
- `diagnostic_db_only_orders`

## Non-negotiables

- no tolerance widening
- no quarantine of post-cutover hard-missing orders by default
- no masking of diagnostic buckets as PASS without reporting them
- any new hard-stop/diagnostic bucket requires a contract update before validator logic changes
