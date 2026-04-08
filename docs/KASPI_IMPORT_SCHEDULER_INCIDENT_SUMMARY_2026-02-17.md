# Kaspi Import Scheduler Incident Summary (2026-02-17)

> ARCHIVED — schedule references preserved for incident history.
> Current runtime authority: `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`.

## Context
- Incident: scheduled import/append flow did not reliably place today's orders into `excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Impact: operational uncertainty (schedule seemed missed), false hard-fail outcomes, and delayed confidence in workbook completeness.
- Fix commit: `8029c97`.

## Root Problems
1. Scheduler config drift.
- Active LaunchAgent had only `16:05` and was missing `11:00`.
- Result: one expected daily run never triggered.

2. Final gate logic used live API after import, not the run snapshot.
- `run_full_import.command` exported `ActiveOrders.xlsx`, then import appended from that snapshot.
- Final gate compared CRM vs live API at the end of the run.
- If new orders appeared in API after export, gate reported a failure even when append was correct for the exported snapshot.

3. This looked like random break/fix behavior.
- Because API data changes during runtime, failures appeared intermittent even when append logic itself was functioning.

## Solution
1. Restored intended daily schedule.
- Added dual schedule entries (`11:00`, `16:05`) to LaunchAgent plist.
- Kept installer output aligned with real schedule to avoid future drift.

2. Switched strict success gate to snapshot parity.
- Captured a temp copy of `excel_ui/ActiveOrders/ActiveOrders.xlsx` before Step 2.
- Passed snapshot + CRM + target date to evaluator.
- Evaluator now validates: "all target-date order IDs from the run snapshot exist in CRM".
- This removes false failures caused by live API drift after snapshot export.

3. Kept unattended-safe runtime behavior.
- Retained timeout wrapper and unattended flags in Step 2.
- Ensured temp artifacts are cleaned after evaluation.

## Files Changed, Why, and How
- `config/com.example.kaspi-import.plist`
  - Why: schedule mismatch vs expected business windows.
  - How: `StartCalendarInterval` set to two entries: `11:00` and `16:05`.

- `scripts/install_scheduler.sh`
  - Why: installer output must reflect true schedule contract.
  - How: schedule summary lines updated to show both run times.

- `excel_ui/run_full_import.command`
  - Why: strict gate was comparing to moving API target.
  - How: added pre-Step2 `ActiveOrders` snapshot capture; final evaluator call now includes `--activeorders-file`, `--crm-file`, `--target-date`; temp cleanup added.

- `scripts/evaluate_import_run_result.py`
  - Why: needed deterministic success criteria for unattended runs.
  - How: added snapshot-based parity mode while preserving legacy health-json mode; added robust target-date parsing path.

- `scripts/report_import_status.py`
  - Why: support machine-readable post-run health signals.
  - How: added `--json-out` payload emission (totals/store rows/partial API flags) used by strict gate flow.

- `tests/test_kaspi_import_scheduler_contract.py`
  - Why: prevent scheduler regressions.
  - How: asserts exact schedule pairs `[(11, 0), (16, 5)]`.

- `tests/test_run_full_import_command_step2.py`
  - Why: lock Step 2 unattended/snapshot-gate command contract.
  - How: asserts snapshot creation and evaluator args in script text.

- `tests/test_evaluate_import_run_result.py`
  - Why: fail-first coverage for snapshot gate behavior.
  - How: added pass/fail cases for snapshot-vs-CRM parity by target date.

- `tests/test_report_import_status.py`
  - Why: ensure JSON report stability and API filter expectations.
  - How: added JSON output contract test and delivery-state usage test.

- `.claude/PROGRESS.md`
  - Why: track outcomes and ops-relevant decisions.
  - How: added dated summary of root cause/fix/verification.

- `.claude/SESSION_LOG.md`
  - Why: preserve executable evidence trail.
  - How: added detailed incident log, commands, and post-fix proof.

## Verification Evidence
- Targeted tests: `21 passed` for scheduler/Step2/evaluator/report suites.
- Scheduler runtime: LaunchAgent showed trigger execution and completion (`runs=1`, `last exit code=0` for 16:05 run).
- Final parity check on 2026-02-17: `API_TODAY=52`, `CRM_TODAY=52`, `MISS_CRM=0`.
- Workbook safety checks:
  - integrity validator: `Errors: 0`
  - Excel open probe: `OK=True`.

## Operational Note
- If `11:00` schedule is added/reloaded after 11:00 local time, it will not backfill retroactively for that day; it starts from next eligible day/time.

## Follow-up Hardening (V2.1, 2026-02-17)
- Strict preflight now defaults to tighter workbook freshness (`36h`) and rejects future workbook mtimes beyond skew (`120s`).
- Strict preflight bootstraps into repo `.venv/bin/python` when present, reducing launchd interpreter drift risk.
- Oracle pack contract now explicitly includes workbook-anchor comparator chain for external analysis:
  - `scripts/validate_sales_vs_workbook_anchor.py`
  - `scripts/validate_sales_against_workbook.py`

## Current authoritative schedule (supersedes incident-time 16:05)
- This document records incident-time recovery on `2026-02-17`.
- Current production contract is owned by `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`.
- Current authoritative schedule:
  - import: `11:00`, `15:02`, `16:01`
  - waybill deadline: `18:30`
