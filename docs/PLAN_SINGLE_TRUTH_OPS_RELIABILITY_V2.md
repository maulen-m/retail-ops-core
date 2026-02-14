# PLAN_SINGLE_TRUTH_OPS_RELIABILITY_V2

## Objective
Make single-truth enforcement operationally reliable (scheduler runs with correct Python/deps),
reduce repo dirtiness, and prevent stale workbook anchors from giving false confidence.

## Scope
- Repo: ~/Docs/Autonomous_business
- In scope: launchd plists, strict preflight wrapper, anchor docs, git hygiene, alerting.
- Out of scope: employee worktree; any write-side automation not explicitly gated.

## Non-negotiables
- Tests first (fail-first evidence).
- No DB write-side actions unless env gate + --apply.
- Keep edits surgical; ignore unrelated dirty files.

## Phase A — Scheduler Interpreter Hardening
- Change launchd ProgramArguments to use /usr/bin/env python3 (PATH-driven) or venv python.
- Add contract test for expected interpreter strategy.

## Phase B — Workbook Anchor Freshness
- Add freshness check (mtime threshold or max-date check).
- Fail closed on stale workbook.
- Add tests.

## Phase C — Preflight Failure Alerting
- Add optional alert on strict preflight failure.
- Ensure alert is best-effort: no crash if alert config missing.
- Add tests.

## Phase D — Git Hygiene
- Add .gitignore for logs/backups/oracle listings.
- Decide policy for docs/transfer_ledger tracked outputs.

## Verification Gates
- python3 scripts/validate_params.py --strict
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
- python3 scripts/run_contract_suite.py --fixture small
- python3 scripts/validate_single_truth_system.py
- scripts/lint_docs.sh
- scripts/check_no_db_tracked.sh

## Rollback
- git revert <commits>
- launchctl unload jobs if needed
- restore db backup only if apply actions were run
