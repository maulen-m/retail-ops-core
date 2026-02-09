# Dim SKU Light Weight Sync (Single Truth) — 2026-02-09

## Purpose
Restore and protect `dim_sku.weight_kg` from helper-row contamination in workbook-derived sync flows.

## Canonical Source
- Workbook: `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inventory/Dim sku light v5.xlsx`
- Sheet: `DIM_SKU_light_v5`
- Canonical parser: `core/excel/dim_sku_light_parser.py`

## Root Cause
- `sync_po_parts_from_inbound_calendar.py` previously used a last-row-wins map on duplicate `SKU_key` values from embedded `DIM_SKU_light_v5`.
- Helper rows with micro values (for example `CNY=0.19`, `Wt=0.07`) appeared after canonical rows and overwrote `dim_sku.weight_kg`.
- This suppressed the delivery term in landed COGS and distorted PO/cashflow/business-insides outputs.

## Guardrails
- Explicit restore script:
  - `scripts/sync_dim_sku_from_dim_sku_light.py`
- Dry-run default; apply requires:
  - `ENABLE_DIM_SKU_SYNC_WRITE=1`
  - `--apply`
- Default update scope:
  - `weight_kg` only
- Base cost behavior:
  - reference-only by default
  - update only with `--update-base-cost`
- Inbound PO sync:
  - `scripts/sync_po_parts_from_inbound_calendar.py` does not overwrite existing `dim_sku.weight_kg` unless explicit CLI flag is set.

## Standard Run
```bash
python3 scripts/sync_dim_sku_from_dim_sku_light.py \
  --xlsx "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inventory/Dim sku light v5.xlsx"

ENABLE_DIM_SKU_SYNC_WRITE=1 python3 scripts/sync_dim_sku_from_dim_sku_light.py \
  --xlsx "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inventory/Dim sku light v5.xlsx" \
  --apply
```

## Validation
```bash
python3 scripts/validate_dim_sku_light_alignment.py \
  --xlsx "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inventory/Dim sku light v5.xlsx"

python3 scripts/validate_cogs_integrity.py
python3 scripts/validate_params.py --strict
```

Validation contract:
- Weight mismatches vs workbook: hard fail.
- Base-cost drift vs workbook: warning by default (reference signal).

## Recompute Outputs After Restore
```bash
python3 scripts/generate_po_dashboard_data.py
python3 scripts/update_cashflow_dashboard.py
python3 scripts/generate_business_insides.py --as-of 2026-02-08 --strict-cogs
```

## Rollback
1. Restore DB backup created before apply.
2. Re-run:
```bash
python3 scripts/validate_dim_sku_light_alignment.py \
  --xlsx "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inventory/Dim sku light v5.xlsx"
python3 scripts/validate_params.py --strict
```

