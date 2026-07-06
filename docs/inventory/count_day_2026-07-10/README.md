# Physical Count Day Prep Pack - 2026-07-10

Purpose: printable and machine-readable preparation pack for the 2026-07-10 warehouse physical count.

Scope:
- Expected balances are derived from `stock_ledger` using read-only SQLite access.
- The pack is file-only. It does not write `db/app.db`.
- Excel UI files are out of scope.
- Count-day intake must remain dry until an owner-approved count manifest and explicit write gate exist.

Packet contents:
- `count_day_expected_balances_20260710.csv` - printable line-level count sheet by priority family, size, and store.
- `count_day_expected_balances_20260710.xlsx` - workbook with `Count sheet`, `Family summary`, and `Size matrix` tabs.
- `count_day_family_summary_20260710.csv` - per-family sheet counts and flags.
- `count_day_family_size_matrix_20260710.csv` - per-family x size expected-balance matrix.
- `intake_template_20260710.csv` - OCR/manual intake template.
- `OD-004_photo_protocol_checklist.md` - count-day photo protocol restated from the OD-004 registry.
- `OCR_INTAKE_FLOW.md` - photo -> OCR -> intake CSV -> count-anchor lane flow.
- `OWNER_LOGISTICS_QUESTIONS.md` - batched open questions for owner.

Evidence:
- `exports/validation/g_count_prep_20260706/count_sheet_build_summary.json`
- `exports/validation/g_count_prep_20260706/count_sheet_family_summary.csv`
- `exports/validation/g_count_prep_20260706/synthetic_manifest_validation.txt`
- `exports/validation/g_count_prep_20260706/synthetic_anchor_dry_run_stdout.json`

Operator rule:
- Use the count sheets as expected-balance guides, not as count truth.
- The production count anchor starts only after photo/OCR reconciliation and owner approval of the manifest.
