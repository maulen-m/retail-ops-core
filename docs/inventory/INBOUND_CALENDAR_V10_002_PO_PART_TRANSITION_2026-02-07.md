# Inbound Calendar V10.002 -> PO Part Transition (2026-02-07)

## Purpose
Capture split inbound truth from `Inbound_calendar_V10.002.xlsx` into DB tables with deterministic, idempotent writes:
- `po_header` (PO-level aggregate)
- `po_part` (new split-shipment truth)
- `po_line.po_part_id` (line-level linkage)

## Source Workbook
- Path: `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/backup/7.2.26/Inbound_calendar_V10.002.xlsx`
- Required sheets:
  - `Inbounds_sheet`
  - `PO_part_id_Totals`
  - `DIM_SKU_light_v5`

## Column Contract
### `Inbounds_sheet` (required)
- `SKU Key`, `Size`, `message_date`, `Order Qty_Approved`, `PO_id`, `PO_part_id`
- `cargo_send_date`, `Estimated_Arrival_date`, `Actual_Arrival_date`
- `Status`, `base_cost`, `PO Base (CNY)`, `Actual_qty`, `supplier_id`

### `PO_part_id_Totals` (required)
- `PO_part_id`, `PO_id`, `supplier_id`, `message_date`, `cargo_send_date`
- `Estimated_Arrival_date`, `Actual_Arrival_date`, `Status`
- `Total Units`, `Base_cost_CNY`
- `Est. Weight (kg)`, `Total Bags`
- `is_paid_BASE`, `is_paid_DLV`, `To_pay_BASE_KZT`, `To_pay_DLV_KZT`

#### May 2026 Workbook Display Labels

Owner-maintained workbook format edits may add display suffixes to live money
columns without changing their canonical meaning. The parser must read these
headers as the canonical fields:

- `To_pay_BASE_KZT (live)` -> `To_pay_BASE_KZT`
- `To_pay_DLV_KZT (live)` -> `To_pay_DLV_KZT`

If both an exact canonical header and a display-suffixed alias are present for
the same field, validation must fail closed until the duplicate mapping is
resolved. Do not infer or ignore missing payment fields.

### `DIM_SKU_light_v5` (used when present)
- `SKU_key`, `AvgPrc` (stored to `dim_sku.avg_sell_price_kzt_used`)

## Write Safety
- Migration write gate:
  - `ENABLE_SCHEMA_WRITE=1 ... --apply`
- Workbook sync write gate:
  - `ENABLE_PO_PART_SYNC_WRITE=1 ... --apply`
- Default mode is dry-run for both scripts.

## Execution
1. Dry-run schema check:
   - `python3 scripts/migrate_023_po_parts_schema.py`
2. Apply schema migration:
   - `ENABLE_SCHEMA_WRITE=1 python3 scripts/migrate_023_po_parts_schema.py --apply`
3. Dry-run workbook sync:
   - `python3 scripts/sync_po_parts_from_inbound_calendar.py --xlsx "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx"`
4. Apply workbook sync:
   - `ENABLE_PO_PART_SYNC_WRITE=1 python3 scripts/sync_po_parts_from_inbound_calendar.py --xlsx "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx" --apply`

## Idempotency Rules
- Re-running migration is a no-op.
- Re-running workbook sync updates existing `(po_id, po_part_id, sku_key, my_size)` rows, no duplicates.
- `po_part` upserts by `po_part_id`.
- ARC sell prices are refreshed from `DIM_SKU_light_v5.AvgPrc`.
- Payment flags are normalized (`YES/NO/Y/N/TRUE/FALSE/1/0`) and persisted to `po_part`.
- Header-level `weight_nom_kg` and `total_places` are rebuilt from `po_part` aggregates each sync.

## Paid-Capital Notes (v2)
- `is_paid_BASE=YES` marks base cost as paid.
- `is_paid_DLV=YES` marks delivery cost as paid.
- `To_pay_*` columns remain source-of-truth for unpaid obligations.
- Cashflow paid-capital views include only paid portions from `po_part`.

## Status Mapping
- `Transit` -> `IN_TRANSIT`
- `Arrived` -> `RECEIVED`

## Rollback
1. Restore DB from pre-task backup.
2. Re-run:
   - `python3 scripts/validate_params.py --strict`
   - `python3 scripts/validate_po_dashboard_invariants.py`
