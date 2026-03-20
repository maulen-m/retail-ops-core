# PLAN_WEBUI_GREEN_STABILIZATION_2026-03-08

## Purpose

Convert the evidenced `2026-03-08` WebUI archive single-truth green closeout into a durable operational baseline on a clean branch rooted at commit `86ce447782a005c47ac3d1b61dde8414900320a8`, without reopening WebUI source acquisition.

## READCHECK

- active worktree: ` ~/Docs/wt_webui_green_stabilization_v1`
- branch: `codex/TASK-webui-green-stabilization-v1`
- head: `86ce447782a005c47ac3d1b61dde8414900320a8`
- source worktree at `~/Docs/Autonomous_business` was dirty, so stabilization is isolated here by rule
- rollback anchor: `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`

## Baseline facts

- The prior closeout evidence says the rollout was green on `2026-03-08`.
- This clean baseline does not yet contain the previously uncommitted closeout/stabilization files.
- Therefore this task has two layers:
  1. selectively port the already-evidenced green closeout behavior into a clean branch,
  2. add the new stabilization work required by this plan.

## Phase order

### T0 — Release Anchor + Baseline Freeze

Goal:
- create the formal `2026-03-08` release anchor and freeze the acceptance baseline

Outputs:
- `exports/validation/owner_truth_release/2026-03-08/full_gates_green_final.md`
- `exports/validation/owner_truth_release/2026-03-08/release_manifest.json`
- `exports/validation/owner_truth_release/2026-03-08/release_inventory.txt`
- `exports/validation/owner_truth_release/2026-03-08/release_notes.md`
- `exports/validation/owner_truth_release/2026-03-08/oracle_baseline_reference.md`

Test strategy:
- read-only validation of cited evidence paths and exact commit anchoring
- ensure the release anchor cites `86ce447...`, `4124c148...`, and rollback `2026-03-04`

Acceptance:
- anchor cites exact commit, commands, evidence, and rollback path

### C1 — Deterministic Governance Prereqs

Goal:
- remove the need for hand-created governance artifacts in the daily strict path

Outputs:
- `scripts/generate_owner_truth_exceptions.py`
- `tests/test_generate_owner_truth_exceptions.py`
- updated `scripts/run_owner_truth_daily.py`
- updated `tests/test_run_owner_truth_daily_contract.py`
- updated `tests/test_system_doctor_contract.py`

Test strategy:
- write tests first for generated exceptions payload/schema and output paths
- extend daily-run contract tests so the strict path generates prerequisites instead of assuming manual artifacts
- extend doctor contract tests so governance prerequisites remain fail-closed and deterministic

Acceptance:
- `run_owner_truth_daily.py` no longer depends on hand-created governance artifacts

### H1 — Cold-Start E2E Smoke + Idempotence

Goal:
- prove the daily path can run from a cold start twice with stable semantics

Outputs:
- `scripts/smoke_test_owner_truth_daily.py`
- `tests/test_smoke_test_owner_truth_daily.py`
- `exports/validation/owner_truth_release/2026-03-08/cold_start_smoke_run_1.md`
- `exports/validation/owner_truth_release/2026-03-08/cold_start_smoke_run_2.md`
- `exports/validation/owner_truth_release/2026-03-08/idempotence_report.json`

Test strategy:
- write tests first for smoke script command graph, output capture, and approved volatile-field normalization
- compare two strict runs semantically, not by raw timestamps

Acceptance:
- two consecutive strict runs are identical except approved volatile fields

### H2 — Clean Commit / PR Split

Goal:
- produce one-intent commits and a reproducible commit manifest

Outputs:
- `exports/validation/owner_truth_release/2026-03-08/commit_manifest.json`
- `exports/validation/owner_truth_release/2026-03-08/commit_manifest.md`

Test strategy:
- no new unit tests; use git-scoped checks on commit contents and phase boundaries

Acceptance:
- final diff excludes unrelated files and commits are phase-scoped

### O1 — Overfit Reduction + Release Hygiene

Goal:
- remove unapproved closeout-date/path assumptions from active automation and active docs

Outputs:
- `scripts/check_release_hygiene.py`
- `tests/test_release_hygiene.py`
- updated `docs/validation/OWNER_PNL_PUBLICATION_CONTRACT.md`
- updated `docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md`
- updated `docs/DAILY_SOP.md`
- `exports/validation/owner_truth_release/2026-03-08/overfit_risk_register.md`

Test strategy:
- write hygiene tests first for forbidden absolute paths and disallowed closeout-date hardcoding in active automation
- run the hygiene checker in strict mode before phase completion

Acceptance:
- active docs are repo-relative and no unapproved date/path constants remain in active automation

### A1 — Scheduler-safe Proving Run

Goal:
- run the stabilized path under the repo `.venv` and stamp final evidence

Outputs:
- `exports/validation/owner_truth_release/2026-03-08/proving_run/proving_run_summary.json`
- `exports/validation/owner_truth_release/2026-03-08/proving_run/proving_run_transcript.md`
- `docs/OPS_ROLLOUT_EVIDENCE_OWNER_TRUTH_GREEN_STABILIZATION_2026-03-08.md`

Test strategy:
- no new unit tests; use `.venv` proving run plus required runtime gates

Acceptance:
- proving run is green, evidence cites exact commit(s), commands, outputs, and rollback

## Required runtime gates

- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_generate_owner_truth_exceptions.py tests/test_run_owner_truth_daily_contract.py tests/test_system_doctor_contract.py tests/test_smoke_test_owner_truth_daily.py tests/test_release_hygiene.py`
- `python3 scripts/check_release_hygiene.py --strict --project-root .`
- `./.venv/bin/python scripts/smoke_test_owner_truth_daily.py --as-of 2026-03-08 --strict`
- `./.venv/bin/python scripts/ops_status.py --project-root .`

## Stop-the-line conditions

- any failed gate
- any DB write without env gate + `--apply` + backup + before/after diff + rollback note
- any hidden dependency on manual artifacts
- any reopened WebUI scrape/source work
- any mixed-scope commit or work from a dirty baseline
