# Owner Truth Live Daily Artifact Contract

## Purpose

Define the fail-closed contract for `exports/daily/<as_of>/daily_ops_report.json` in live mode.

This artifact is required operational evidence for `system_doctor.py` and for owner-truth live proving.

## Source of Truth

- Live mode report source: `exports/validation/board_v8_runtime/<as_of>/daily_ops_summary.json`
- Generator: `scripts/generate_daily_ops_report.py`
- Validator: `scripts/validate_daily_ops_report.py --strict`
- Orchestrator: `scripts/run_owner_truth_daily.py`

## Non-Negotiable Rules

- Live mode must generate `daily_ops_report.json` from the live `run_kaspi_daily_ops.py` summary.
- Live mode must not copy or fabricate `daily_ops_report.json`.
- Live mode must not use replay-only seeds to satisfy this artifact.
- The artifact must be generated even when live daily ops is red, as long as the live summary exists.
- A red live daily ops summary does not become green through report generation; the owner-truth run remains failed on the original live stopline.
- `system_doctor.py` validates the report schema/artifact presence; it does not reinterpret a red daily-ops summary as green.

## Required Fields

`daily_ops_report.json` must include:

- `generated_at`
- `as_of`
- `status`
- `ok`
- `exit_code`
- `profile`
- `steps_total`
- `steps_failed`
- `failed_step_names`
- `stores_total`
- `stores_red`
- `stores_green`
- `red_store_codes`
- `store_results`
- `shipping_backlog`
- `summary_json`

## Runtime Behavior

- If `run_kaspi_daily_ops.py` succeeds:
  - `run_owner_truth_daily.py` must generate and validate `daily_ops_report.json`
  - then continue with downstream steps
- If `run_kaspi_daily_ops.py` fails:
  - `run_owner_truth_daily.py` must still generate and validate `daily_ops_report.json`
  - then stop with the original `RUN_KASPI_DAILY_OPS_FAIL` stopline

## Doctor Contract

- `system_doctor.py --strict --as-of <date>` requires `exports/daily/<date>/daily_ops_report.json`
- Missing report = hard red
- Schema-invalid report = hard red

## Change Control

Any change to this artifact contract must update:

- this document
- `scripts/generate_daily_ops_report.py`
- `scripts/validate_daily_ops_report.py`
- `scripts/run_owner_truth_daily.py`
- contract tests for generator, validator, and owner-truth daily orchestration
