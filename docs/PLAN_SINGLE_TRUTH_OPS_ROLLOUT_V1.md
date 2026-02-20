# PLAN_SINGLE_TRUTH_OPS_ROLLOUT_V1

## Objective
Roll out Single-Truth Hardening V1 from stabilization worktree into main repo with no regression to live order processing and no uncontrolled write-side behavior.

## Scope
- Repo: `~/Docs/Autonomous_business`
- Source commits: `80e845f d519199 9892a7c e8a7329`
- Optional memory commit: `b6e7dd0` (only if conflict-free and requested)

## Non-Negotiables
- Ignore unrelated dirty files.
- No DB write-side actions unless both env gate + `--apply` are set.
- No employee worktree changes.
- Keep changes surgical and auditable.

## Phase 0 — Branch + Baseline
1. Create branch `codex/TASK-single-truth-ops-rollout-v1`.
2. Confirm source commits are available.
3. Confirm no DB artifacts are staged.

## Phase 1 — Integrate Hardening Commits
1. Cherry-pick docs/tests/ops/schema commits from stabilization branch.
2. Resolve conflicts only in touched files.
3. Exclude Oracle pack artifacts and generated snapshots from commits.

## Phase 2 — Validate Rollout
Run full required gates:
1. `python3 scripts/validate_params.py --strict`
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q`
3. `python3 scripts/run_contract_suite.py --fixture small`
4. `python3 scripts/validate_single_truth_system.py`
5. `scripts/lint_docs.sh`
6. `scripts/check_no_db_tracked.sh`

## Phase 3 — Deliver Evidence
1. Report exact commands and PASS results.
2. Provide rollback commands.
3. Provide cherry-pick trail for auditability.

## Done Definition
- All target commits integrated in main rollout branch.
- Full gate chain green.
- No DB files tracked.
- No unrelated files staged.

## Rollback
1. Code rollback:
   - `git revert <newest_commit> ... <oldest_commit>`
2. DB rollback (only if a write apply was explicitly performed):
   - restore latest backup file from `db/backups/` to `db/app.db`
3. Re-check:
   - `python3 scripts/validate_params.py --strict`
   - `scripts/check_no_db_tracked.sh`
