# COGS Forensic Reference Supersession Decision

## Decision
- For `truth_source=webui_archive`, the legacy forensic reference file from `run_20260304_032257` is superseded.
- It remains a diagnostic comparison artifact, not the blocking authority for strict WebUI rollout.
- For `truth_source=db`, supersession is allowed only for validation windows that start after the forensic file's max delivered sale date and contain zero forensic rows.

## Why
- The legacy forensic file shows month-level COGS gaps for Jan-Feb 2026.
- The legacy forensic file has delivered rows from 2025-06-06 through 2026-02-24 and no delivered rows in March-June 2026.
- The current internal controls that operate on the workbook-catalog-synced DB are green:
  - `validate_monthly_economics_parity.py --since 2025-06-06 --until 2026-03-07 --strict`
  - `audit_cogs_realism.py --as-of 2026-03-07 --days 60 --strict`
- The post-forensic DB controls for the current green-path window are green:
  - `validate_cogs_completeness_by_month.py --start 2026-03-01 --end 2026-06-14 --strict`
  - `audit_cogs_realism.py --as-of 2026-06-14 --days 60 --strict`
- The mismatch is therefore treated as stale external-reference drift, not live DB economics corruption.

## Strict Contract
- Supersession applies only when the required replacement reports are present and `PASS`.
- If either replacement report is missing or red, `validate_cogs_realism_vs_forensic.py --strict` must fail closed.
- DB supersession must also prove the validation window has zero forensic rows and starts after the forensic max delivered sale date. In-window DB-vs-forensic mismatches must still fail closed.

## Replacement Authority
- Monthly economics parity summary
- Current 60-day COGS realism audit

## Change Management
- Update this decision first.
- Then update `config/cogs_forensic_reference.yaml`.
- Then update tests and validator logic.
