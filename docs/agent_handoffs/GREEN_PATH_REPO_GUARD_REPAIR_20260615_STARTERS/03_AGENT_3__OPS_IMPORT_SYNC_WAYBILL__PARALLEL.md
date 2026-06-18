# Agent 3 - Ops Import, Sync, And Waybill Contracts

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/orchestrator_runs/20260615_083131_green_path_june15_continuation/evidence/repo_guard_full_pytest_rerun_20260615_1320/closeout.md`
4. this starter prompt.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/20260615_repo_guard_repair/agent3_ops_import_sync_waybill_closeout.md`

## Objective

Repair operational contract failures in CRM import, Kaspi sync enrichment, waybill scheduler contract, and waybill selection filtering. Keep daily live automations untouched.

## Failing Tests

- `tests/test_import_orders_to_crm.py::test_main_does_not_archive_when_candidate_promotion_fails`
- `tests/test_kaspi_waybill_deadline_scheduler_contract.py::test_waybill_deadline_plist_runs_merged_build_waybills_command`
- `tests/test_sync_kaspi_orders_enrich_flag.py::test_main_calls_enrichment_for_all_mode`
- `tests/test_sync_kaspi_orders_enrich_flag.py::test_main_calls_enrichment_for_single_store_mode`
- `tests/test_waybill_selection_filters.py::test_build_daily_waybills_read_db_orders_filters_status_signature`

## Boundaries

May edit only:

- `scripts/import_orders_to_crm.py`
- `scripts/sync_kaspi_orders.py`
- `scripts/build_daily_waybills.py`
- waybill deadline scheduler config/test if needed
- the focused tests named above

Do not change installed LaunchAgents. Do not send Telegram. Do not run live imports or waybill sends. Test-only fixtures are allowed.

## Required Validation

Run the focused tests above. Also run:

- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- scoped `git diff --check`

