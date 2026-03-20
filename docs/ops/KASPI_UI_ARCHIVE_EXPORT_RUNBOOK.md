# KASPI UI Archive Export Runbook

## Purpose
Operational runbook for low-human-time ocean-drop alignment with delivered status-change dates.

## Daily/On-Demand Flow
1. Build/update UI pack (seed xlsx mode or browser output import):
   - `python3 scripts/export_kaspi_archive_ui_history.py --since 2026-01-01 --until 2026-02-26 --strict --store UNIVERSAL --store ACMEWEAR --store 11KZ --store MELVIS --store STOREB --seed-xlsx <file> ...`
2. Validate UI pack contract:
   - `python3 scripts/validate_kaspi_archive_pack_integrity.py --source ui --as-of 2026-02-26 --strict`
3. Merge UI status-change dates into ocean-drop anchor dataset:
   - dry-run: `python3 scripts/build_ocean_drop_anchor_dataset.py --as-of 2026-02-26 --strict --ui-pack-root <pack_root>`
   - apply registry update: `ENABLE_OCEAN_DROP_ANCHOR_UPDATE=1 python3 scripts/build_ocean_drop_anchor_dataset.py --as-of 2026-02-26 --strict --ui-pack-root <pack_root> --update-anchor-registry --apply`
4. Ingest status-change dates into DB:
   - dry-run: `python3 scripts/ingest_kaspi_statusdates_from_ui_pack.py --strict --ui-pack-root <pack_root>`
   - apply: `ENABLE_STATUSDATE_INGEST_APPLY=1 python3 scripts/ingest_kaspi_statusdates_from_ui_pack.py --strict --ui-pack-root <pack_root> --apply`
5. Rebuild sales fact:
   - dry-run: `python3 scripts/rebuild_sales_fact_v2_from_kaspi_entries.py --as-of 2026-02-26 --strict`
   - apply: `ENABLE_SALES_FACT_V2_REBUILD_APPLY=1 python3 scripts/rebuild_sales_fact_v2_from_kaspi_entries.py --as-of 2026-02-26 --strict --apply`
6. Validate alignment:
   - `python3 scripts/validate_business_insides_ocean_drop_alignment.py --as-of 2026-02-26 --strict`
   - `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-02-26`

## Fail-Closed Rules
- No `--apply` without env gate.
- No DB write without backup artifact.
- No decision-grade BUSINESS_INSIDES if alignment report is FAIL.

## Key Artifacts
- UI pack: `exports/kaspi_archive_ui_history_<since>_to_<until>_<timestamp>/`
- Merge report: `exports/validation/ocean_drop_merge/<as_of>/merge_report.json`
- Ingest manifest: `exports/apply_manifests/statusdate_ingest_<timestamp>.json`
- BI alignment: `exports/validation/business_insides_ocean_drop_alignment/<as_of>/alignment_report.json`
