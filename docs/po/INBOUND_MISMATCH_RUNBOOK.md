# Inbound Mismatch Runbook

Purpose: fail closed when inbound workbook sheets disagree before any publication pipeline consumes PO arrivals/payment truth.

## Validator

```bash
python3 scripts/validate_inbound_sheet_consistency.py \
  --xlsx config/anchors/INBOUND_CALENDAR_LATEST.xlsx --json
```

Exit codes:
- `0`: no mismatches.
- `1`: mismatch or parsing contract breach.

## What is compared
- `Inbounds_sheet` is authoritative for row quantities.
- Quantity precedence: `Actual_qty` (if present and positive) else `Qty`.
- `Cargo_send_*` sheets are compared against `Inbounds_sheet` by `(PO_part_id, SKU_key)`.
- `PO_part_id_Totals.Total Units` is compared against summed authoritative inbound rows per `PO_part_id`.

## Strict gate integration

`python3 scripts/validate_params.py --strict` runs this validator automatically using:
- `AB_INBOUND_WORKBOOK_PATH` when set,
- otherwise `config/anchors/INBOUND_CALENDAR_LATEST.xlsx`.

If any mismatch is detected, strict validation fails and publication must stop.

## Operator response
1. Fix workbook mismatch at source (cargo/inbounds/totals).
2. Re-run the validator until exit `0`.
3. Re-run strict chain.
