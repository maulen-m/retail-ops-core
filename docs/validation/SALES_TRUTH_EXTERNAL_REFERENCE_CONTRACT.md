# Sales Truth External Reference Contract

## Purpose
Define a fail-closed parity contract between published sales truth (`view_sales_line_truth` / `view_sales_daily_truth`) and external Kaspi ArchiveOrders reference exports.

## Reference Scope
- Input source:
  - `AB_KASPI_ETL_ARCHIVE_DIR` (raw ArchiveOrders XLSX directory), or
  - `AB_KASPI_ETL_REFERENCE_DIR` (sanitized CSV reference set).
- Delivered predicate:
  - Include rows where `Статус == "Выдан"` (or normalized aliases `DELIVERED`, `COMPLETED`).
- Sale date:
  - `Дата изменения статуса`.
- Positive sales:
  - Exclude cancelled/returned statuses from delivered positive sales.
- Day completeness:
  - By default, the parity validator excludes `as_of` day (treats it as potentially incomplete).

## Normalized Keys
- `sale_date`
- `store_code`
- `order_id`
- `quantity`
- `gross_rev_kzt`

## Strict Parity Rules
`scripts/validate_sales_truth_external_reference.py --strict` must enforce:
- Daily aggregate parity per `sale_date + store_code`:
  - `units_delivered` exact
  - `gross_rev_kzt` exact (tolerance: `±1 KZT`)
  - `orders_delivered` exact
- Order set parity per `sale_date + store_code`:
  - `missing_in_db = ref_ids - db_ids` must be empty
  - `extra_in_db = db_ids - ref_ids` must be empty

Any mismatch is a hard failure (non-zero exit).

## Integration
- `system_doctor --strict` runs this gate in governance layer with `--strict-if-configured`.
- `run_h5_proving_day.py` inherits this through `system_doctor`.
- A proving day cannot be green if this parity gate is red.

## Canonical Truth Policy
- External reference is an oracle for validation and repair.
- Canonical truth remains DB-backed published views:
  - `view_sales_line_truth`
  - `view_sales_daily_truth`
- Downstream reports (including `BUSINESS_INSIDES`) must consume canonical views, not direct external overlays.
