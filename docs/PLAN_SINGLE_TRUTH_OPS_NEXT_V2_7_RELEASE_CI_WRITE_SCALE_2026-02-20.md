# PLAN_SINGLE_TRUTH_OPS_NEXT_V2_7_RELEASE_CI_WRITE_SCALE_2026-02-20

## Objective
Lock v2.5 as production baseline, make v2.6 observability default, run the full headless gate chain in CI, and scale write-side safety with manifest-driven enforcement.

## Scope
- In scope: docs/contracts, read-only observability artifacts, CI/headless reliability, write-side gating enforcement.
- Out of scope: ads attribution implementation, write/apply DB operations.
- Anchor path/symlink authority for this plan is `config/anchors/README.md`.

## Global Non-Negotiables
1. Tests-first and fail-first evidence before each behavior change.
2. Fail-closed only; no warn-only downgrade for stop-line checks.
3. No DB writes unless explicit env gate + `--apply` (not used in this plan).
4. Keep active docs free from machine-local absolute paths.

## Gate Chain (must be green)
1. `python3 scripts/validate_params.py --strict`
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
3. `python3 scripts/run_contract_suite.py --fixture small`
4. `python3 scripts/validate_single_truth_system.py`
5. `scripts/lint_docs.sh`
6. `scripts/check_no_db_tracked.sh`
7. `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
8. `python3 scripts/check_anchor_health.py --project-root <repo>`
9. `python3 scripts/ops_status.py --project-root <repo>`

## Phase P0 — Baseline + Integration Evidence
### Deliverables
- `exports/validation/ops_next_v2_7_release_ci_write_scale_<DATE>/baseline_gates.md`
- `exports/validation/ops_next_v2_7_release_ci_write_scale_<DATE>/SESSION_JOURNAL.md`

### Definition of Done
- Gate chain is executed and results are recorded with exit codes.

### Rollback
- No code rollback required for baseline-only phase.

## Phase P1 — Observability Default (v2.6)
### Deliverables
- Drift pack includes deterministic status (`PASS/WARN/CRITICAL/STOP_LINE`) and reason list.
- Tests proving classification behavior and deterministic payload shape.

### Definition of Done
- `scripts/build_single_truth_drift_pack.py` is read-only and includes explicit status computation.
- Tests fail-first then pass.

### Rollback
- Revert drift-pack status commit.

## Phase P2 — Headless CI Gate Chain
### Deliverables
- `.github/workflows/single_truth_headless.yml`
- `scripts/prepare_ci_headless_fixture.py` (anchors + workbook fixtures, read-only)
- Contract tests for workflow commands and fixture bootstrap.

### Definition of Done
- Workflow mirrors gate-chain commands in this plan.
- Headless fixture script creates deterministic workbook anchors.

### Rollback
- Revert workflow + fixture script commit.

## Phase P3 — Write-Side Gating Scale
### Deliverables
- `config/write_side_gating_manifest.yaml`
- `scripts/validate_write_side_gating.py`
- Strict-chain wiring in `scripts/validate_params.py`
- Contract/runbook updates.

### Definition of Done
- Manifest validator fails on missing env/apply tokens.
- Strict validation fails when manifest contract is broken.

### Rollback
- Revert manifest + validator + strict wiring commit.

## Phase P4 — Docs + Operator Path
### Deliverables
- `docs/WRITE_APPLY_RUNBOOK.md`
- Updated `docs/DAILY_SOP.md` and `docs/00_START_HERE.md`
- Clean v2.7 plan text without artifact contamination.

### Definition of Done
- Active docs point to anchor authority and write-side contract authority.

### Rollback
- Revert docs-only commit.

## Phase P5 — Final Verification + Evidence
### Deliverables
- `exports/validation/ops_next_v2_7_release_ci_write_scale_<DATE>/targeted_tests_red.md`
- `exports/validation/ops_next_v2_7_release_ci_write_scale_<DATE>/targeted_tests_green.md`
- `exports/validation/ops_next_v2_7_release_ci_write_scale_<DATE>/full_gates_green.md`
- `docs/OPS_ROLLOUT_EVIDENCE_V2_5_1_INTEGRATION_<DATE>.md`

### Definition of Done
- All gate commands are green.
- Evidence files exist and are linked in journal.

### Rollback
- `git revert <newest_commit> ... <oldest_commit>`
- Re-run minimum checks:
  - `python3 scripts/validate_params.py --strict`
  - `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`

## Stop-the-Line Criteria
- Any gate returns non-zero.
- Any regression from fail-closed behavior.
- Any docs/path contract violation in active docs.
- Any unguarded write path detected by manifest validator.
