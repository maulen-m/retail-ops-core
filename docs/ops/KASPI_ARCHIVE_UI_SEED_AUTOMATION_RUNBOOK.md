# KASPI_ARCHIVE_UI_SEED_AUTOMATION_RUNBOOK

## Purpose
Refresh the UI status-date archive pack for all stores in one command with fail-closed validation.

## Preconditions
- UI seed XLSX files exist (one per store) with required columns (`Дата изменения статуса`, `Статус`, etc.).
- Either:
  - `--seed-root` points to folder with `*.xlsx`, or
  - existing UI anchor pack has `store_*/raw/*.xlsx`, or
  - `AB_KASPI_UI_SEED_DIR` is set.

## Validate-only refresh (default)
```bash
python3 scripts/refresh_kaspi_archive_ui_pack.py \
  --as-of 2026-03-04 \
  --since 2025-06-06 \
  --strict
```

Outputs:
- `exports/validation/archive_ui_pack_refresh/<as_of>/report.json`
- `exports/validation/archive_ui_pack_refresh/<as_of>/report.md`
- `exports/validation/archive_pack_integrity/ui/<as_of>/integrity_report.json`

## Apply anchor update (config write)
Anchor write is opt-in only.

```bash
ENABLE_ANCHOR_APPLY=1 \
python3 scripts/refresh_kaspi_archive_ui_pack.py \
  --as-of 2026-03-04 \
  --since 2025-06-06 \
  --strict \
  --apply
```

This updates `config/anchors/kaspi_archive_ui_pack.json` to the new `pack_root`.

## Stoplines
- Missing seed files -> `UI_PACK_REFRESH_FAIL`
- Strict integrity failure -> non-zero exit
- Apply without `ENABLE_ANCHOR_APPLY=1` -> non-zero exit

## Operational cadence
- Run once daily before `system_doctor --strict`.
- Keep previous pack roots immutable; never delete historical packs.
