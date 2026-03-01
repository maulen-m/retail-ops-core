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

## Strict Failure Conditions
- Any API-pack style blank status-change date for completed rows.
- Missing windows or non-`ok` window status.
- Missing store CSV.
- `as_of` outside pack range.

## Validator
- Script: `scripts/validate_kaspi_archive_pack_integrity.py`
- Command:
  - `python3 scripts/validate_kaspi_archive_pack_integrity.py --source ui --strict --as-of <YYYY-MM-DD>`
