# Agent 5 - Validator Output And Semantics Contracts

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/orchestrator_runs/20260615_083131_green_path_june15_continuation/evidence/repo_guard_full_pytest_rerun_20260615_1320/closeout.md`
4. this starter prompt.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/20260615_repo_guard_repair/agent5_validator_semantics_closeout.md`

## Objective

Repair validator semantic/output failures outside the LINE31, PO, ops-import, and WebUI-owner clusters.

## Failing Tests

- all failures in `tests/test_validate_inbound_sheet_consistency.py`
- `tests/test_validate_opex_readiness.py::test_validate_opex_readiness_pass`
- `tests/test_validate_returns_economics_audit.py::test_validate_returns_economics_fails_stale_leak`
- `tests/test_validate_shipped_truth_crm_waybill.py::test_validate_passes_with_cancel_normalization`

## Boundaries

May edit only:

- `scripts/validate_inbound_sheet_consistency.py`
- `scripts/validate_opex_readiness.py`
- `scripts/validate_returns_economics_audit.py`
- `scripts/validate_shipped_truth_crm_waybill.py`
- the focused tests named above
- a narrow validator contract doc only if required

No production DB/workbook/external/LaunchAgent writes.

## Required Validation

Run the focused failing tests above. Also run:

- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- scoped `git diff --check`

