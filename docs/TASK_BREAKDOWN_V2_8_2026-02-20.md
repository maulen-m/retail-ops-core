# TASK_BREAKDOWN_V2_8_2026-02-20

## Evidence Root
- `exports/validation/ops_rollout_v2_8_promotion_observability_write_pilot_2026-02-20/`

## P0 — Baseline
### Inputs
- Existing branch state after v2.7 promotion.

### Outputs
- `baseline_gates.md`
- `SESSION_JOURNAL.md`

### DoD
- Baseline command outputs captured with exit codes.

### Stop-the-line
- Any missing baseline artifact.

### Rollback
- N/A (read-only phase).

## P1 — Fail-first tests
### Files
- `tests/test_prepare_ci_headless_fixture.py`
- `tests/test_ci_headless_workflow_contract.py`
- `tests/test_build_daily_waybills_import_guard.py` (new)

### Expected RED checks
- Fixture missing strict artifacts.
- Workflow missing dim-sku fixture env + db assertion.
- Import of `scripts.build_daily_waybills` exits early.

### Evidence
- `targeted_tests_red.md`

### DoD
- Red evidence present with explicit failing assertions.

### Rollback
- Revert test-only commit.

## P2 — Implementation
### Files
- `scripts/prepare_ci_headless_fixture.py`
- `.github/workflows/single_truth_headless.yml`
- `scripts/build_daily_waybills.py`
- `scripts/run_contract_suite.py`

### Changes
- Fixture script now creates:
  - headless workbook fixtures under `config/anchors/fixtures/`,
  - `db/app.db` fixture with strict-required schema/data,
  - `exports/po_dashboard_data.json`,
  - business-insides snapshot pair for as-of date.
- Workflow consumes fixture dim-sku workbook path and asserts fixture DB presence.
- `build_daily_waybills` venv re-exec limited to CLI execution only (`__name__ == "__main__"` guard).
- Contract suite stagecode expected selection aligned with current stage filter behavior.

### DoD
- Targeted tests turn green.

### Evidence
- `targeted_tests_green.md`

### Rollback
- Revert implementation commit(s) and re-run targeted suite.

## P3 — Verification + Evidence
### Required checks
1. `python3 scripts/validate_params.py --strict`
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
3. `python3 scripts/run_contract_suite.py --fixture small`
4. `python3 scripts/validate_single_truth_system.py`
5. `scripts/lint_docs.sh`
6. `scripts/check_no_db_tracked.sh`
7. `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
8. `python3 scripts/check_anchor_health.py --project-root ~/Docs/Autonomous_business`
9. `python3 scripts/ops_status.py --project-root ~/Docs/Autonomous_business`

### Outputs
- `full_gates_green.md` (contains latest full run output; green or blocked classification)
- `docs/OPS_ROLLOUT_EVIDENCE_V2_8_EXECUTION_2026-02-20.md`

### DoD
- Evidence doc references exact artifacts and distinguishes:
  - verified green in this session,
  - blocked failures attributable to pre-existing suites outside v2.8 scope.

### Rollback
- `git revert <newest> ... <oldest>`
- Re-run minimum validation commands from plan.
