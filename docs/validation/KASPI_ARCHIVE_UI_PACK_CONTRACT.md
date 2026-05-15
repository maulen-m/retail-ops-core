# KASPI_ARCHIVE_UI_PACK_CONTRACT

## Purpose
Define strict integrity checks for UI-exported Kaspi archive packs used for delivered-day truth alignment.

## Contract
- Source: Kaspi merchant UI archive export (`Архив`), 90-day windows.
- Expected date semantics: delivered/status-change capable.
- Required checks:
  - Full window coverage (`windows.csv` spans requested `since..until` with `status=ok`).
  - Per-store CSV exists (`store_<STORE>/ArchiveOrders_<STORE>.csv`).
  - Required columns include `Статус` and `Дата изменения статуса`.
  - Completed rows (`Выдан`/`Завершен`) must have non-empty `Дата изменения статуса`.

## Date-Mode Separation
- Delivered/sales truth uses `Дата изменения статуса` (`statusChangeDate`) for completed rows.
- Shipped truth uses API `courierTransmissionDate` and must not be inferred from creation date.
- Historical shipped parity checks must query both API states: `KASPI_DELIVERY` and `ARCHIVE`.

## Strict Failure Conditions
- Any API-pack style blank status-change date for completed rows.
- Missing windows or non-`ok` window status.
- Missing store CSV.
- `as_of` outside pack range.

## Validator
- Script: `scripts/validate_kaspi_archive_pack_integrity.py`
- Command:
  - `python3 scripts/validate_kaspi_archive_pack_integrity.py --source ui --strict --as-of <YYYY-MM-DD>`

## Operator Wrapper
- Preferred read-only refresh command:
  - `python3 scripts/run_webui_archive_source_refresh.py --since <YYYY-MM-DD> --until <YYYY-MM-DD> --stores <STORE,STORE> --mode auto --strict`
- The wrapper delegates to existing UI archive download/full-parse/normalization validators and writes immutable evidence only.
- Production DB apply, workbook mutation, scheduler mutation, and external writes are out of scope for this wrapper.
