# TASK_BREAKDOWN_P0_P1_P2_P3_P4_P5_2026-02-20

## Context
Baseline plan: `docs/PLAN_SINGLE_TRUTH_OPS_NEXT_V2_7_RELEASE_CI_WRITE_SCALE_2026-02-20.md`

Evidence root:
- `exports/validation/ops_next_v2_7_release_ci_write_scale_2026-02-20/`

## Common End-of-Phase Gates (H1-H9)
1. `python3 scripts/validate_params.py --strict`
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
3. `python3 scripts/run_contract_suite.py --fixture small`
4. `python3 scripts/validate_single_truth_system.py`
5. `scripts/lint_docs.sh`
6. `scripts/check_no_db_tracked.sh`
7. `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
8. `python3 scripts/check_anchor_health.py --project-root ~/Docs/Autonomous_business`
9. `python3 scripts/ops_status.py --project-root ~/Docs/Autonomous_business`

---

## P0 — Baseline
### Files
- No code changes required.

### Tests / Gates
- Run H1-H9 and capture baseline.

### Artifacts
- `exports/validation/ops_next_v2_7_release_ci_write_scale_2026-02-20/baseline_gates.md`
- `exports/validation/ops_next_v2_7_release_ci_write_scale_2026-02-20/SESSION_JOURNAL.md`

### DoD
- All baseline gate exit codes recorded.

### Rollback
- None (read-only phase).

### Stop-the-line
- Any baseline gate non-zero.

---

## P1 — Observability default (drift pack status)
### Files to edit/create
- `scripts/build_single_truth_drift_pack.py`
- `tests/test_build_single_truth_drift_pack.py`

### Tests first (fail-first)
- `tests/test_build_single_truth_drift_pack.py::test_drift_pack_includes_status_classification`
- `tests/test_build_single_truth_drift_pack.py::test_classify_pack_status_prioritizes_stop_line_then_critical`

### Green verification
- Re-run full `tests/test_build_single_truth_drift_pack.py`

### Artifacts
- `exports/validation/ops_next_v2_7_release_ci_write_scale_2026-02-20/targeted_tests_red.md`
- `exports/validation/ops_next_v2_7_release_ci_write_scale_2026-02-20/targeted_tests_green.md`

### DoD
- Drift pack payload includes `status` + `status_reasons` deterministically.

### Rollback
- `git revert <p1_commit_sha>`

### Stop-the-line
- Missing status classification or non-deterministic drift output format.

---

## P2 — CI headless chain
### Files to edit/create
- `.github/workflows/single_truth_headless.yml`
- `scripts/prepare_ci_headless_fixture.py`
- `tests/test_prepare_ci_headless_fixture.py`
- `tests/test_ci_headless_workflow_contract.py`
- `docs/CI_HEADLESS_PLAN.md`

### Tests first (fail-first)
- `tests/test_prepare_ci_headless_fixture.py`
- `tests/test_ci_headless_workflow_contract.py`

### Green verification
- Re-run the two suites above.

### Artifacts
- `exports/validation/ops_next_v2_7_release_ci_write_scale_2026-02-20/targeted_tests_red_phase_misc.md`
- `exports/validation/ops_next_v2_7_release_ci_write_scale_2026-02-20/targeted_tests_green.md`

### DoD
- Workflow file contains all required commands from `docs/CI_HEADLESS_PLAN.md`.
- Fixture script creates valid workbook anchors for headless checks.

### Rollback
- `git revert <p2_commit_sha>`

### Stop-the-line
- Missing required gate command from headless workflow.
- Fixture script mutates DB or external systems.

---

## P3 — Write-side gating scale
### Files to edit/create
- `config/write_side_gating_manifest.yaml`
- `scripts/validate_write_side_gating.py`
- `scripts/validate_params.py`
- `tests/test_write_side_gating_contract.py`
- `tests/test_validate_write_side_gating.py`
- `docs/WRITE_SIDE_GATING_CONTRACT.md`
- `docs/WRITE_APPLY_RUNBOOK.md`

### Tests first (fail-first)
- `tests/test_write_side_gating_contract.py`
- `tests/test_validate_write_side_gating.py`

### Green verification
- Re-run above tests.
- `python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml`

### Artifacts
- `exports/validation/ops_next_v2_7_release_ci_write_scale_2026-02-20/targeted_tests_green.md`

### DoD
- Manifest validator enforces env+apply token presence per listed write script.
- `validate_params --strict` reports gating contract status.

### Rollback
- `git revert <p3_commit_sha>`

### Stop-the-line
- Any manifest entry points to missing script.
- Any listed write script missing env or `--apply` token.

---

## P4 — Docs convergence and authority chain
### Files to edit/create
- `docs/PLAN_SINGLE_TRUTH_OPS_NEXT_V2_7_RELEASE_CI_WRITE_SCALE_2026-02-20.md`
- `docs/00_START_HERE.md`
- `docs/DAILY_SOP.md`
- `tests/test_ops_docs_anchor_contract.py`

### Tests first (fail-first)
- `tests/test_ops_docs_anchor_contract.py::test_ops_next_v27_plan_has_no_oracle_listing_artifact_tokens`

### Green verification
- Re-run `tests/test_ops_docs_anchor_contract.py`
- `scripts/lint_docs.sh`

### Artifacts
- `exports/validation/ops_next_v2_7_release_ci_write_scale_2026-02-20/targeted_tests_green.md`

### DoD
- No artifact-contaminated content in active v2.7 plan.
- Anchor authority and write-side authority links are explicit.

### Rollback
- `git revert <p4_commit_sha>`

### Stop-the-line
- Any active docs include banned absolute path or stale clone path.

---

## P5 — Final gates + evidence + journal
### Files to edit/create
- `docs/OPS_ROLLOUT_EVIDENCE_V2_5_1_INTEGRATION_2026-02-20.md`
- `claude/journal.md`

### Validation
- Run H1-H9.

### Artifacts
- `exports/validation/ops_next_v2_7_release_ci_write_scale_2026-02-20/full_gates_green.md`

### DoD
- All H1-H9 commands are green and logged.
- Journal has timestamped command + output summaries and links to evidence artifacts.

### Rollback
1. Code:
   - `git revert <newest_commit> ... <oldest_commit>`
2. Runtime scheduler (if plist behavior rollback required):
   - `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.example.single-truth-preflight.plist || true`
   - `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.example.on-delivery-residuals.plist || true`
   - `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.example.anchor-health-warning.plist || true`

### Stop-the-line
- Any H1-H9 command non-zero.
- Missing evidence artifacts for reported PASS claims.

---

## Likely Integration Conflicts + Sequencing
### Conflicts
1. `docs/PLAN_SINGLE_TRUTH_OPS_NEXT...` was artifact-contaminated and untracked.
2. Existing `gates.yml` may diverge from the new headless workflow contract.
3. Write-side scripts list can drift quickly and invalidate static tests.

### Single-worktree safe sequence
1. Apply P1 + P2 tests first and capture RED.
2. Implement scripts/workflow for P1/P2 and get targeted GREEN.
3. Apply P3 manifest/validator and strict-chain wiring.
4. Apply P4 docs cleanup + authority links.
5. Run P5 full H1-H9 and publish evidence.
