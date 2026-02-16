# PLAN_SINGLE_TRUTH_OPS_RELIABILITY_V2_EXECUTION_2026-02-17

## Summary
Execute a single-pass reliability hardening in main repo so strict daily operations are resilient and auditable:
- launchd scheduler runs with interpreter strategy that does not depend on `/usr/bin/python3`
- workbook anchor freshness is enforced fail-closed
- strict preflight can send best-effort failure alerts
- strict preflight auto-generates missing daily `BUSINESS_INSIDES` snapshot before validation
- runtime artifact dirt is controlled via `.gitignore` without mutating tracked transfer ledgers

## Explicit Exclusion
Ads integration is **out of scope** in this execution and remains in a separate worktree stream until that stream is successful.

## Non-negotiables
- Tests first; fail-first evidence before implementation changes.
- No write-side action unless env gate + explicit CLI flag.
- Ignore unrelated repository changes.

## Public Interface Changes
1. `scripts/run_strict_daily_preflight.py`
- Add `--ensure-business-insides` (default enabled)
- Add `--business-insides-as-of` (default: today)
- Behavior: if daily business-insides snapshot is missing, generate it before strict validation.

2. `config/com.example.single-truth-preflight.plist`
- Keep `/usr/bin/env python3`
- Include `--send-alert-on-fail`
- Include `--ensure-business-insides`

3. Docs
- Update `docs/DAILY_SOP.md` and `docs/ARCHITECTURE.md` with strict preflight flow.

## Test Plan (must fail before implementation)
- `tests/test_run_strict_daily_preflight.py`
  - autogenerates missing business-insides snapshot
  - fails if generation fails
  - still enforces stale workbook fail-closed
- `tests/test_single_truth_ops_scheduler_contract.py`
  - preflight plist contains `--ensure-business-insides`
  - interpreter remains `/usr/bin/env` + `python3`
- `tests/test_gitignore_ops_reliability.py`
  - runtime artifacts ignored
  - no transfer-ledger ignore wildcard added

## Verification Gates
1. `python3 scripts/validate_params.py --strict`
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
3. `python3 scripts/run_contract_suite.py --fixture small`
4. `python3 scripts/validate_single_truth_system.py`
5. `scripts/lint_docs.sh`
6. `scripts/check_no_db_tracked.sh`

## Rollback
1. `git revert <newest_commit> ... <oldest_commit>`
2. If any write-side apply was run: restore `db/backups/app.db.pre_ops_reliability_v2_exec_<timestamp>.sqlite` to `db/app.db`
3. Re-run:
- `python3 scripts/validate_params.py --strict`
- `scripts/check_no_db_tracked.sh`
