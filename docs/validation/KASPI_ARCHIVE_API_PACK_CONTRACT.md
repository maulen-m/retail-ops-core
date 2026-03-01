# KASPI_ARCHIVE_API_PACK_CONTRACT

## Purpose
Define strict integrity checks for API-extracted Kaspi archive packs (`creationDate` mode).

## Contract
- Source: Kaspi API archive/history extractor.
- Expected date semantics: `creationDate`.
- Required checks:
  - Full window coverage (`windows.csv` spans requested `since..until` with `status=ok`).
  - Per-store CSV exists (`store_<STORE>/ArchiveOrders_<STORE>.csv`).
  - Schema sanity for exported columns.
- Not required:
  - `Дата изменения статуса` completeness for completed rows.
    API payload does not reliably provide this field for historical ranges.

## Strict Failure Conditions
- Missing `store_*` folders.
- Window mismatch or non-`ok` window status.
- Missing expected per-store CSV.
- `as_of` outside pack range.

## Validator
- Script: `scripts/validate_kaspi_archive_pack_integrity.py`
- Command:
  - `python3 scripts/validate_kaspi_archive_pack_integrity.py --source api --strict --as-of <YYYY-MM-DD>`
