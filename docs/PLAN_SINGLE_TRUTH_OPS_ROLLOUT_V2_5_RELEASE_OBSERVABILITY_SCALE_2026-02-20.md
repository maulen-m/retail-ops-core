# PLAN_SINGLE_TRUTH_OPS_ROLLOUT_V2_5_RELEASE_OBSERVABILITY_SCALE_2026-02-20

## Purpose
Lock the v2.1→v2.4 “fail-closed ops reliability” work into a single release-candidate execution envelope,
then extend it with higher-leverage observability + scale-readiness phases (without reintroducing false-green risk).
This plan is optimized for: single-agent execution, deterministic gates, and near-zero human time
(human only does logins/secrets + workbook refresh).

## Baseline (already shipped; do not re-implement)
Most recent shipped tranche is v2.4 “Anchor Content Freshness”:
- Commits (provided): 630f33d, b71f52b, 014df65, f9cb293
- Key behavior:
  - Anchor health checks include content-date freshness + future content-date fail-closed guard.
  - Deterministic ops_status command exists for operator go/no-go.
  - Anchor-health warning job uses spam guard state file + repeat interval.
  - Anchor-path authority is centralized in config/anchors/README.md.
  - No DB write/apply behavior in the rollout.

Earlier shipped foundations include:
- v2.1 “Critical5” and v2.3.1 stop-line clearing: .venv runtime pinning, workbook freshness gates, validate-only installer, docs lint bans.

## Locked decisions
- Reliability posture: FAIL-CLOSED.
- DB writes: forbidden unless explicitly gated (ENV var + --apply + backup) and called out in the phase.
- Execution model: single worktree/branch sequential execution is the default.
- Evidence: every phase writes an append-only session journal and produces red->green evidence for new tests.

## Global Gates (must stay green)
### Canonical hard gate chain (non-negotiable)
- python3 scripts/validate_params.py --strict
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
- python3 scripts/run_contract_suite.py --fixture small
- python3 scripts/validate_single_truth_system.py
- scripts/lint_docs.sh
- scripts/check_no_db_tracked.sh

### Ops stop-line checks (must pass; cwd-independent)
- bash scripts/install_single_truth_ops_scheduler.sh --validate-only
- python3 scripts/check_anchor_health.py --project-root <REPO_PATH>
- python3 scripts/ops_status.py --project-root <REPO_PATH>
- Re-run at least once from /tmp (cwd-independence enforcement)

## Phase P0 — Triage + Release Baseline Capture
Goal (measurable):
- Establish a clean baseline snapshot of gates and ops stop-line checks that is reproducible from repo root and /tmp.

Inputs:
- Repo at <REPO_PATH>
- Existing v2.4 evidence folders + plan docs
- Anchor authority file: config/anchors/README.md

Outputs (artifacts):
- exports/validation/ops_rollout_v2_5_rc_<YYYY-MM-DD>/
  - SESSION_JOURNAL.md (append-only, timestamped)
  - baseline_gates.md
  - baseline_stopline_checks.md (validate-only + anchor health + ops_status)
  - cwd_independence.md (/tmp rerun evidence)

Definition of Done:
- All global gates PASS and recorded.
- Stop-line checks PASS from repo root and /tmp.
- No repo dirt introduced (except explicit phase outputs).

Validation/Gates:
- Global gates + stop-line checks.
- Doc lint contract (banned paths/tokens) passes.

Rollback/backout:
- No code changes required in P0; if baseline fails, STOP and do not proceed.

Stop-the-line:
- Any gate fails or differs between repo root and /tmp.
- ops_status exit code non-zero.

## Phase P1 — Release Consolidation (v2.1→v2.4)
Goal (measurable):
- Produce one “Ops RC” branch that contains exactly the intended ops reliability chain:
  - runtime determinism (launchd + validate-only)
  - anchor authority + health checks (mtime + content date + future content-date guard)
  - deterministic operator status surface
  - alert spam guard
  - docs/tests preventing regression

Inputs:
- v2.1/v2.2/v2.3/v2.3.1/v2.4 commits and docs in repo
- Oracle listings (if used for external review)

Outputs:
- docs/OPS_ROLLOUT_EVIDENCE_V2_5_<YYYY-MM-DD>.md (links to evidence artifacts)
- (optional) updated Oracle pack listing section if new files are introduced

Definition of Done:
- No duplicate/conflicting runbooks; docs/00_START_HERE.md points to docs/DAILY_SOP.md; anchor authority remains config/anchors/README.md.
- All gates PASS.

