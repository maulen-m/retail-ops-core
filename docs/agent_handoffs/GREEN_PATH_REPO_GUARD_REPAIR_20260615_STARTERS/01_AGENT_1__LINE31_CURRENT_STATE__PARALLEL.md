# Agent 1 - LINE31 Current-State Contracts

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/green_path_run/STATUS.md`
4. `~/Docs/Autonomous_business/.claude/orchestrator_runs/20260615_083131_green_path_june15_continuation/evidence/repo_guard_full_pytest_rerun_20260615_1320/closeout.md`
5. this starter prompt.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/20260615_repo_guard_repair/agent1_line31_current_state_closeout.md`

## Objective

Repair the LINE31 downstream test-contract failures so they match the current fail-closed/yellow owner-source and noncreative state without weakening production validators.

## Failing Tests

- `tests/test_prepare_line31_launch_readiness_from_assets.py::test_prepare_launch_readiness_creative_ready_pending_approval`
- `tests/test_prepare_line31_launch_readiness_from_assets.py::test_prepare_launch_readiness_asset_dir_with_approval_is_launch_ready`
- `tests/test_prepare_line31_launch_readiness_from_assets.py::test_prepare_launch_readiness_owner_approved_records_evidence`
- `tests/test_report_line31_next_inputs_status.py::test_next_inputs_command_outputs_json`
- `tests/test_report_line31_next_launch_action.py::test_report_current_state_points_to_fill_creative_mapping`
- `tests/test_report_line31_next_launch_action.py::test_report_command_outputs_json`
- `tests/test_validate_line31_launch_readiness.py::test_current_line31_evidence_passes_when_pending_creative_is_allowed`
- `tests/test_validate_line31_launch_readiness.py::test_line31_launch_readiness_commands_do_not_mutate_protected_surfaces`
- `tests/test_write_line31_current_launch_status.py::test_current_status_points_to_latest_packet_and_pending_creative`

## Boundaries

May edit only LINE31-related scripts/tests/docs needed for these failures:

- `scripts/prepare_line31_launch_readiness_from_assets.py`
- `scripts/report_line31_next_inputs_status.py`
- `scripts/report_line31_next_launch_action.py`
- `scripts/validate_line31_launch_readiness.py`
- `scripts/write_line31_current_launch_status.py`
- LINE31 tests named above.

Do not edit dashboard/status/scoreboard/session files.

## Required Validation

Run the focused LINE31 tests above. Also run:

- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- scoped `git diff --check`

