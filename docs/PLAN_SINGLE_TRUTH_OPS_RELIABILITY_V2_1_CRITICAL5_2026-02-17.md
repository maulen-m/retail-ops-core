# PLAN_SINGLE_TRUTH_OPS_RELIABILITY_V2_1_CRITICAL5_2026-02-17

## Summary
Critical 5 hardening for Single-Truth Ops Reliability V2:
1. Include workbook comparator chain in Oracle pack contract.
2. Pin strict preflight runtime to repo `.venv/bin/python` when available.
3. Tighten default workbook freshness to 36h.
4. Add fail-closed guard for future workbook mtimes.
5. Add tests for workbook env propagation into strict validation subprocess.

Ads integration is out of scope and remains in separate worktree stream.

## Public Interface Changes
- `scripts/run_strict_daily_preflight.py`
  - runtime bootstrap: re-exec to repo venv python when available
  - default freshness: `36h`
  - new guard: fail if workbook mtime is future beyond skew
  - new CLI: `--max-future-mtime-skew-seconds`
- `config/com.example.single-truth-preflight.plist`
  - adds `AB_CRM_WORKBOOK_MAX_AGE_HOURS=36`
  - adds `AB_CRM_WORKBOOK_MAX_FUTURE_SKEW_SECONDS=120`
- `Oracle_listings/oracle_pack_file_lists.md`
  - explicitly includes both workbook anchor scripts

## Test-First Additions
- `tests/test_run_strict_daily_preflight.py`
  - workbook env propagation assertion
  - future mtime fail-closed assertion
  - small future skew allowed assertion
  - default 36h threshold assertion
- `tests/test_preflight_python_pinning.py`
  - venv re-exec/skip behavior
- `tests/test_oracle_pack_file_lists.py`
  - comparator chain presence in pack listing contract

## Verification Gates
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_single_truth_system.py`
- `scripts/lint_docs.sh`
- `scripts/check_no_db_tracked.sh`

## Rollback
- `git revert <newest_commit> ... <oldest_commit>`
- If any write-side apply actions were executed separately, restore latest `db/backups/*.sqlite` backup to `db/app.db` and rerun strict gates.
