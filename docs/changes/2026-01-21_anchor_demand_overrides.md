# Anchor + Demand Override Updates (2026-01-21)

## Summary
Focused changes to stabilize size-share inputs and demand overrides for PO-5 readiness.

## What changed
- **Size share anchors**
  - Imported anchor shares into `dim_anchor` from:
    `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/PO-5_19.1.26/Final/real PO-5/po5_size_share_anchors_from_dim_anchor copy.xlsx`
  - Import script: `scripts/import_size_share_anchors.py` (dry-run default; apply with `ENABLE_PARAM_WRITE=1`).
  - DB backup before import:
    `~/Docs/Oracle/Autonomous_business/2026-01-21/po5_anchor_refresh/app_2026-01-21_162902.db.gz`

- **Anchor-only sizing (temporary)**
  - Anchor size share weight set to **1.0** to ignore sales-derived size shares until verified.
  - Size-share sales data source moved to `sales_fact_v2` (newer, consistent table).

- **Demand overrides**
  - `CL_OC_MEN_LINE52_BLACK`:
    - 2026-01-01 → 2026-03-01: **D=30**
    - 2026-03-01 → 2026-06-01: **D=30**
  - `CL_NEW-CLO2_MEN_SUIT-61_BLACK`: **D=20** (2026-01-01 → 2026-03-01)
  - `CL_NEW-CLO_MEN_BERSERK-RUSH_WHITE`: **D=0.4** (2026-01-20 → 9999-12-31)

## Commands run
```
ENABLE_PARAM_WRITE=1 python3 scripts/import_size_share_anchors.py \
  --excel "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/PO-5_19.1.26/Final/real PO-5/po5_size_share_anchors_from_dim_anchor copy.xlsx" \
  --sheet "dim_anchor" --apply

python3 scripts/upsert_demand_overrides.py --seed-defaults
python3 scripts/update_po_dashboard.py
```

## Outputs refreshed
- `exports/po_dashboard_data.json`
- `exports/po_dashboard.html`
- `exports/po_supplier_export_2026-01-20.csv`
- `exports/po_supplier_summary_2026-01-20.md`
- `exports/demand_diagnostics.csv`
- `exports/stock_rebuild_diagnostics.csv`

## Related commits
- `0859eef` — anchor-only size shares + anchor import script + sales_fact_v2 sizing source
- `03aa74c` — update LINE52 + SUIT-61 demand overrides
- `96d738e` — berserk rush white demand override

