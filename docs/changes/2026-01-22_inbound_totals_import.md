# Inbound Totals Import (2026-01-22)

## Summary
Imported inbound totals for PO‑5, PO‑4.1, and PO‑4.2 from the consolidated Excel sheet, and updated SUIT‑61 average sell price in the DB source of truth.

## Source file
`~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/PO-5_19.1.26/Final/real PO-5/fixed line61/Approved_qnt/Inbound_total_21.1.2026.xlsx`

Sheet: `size_level`

## What changed
- **Inbound import**
  - Upserted `po_header` for PO‑5 / PO‑4.1 / PO‑4.2.
  - Upserted size-level `po_line` rows (order_qty from `Order Qty_Approved`).
  - Activated/created missing `dim_sku` + `dim_sku_size` entries as needed.
  - Status auto-set based on dates: `message_date` → `SENT`, `cargo_send_date` → `SHIPPED_CARGO`.

- **Price update**
  - `CL_NEW-CLO2_MEN_SUIT-61_BLACK` set to `avg_sell_price_kzt_used = 12990`
  - `avg_sell_price_source = MANUAL_OVERRIDE`

## Commands run
```
python3 scripts/backup_db.py --dest ~/Docs/Oracle/Autonomous_business/2026-01-21/inbound_totals --no-cleanup
python3 scripts/import_inbound_total_excel.py \
  "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/PO-5_19.1.26/Final/real PO-5/fixed line61/Approved_qnt/Inbound_total_21.1.2026.xlsx" \
  --report-md docs/changes/2026-01-21_inbound_total_21.1.2026.md --apply
python3 scripts/update_dim_sku_price.py \
  --sku-key CL_NEW-CLO2_MEN_SUIT-61_BLACK --price-kzt 12990 --source MANUAL_OVERRIDE --apply
```

## Outputs
- Report (ASCII tables + ETA estimates): `docs/changes/2026-01-21_inbound_total_21.1.2026.md`
- DB backup: `~/Docs/Oracle/Autonomous_business/2026-01-21/inbound_totals/app_2026-01-22_002422.db.gz`