Validation/Gates:
- Global gates + stop-line checks.
- Ensure banned-token lint catches legacy absolute path regressions.

Rollback/backout:
- git revert v2.5-only commits.
- Re-run installer validate-only from reverted state.

Stop-the-line:
- Any regression that makes validate-only pass while launchd runtime would fail (import mismatch risk).
- Any docs path drift that reintroduces non-canonical anchor sources.

## Phase P2 — Correctness & Hardening Extensions (silent failure focus)
Goal:
- Increase detection of silent failure modes:
  - workbook parsing changes
  - unexpected future-dated content
  - anchor symlink broken-but-existing
  - state file not writable under launchd

Inputs:
- scripts/check_anchor_health.py
- scripts/run_anchor_health_alert.py
- tests/ suite

Outputs:
- New/extended tests (fail-first then green)
- exports/validation/ops_rollout_v2_5_hardening_<YYYY-MM-DD>/
  - targeted_tests_red.md
  - targeted_tests_green.md
  - full_gates_green.md

Definition of Done:
- Tests reproduce the failure mode first (red), then pass after fix (green).
- Fail-closed behavior: parsing/import errors must surface as non-zero and clear ERROR lines.

Validation/Gates:
- Global gates + stop-line checks.
- Run the relevant tests from /tmp to validate import-path robustness.

Rollback/backout:
- git revert new tests + code changes.

Stop-the-line:
- Any change that turns a previously fail-closed path into warn-only or best-effort.

## Phase P3 — Observability Pack + Alert Policy (design + implementation later)
Goal:
- Define and implement a daily “decision-grade ops pack” that makes drift visible without manual digging.

Inputs:
- ops_status output
- anchor health output
- existing exports/validation patterns

Outputs:
- docs/PLAN_SINGLE_TRUTH_OPS_ROLLOUT_V2_6_OBSERVABILITY_<DATE>.md (spec)
- (implementation) scripts/build_ops_drift_pack.py and tests (if chosen)
- exports/validation/daily/<YYYY-MM-DD>/ops_pack.md + ops_pack.json

Definition of Done:
- A single artifact answers: “is ops safe to run today?” + “what drift exists?”.
- Alert policy is explicit (warn vs critical vs stop-line).

Validation/Gates:
- Determinism tests: same inputs produce stable outputs (sorted, normalized).
- Stop-line: drift pack generation must not write to DB.

Rollback/backout:
- revert drift pack additions; keep ops_status/anchor health intact.

Stop-the-line:
- Any alert spam regression (repeat alerts within cooldown without recovery).
- Any DB write without explicit env gate.

## Phase P4 — Automation Safety Layer (write gating)
Goal:
- Ensure any script that can mutate DB or external systems is gated by explicit env + explicit flag.

Inputs:
- scripts/ that support write modes
- existing patterns (ENABLE_* + --apply)

Outputs:
- A “write gating contract” doc + tests:
  - docs/WRITE_SIDE_GATING_CONTRACT.md
  - tests/test_write_side_gating_contract.py

Definition of Done:
- Default execution is dry-run; writes require explicit opt-in and are test-covered.

Validation/Gates:
- Grep-based and runtime checks in tests (no accidental writes).

Rollback/backout:
- revert gating changes.

Stop-the-line:
- Any uncovered write path discovered.

## Phase P5 — Scale Readiness (CI/headless + multi-machine)
Goal:
- Make the ops gates runnable in a clean, headless environment without local absolute paths.

Inputs:
- docs lint + contracts
- anchor authority file

Outputs:
- CI plan doc (even if CI isn’t set up yet):
  - docs/CI_HEADLESS_PLAN.md
- Extended lint rules banning user-specific absolute paths in active docs (except config/anchors/README.md where explicitly required).

Definition of Done:
- Full gate chain runs in a clean environment with fixtures, not machine-local anchors.

Validation/Gates:
- /tmp run + isolated venv run.
- No references to deprecated clone-path tokens and other banned legacy patterns.

Rollback/backout:
- revert CI/lint changes only.

Stop-the-line:
- Any reliance on machine-local symlinks in tests (tests must use fixtures).

## If attachments are missing (assumptions policy)
- Treat repo state as source-of-truth.
- Mark every assumption in the session journal.
- Add a gate that would falsify the assumption (e.g., a contract test, a lint rule, or a cwd-independence run).
- Prefer failing closed over guessing.
