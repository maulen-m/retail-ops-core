# Sales Ocean Drop Reference Contract

## Purpose
Define a strict, fail-closed contract for validating internal published sales truth against the Ocean Drop external archive mapping.

## Single-Truth Boundary
- Canonical published truth:
  - `view_sales_line_truth`
  - `view_sales_daily_truth`
- External reference is validation-only:
  - Ocean Drop CSV inputs
  - `view_sales_line_reference`
  - `view_sales_daily_reference`
- Reference data must never be unioned into published truth views.

## Reference Input
Required input columns:
- `№ заказа`
- `Статус`
- `Количество`
- `Сумма`
- `Склад передачи КД`
- `Дата поступления заказа`

Optional identity/date helper columns:
- `Дата изменения статуса`
- `Артикул`
- `Название в системе продавца`
- `Название товара в Kaspi Магазине`
- `mapped_sku_key`
- `mapped_size`

## Normalization Rules
- `order_id` = `№ заказа`
- `status_internal` normalization:
  - delivered: `ЗАВЕРШЕН`, `ВЫДАН`, `DELIVERED`, `COMPLETED`
  - returned: `ВОЗВРАЩЕН`, `RETURNED`, `RETURN`, `RETURNING`
  - cancelled: `ОТМЕНЕН`, `CANCELLED`, `CANCELED`
- `sale_date`:
  - primary: `Дата изменения статуса`
  - fallback: `Дата поступления заказа`
- `store_code` from `Склад передачи КД` via strict mapping.
- Positive sales parity set:
  - include `status_internal=DELIVERED` and `return_flag=0`

## Strict Validation Gate
Command:
```bash
python3 scripts/validate_sales_truth_ocean_drop_parity.py \
  --as-of YYYY-MM-DD \
  --ocean-drop <path_to_ocean_drop_csv> \
  --strict
```

Strict behavior:
- Compare published truth vs normalized Ocean Drop reference by `sale_date + store_code`.
- Enforce both:
  - aggregate parity (units, revenue, orders)
  - order-id set parity
- Any mismatch outside volatility window is hard fail (non-zero exit).

## Artifacts
Validator must emit:
- `exports/validation/sales_ocean_drop_parity/<as_of>/parity_report.json`
- `exports/validation/sales_ocean_drop_parity/<as_of>/parity_report.md`
- `exports/validation/sales_ocean_drop_parity/<as_of>/diff_missing_order_ids.csv`
- `exports/validation/sales_ocean_drop_parity/<as_of>/diff_extra_order_ids.csv`
- `exports/validation/sales_ocean_drop_parity/<as_of>/diff_date_mismatches.csv`

## Fail-Closed Clauses
- Missing required input columns: hard fail.
- Unknown warehouse/store mapping in strict mode: hard fail.
- Missing delivered identity (`sku_key`/`my_size`) in strict mode: hard fail.
- No silent fallback to external reference inside published truth views.
