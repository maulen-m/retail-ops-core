# Agent 4 - WebUI Archive And Owner-Truth Contracts

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/orchestrator_runs/20260615_083131_green_path_june15_continuation/evidence/repo_guard_full_pytest_rerun_20260615_1320/closeout.md`
4. this starter prompt.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/20260615_repo_guard_repair/agent4_webui_owner_truth_closeout.md`

## Objective

Repair WebUI archive and owner-truth test/API contract failures. Keep all work local and test-focused; no browser, no live web UI, no downloads.

## Failing Tests

- `tests/test_run_webui_archive_full_parse.py::test_run_webui_archive_full_parse_marks_missing_credentials_without_download`
- `tests/test_triage_owner_truth_stoplines.py::test_triage_owner_truth_stoplines_pass`
- `tests/test_triage_owner_truth_stoplines.py::test_triage_owner_truth_stoplines_fails_when_missing`
- `tests/test_triage_owner_truth_stoplines.py::test_triage_owner_truth_stoplines_webui_pass`
- `tests/test_triage_owner_truth_stoplines.py::test_triage_owner_truth_stoplines_webui_fallback_contract_pass`
- `tests/test_triage_owner_truth_stoplines.py::test_triage_owner_truth_stoplines_db_uses_publication_validation_fallback`
- `tests/test_validate_webui_archive_bands.py::test_validate_webui_archive_vs_current_db_falls_back_to_repo_quarantine_csv`
- `tests/test_validate_webui_archive_bands.py::test_validate_webui_archive_vs_current_db_falls_back_to_repo_authority_decision`
- `tests/test_validate_webui_archive_bands.py::test_validate_webui_archive_vs_current_db_accepts_workbook_anchor_quarantine_under_crm_authority`
- `tests/test_validate_webui_archive_bands.py::test_validate_webui_archive_vs_current_db_keeps_workbook_anchor_quarantine_hard_without_crm_authority`

## Boundaries

May edit only WebUI/archive/owner-truth scripts and tests involved in the above failures.

Do not start browser automation. Do not download from Kaspi. Do not mutate production DB/workbook/external systems.

## Required Validation

Run the focused failing tests above. Also run:

- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- scoped `git diff --check`

