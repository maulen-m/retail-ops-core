# Plan: FX 75/520 + PO Part Reconciliation (2026-02-07)

## Objective
1. Reconcile canonical FX defaults and docs to:
   - `CNY/KZT = 75`
   - `USD/KZT = 520`
2. Reconcile inbound split-shipment workbook truth into DB with `po_part_id` as first-class key.

## Scope
- In scope:
  - FX defaults/docs/runtime fallback paths
  - `po_part` schema + `po_line.po_part_id`
  - Workbook sync from `Inbound_calendar_V10.002.xlsx`
  - ARC SKU target price propagation from `DIM_SKU_light_v5.AvgPrc`
- Out of scope:
  - Pricelist sync
  - Unrelated unstaged changes

## Tests-First Contract
- `tests/test_business_params.py` default FX assertions
- `tests/test_fx_defaults_runtime_paths.py`
- `tests/test_po_part_schema_migration.py`
- `tests/test_sync_po_parts_from_inbound_calendar.py`

## Write Gates
- Schema migration apply requires:
  - `ENABLE_SCHEMA_WRITE=1` + `--apply`
- Workbook sync apply requires:
  - `ENABLE_PO_PART_SYNC_WRITE=1` + `--apply`

## Acceptance
- All new tests fail first and pass after implementation.
- `po_part` exists and `po_line.po_part_id` populated for imported rows.
- `PO-4.3`, `PO-6`, and `PO_ARC-1` can be represented through workbook sync.
- ARC rows receive `dim_sku.avg_sell_price_kzt_used` from `AvgPrc`.
- Full gate chain green and evidenced in `.claude/SESSION_LOG.md`.
