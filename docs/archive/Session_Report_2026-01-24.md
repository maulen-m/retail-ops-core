# Session Report — 2026-01-24

## Summary
- Implemented **Артикул prefix → SKU_key** parsing and added a **Kaspi_name_core fallback** via `Sku_Map_CRM_3.xlsx`.
- Updated ActiveOrders/API parsers and on‑delivery export to use the same SKU mapping logic.
- Added a SKU‑parse sanity check to the full import flow.

## Commands / Scripts Used
- `excel_ui/run_on_delivery_export.command`
  - Runs `scripts/export_on_delivery_with_econ.py` to create raw + economics exports.
- `scripts/export_on_delivery_with_econ.py`
  - Writes `excel_ui/ActiveOrders/on_delivery/*_raw.xlsx` and `*_econ.xlsx`.
- `excel_ui/run_full_import.command`
  - Includes SKU parse sanity check using the updated parsers.

## Key Output (latest run)
- `excel_ui/ActiveOrders/on_delivery/on_delivery_2026-01-24_1344_raw.xlsx`
- `excel_ui/ActiveOrders/on_delivery/on_delivery_2026-01-24_1344_econ.xlsx`

## Notes
- `Sku_Map_CRM_3.xlsx` lookup path:
  - `~/Documents/useful tables/Main crm spreadsheets/main tables/Sku_Map_CRM_3.xlsx`
- Environment override supported:
  - `AB_SKU_MAP_PATH` or `SKU_MAP_CRM_PATH`
