## Owner Truth Final Blockers Clearance

Date: 2026-03-10
Branch: `codex/TASK-webui-owner-truth-operationalization-v1`
Worktree: repo-local operationalization worktree

### Mission
Clear the last blockers on top of the already-completed owner-truth live-ops fixes, without reopening WebUI source work, without replay fallback in live mode, and without any DB write until a read-first case file proves it is required.

### Stop Rule
Before V1, reconcile the actual worktree against the fresher `db_main` handoff. If the worktree does not match that fresher state, stop immediately and emit a divergence pack instead of continuing.

### Phase Breakdown

#### V0 — Freshness Reconcile + Delta Freeze
- Verify branch, head, dirty state, and rollback anchor.
- Re-run the two currently asserted blocker validators:
  - `validate_webui_archive_vs_current_db.py`
  - `validate_recent_identity_coverage.py`
- Compare actual results to the fresher `db_main` handoff and the older oracle bundle.
- Freeze the current delta with a checkpoint patch or narrow checkpoint commit.
- Acceptance:
  - exact current state is documented
  - divergence is explicitly classified if present
  - no repair work starts before this is resolved

Test strategy:
- No new code in V0.
- Re-run the exact runtime validators named above and preserve their outputs.

#### V1 — ACMEWEAR DB-Absence Case File
- Only if V0 matches the fresher state.
- Build a read-only case file for ACMEWEAR order `832677455`.
- Acceptance:
  - exact absence path is reproduced
  - deterministic classification recorded

Test strategy:
- Add/extend a contract test for `validate_webui_archive_vs_current_db.py` only if code is touched.

#### V2 — ACMEWEAR DB-Absence Repair
- Only if V1 proves a deterministic repair path.
- Perform one narrow repair with backup, env gate, `--apply`, before/after diffs, and rollback note.
- Acceptance:
  - `missing_in_db_orders=0`

Test strategy:
- Re-run the DB validator contract tests if code is touched.
- Re-run the strict DB validator before and after.

#### V3 — UNIVERSAL Governance Identity Coverage Closure
- Only after V2 is green.
- Clear `validate_recent_identity_coverage.py --strict`.
- Acceptance:
  - validator passes for `2026-03-09`

Test strategy:
- Add a contract test only if code is touched.

#### V4 — Full Live Green Proving
- Re-run:
  - `run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`
  - `system_doctor.py --strict --project-root . --as-of 2026-03-09`
- Prove rerun stability.

Test strategy:
- No new tests unless runtime code changes are required.

#### V5 — Merge / Release / Oracle Refresh
- Only after V4 is green.
- Refresh merge manifest, release evidence, and Oracle listing pack.

#### V6 — Automation Hardening
- Only if needed after V4.
- Keep fail-closed behavior unchanged.

#### V7 — Deferred Scale Queue Lock
- Keep all scale items out of merge scope.

### Current Decision
V0 stopline is active until state reconciliation proves the worktree matches the fresher handoff.
