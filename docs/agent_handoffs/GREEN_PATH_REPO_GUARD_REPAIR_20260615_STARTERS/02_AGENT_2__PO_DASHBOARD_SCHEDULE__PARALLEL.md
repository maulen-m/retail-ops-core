# Agent 2 - PO Dashboard And Schedule Contracts

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/orchestrator_runs/20260615_083131_green_path_june15_continuation/evidence/repo_guard_full_pytest_rerun_20260615_1320/closeout.md`
4. this starter prompt.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/20260615_repo_guard_repair/agent2_po_dashboard_schedule_closeout.md`

## Objective

Repair PO dashboard/schedule failures from the current pytest inventory. Prefer updating tests for intentional API signature evolution only when the implementation is correct; otherwise fix the smallest script bug.

## Failing Tests

- `tests/test_plan0_next_po.py::test_plan0_is_next_po_after_latest_real`
- `tests/test_po_dashboard_overrides.py::TestPrepModelB::test_all_els_skus_prep_1`
- `tests/test_po_schedule_anchor.py::test_plan0_message_date_is_2026_02_25`
- `tests/test_po_schedule_anchor.py::test_following_plans_are_plus_10_days`

## Boundaries

May edit only:

- `scripts/generate_po_dashboard_data.py`
- the three PO test files named above
- a narrow PO docs note only if needed by repo contract

No DB/workbook/external/LaunchAgent writes.

## Required Validation

Run the focused failing PO tests and any nearest PO tests you touched. Also run:

- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- scoped `git diff --check`

