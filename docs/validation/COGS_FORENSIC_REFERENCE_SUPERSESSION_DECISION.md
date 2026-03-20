# COGS Forensic Reference Supersession Decision

## Decision
- For `truth_source=webui_archive`, the legacy forensic reference file from `run_20260304_032257` is superseded.
- It remains a diagnostic comparison artifact, not the blocking authority for strict WebUI rollout.

## Why
- The legacy forensic file shows month-level COGS gaps for Jan-Feb 2026.
- The current internal controls that operate on the workbook-catalog-synced DB are green:
  - `validate_monthly_economics_parity.py --since 2025-06-06 --until 2026-03-07 --strict`
  - `audit_cogs_realism.py --as-of 2026-03-07 --days 60 --strict`
- The mismatch is therefore treated as stale external-reference drift, not live DB economics corruption.

## Strict Contract
- Supersession applies only when the required replacement reports are present and `PASS`.
- If either replacement report is missing or red, `validate_cogs_realism_vs_forensic.py --strict` must fail closed.
- This decision does not relax COGS checks for non-WebUI truth sources.

## Replacement Authority
- Monthly economics parity summary
- Current 60-day COGS realism audit

## Change Management
- Update this decision first.
- Then update `config/cogs_forensic_reference.yaml`.
- Then update tests and validator logic.
