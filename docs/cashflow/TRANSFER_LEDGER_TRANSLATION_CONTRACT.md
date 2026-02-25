# Transfer Ledger Translation Contract

## Purpose
Normalize transfer-ledger movements into `fact_cashflow_events` with idempotence and no double-counting.

## Entry Point
- `scripts/translate_transfer_ledger_to_cashflow.py`

## Write Safety
- Default mode is dry-run.
- Apply mode requires all of:
  - `ENABLE_CASHFLOW_WRITE=1`
  - `--apply`
  - `--backup-path <existing_file>`

## Outputs
- `exports/daily/<YYYY-MM-DD>/transfer_ledger_translation_report.json`
- `exports/daily/<YYYY-MM-DD>/transfer_ledger_translation_report.md`

## Required Report Fields
- `mode`
- `status`
- `dry_run_first_count`
- `dry_run_second_count`
- `applied_count`
- `post_apply_dry_run_count`
- `before_event_count`
- `after_event_count`
- `errors`

## Fail-Closed Rules
- Dry-run idempotence mismatch => RED.
- Apply without env gate + backup path => hard error.
- Post-apply dry-run must be `0` (no duplicates); otherwise RED.
