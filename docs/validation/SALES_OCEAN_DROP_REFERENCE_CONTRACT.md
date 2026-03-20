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

Anchor registry (immutable baseline pointer):
- `config/anchors/ocean_drop_sales_anchor.json`
- must define `ocean_drop_path`, `as_of_end`, `sha256`.

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

If `--ocean-drop` is omitted, strict scripts must resolve it from `config/anchors/ocean_drop_sales_anchor.json`.
The resolved file must match the locked anchor path and its sha256.

Strict behavior:
- Compare published truth vs normalized Ocean Drop reference by `sale_date + store_code`.
- Enforce both:
  - aggregate parity (units, revenue, orders)
  - order-id set parity
- Any mismatch outside volatility window is hard fail (non-zero exit).

## Volatility Window Semantics
- Default volatility window is 14 days (`--volatility-days 14`).
- Non-volatile days are older than `as_of - 13 days`.
- Decision-grade PASS requires:
  - `nonvolatile_mismatch_count == 0`
  - strict parity command exits 0
- Volatile mismatches are diagnostic only unless promoted to explicit blocker in an owning board.

## Engine Self-Sufficiency Gate
Command:
```bash
python3 scripts/validate_sales_engine_self_sufficient.py \
  --as-of YYYY-MM-DD \
  --strict
```
Contract:
- Copies DB to a temporary validation DB.
- Wipes/rebuilds `sales_fact_v2` from internal order/order-entry facts only.
- Runs parity against Ocean Drop on the rebuilt temp DB.
- Hard-fails when nonvolatile mismatch count is non-zero for configured window.

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

## Apply Safety (Repair Path)
- Default repair mode is delta-only (`--apply-delta`).
- Replace mode (`--apply-replace`) is blocked unless both env gates are set:
  - `ENABLE_OCEAN_DROP_APPLY=1`
  - `ENABLE_OCEAN_DROP_DELETE=1`
- Every apply path must emit deterministic plan artifacts:
  - `apply_plan.json`
  - `apply_plan.md`
- Every apply path must create a DB backup before writes.

## Anchor Refresh Protocol (P5)
1. Export refreshed Ocean Drop source and place it in controlled archive storage.
2. Compute file checksum:
```bash
python3 - <<'PY'
import hashlib, pathlib
p=pathlib.Path(\"<new_ocean_drop_csv>\")
print(hashlib.sha256(p.read_bytes()).hexdigest())
PY
```
3. Update `config/anchors/ocean_drop_sales_anchor.json` with:
  - `ocean_drop_path`
  - `as_of_end`
  - `sha256`
4. Re-run strict gates:
  - `python3 scripts/validate_sales_truth_ocean_drop_parity.py --strict --as-of <as_of>`
  - `python3 scripts/validate_sales_engine_self_sufficient.py --strict --as-of <as_of>`
5. Archive prior registry snapshot and reference it in journal/evidence.

## Stop-The-Line Rules
- Any attempt to bypass anchor sha256 validation.
- Any reintroduction of reference data into published truth views.
- Any strict parity/self-sufficiency failure on non-volatile window.
