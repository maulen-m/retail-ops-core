# TASK_BREAKDOWN_V2_9_PYTEST_GREEN_AND_PROMOTION_2026-02-20

## A) Promotion Gate Checklist for PR #3
Target PR branch: `codex/TASK-ops-rollout-v2-8-promotion-observability-write-pilot`

## Local gates (must be green before merge)
1. `python3 scripts/validate_params.py --strict`
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
3. `python3 scripts/run_contract_suite.py --fixture small`
4. `python3 scripts/validate_single_truth_system.py`
5. `scripts/lint_docs.sh`
6. `scripts/check_no_db_tracked.sh`
7. `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
8. `python3 scripts/check_anchor_health.py --project-root ~/Docs/Autonomous_business`
9. `python3 scripts/ops_status.py --project-root ~/Docs/Autonomous_business`

## Headless CI gates (must be green on PR and merge commit)
- Workflow: `.github/workflows/single_truth_headless.yml`
- Required job chain must include:
  - strict validation,
  - full pytest,
  - contract suite,
  - single-truth validator,
  - docs lint,
  - no-db-tracked check,
  - scheduler validate-only,
  - anchor-health,
  - ops-status.

## Evidence required before merge
- PR link
- commit SHA list included in merge
- log artifact paths for each gate
- explicit rollback command set

## B) Likely Failing Areas (from v2.7/v2.8 surfaces)
1. CI fixture parity drift
- Missing generated fixture artifacts (`db/app.db`, business-insides snapshot, anchor symlinks) causes headless strict failures.

2. Waybill/ship runtime semantics
- assemble API returns success but order remains unassembled; false shipped counts lead to waybill URL missing.

3. Workbook anchor resolution/freshness
- symlink valid but content stale, or path resolution differs between local and CI.

4. Import-time side effects
- script imports executing env/runtime logic during pytest collection can fail before tests run.

5. Write gating semantic bypass
- manifest token exists, but script path may still write with only one condition (env or `--apply`) satisfied.

6. CI workflow drift from required gate chain
- workflow changes over time may omit one strict check or artifact upload.

## C) Bucketed Task Map (execution-ready)

## Bucket B1 — CI Fixture Contract
### Inputs
- `scripts/prepare_ci_headless_fixture.py`
- `.github/workflows/single_truth_headless.yml`
- `tests/test_prepare_ci_headless_fixture.py`
- `tests/test_ci_headless_workflow_contract.py`

### Proposed tests to add/strengthen
- `tests/test_prepare_ci_headless_fixture.py::test_fixture_creates_required_strict_artifacts`
- `tests/test_prepare_ci_headless_fixture.py::test_fixture_creates_anchor_symlinks`
- `tests/test_ci_headless_workflow_contract.py::test_ci_uses_fixture_dim_sku_workbook_path`
- `tests/test_ci_headless_workflow_contract.py::test_ci_runs_required_gate_chain`

### Correct-fix shape
- Fixture script builds all required files deterministically.
- CI consumes fixture outputs through explicit env vars and fails if missing.

### Acceptance tests
- Targeted fixture/workflow tests red then green.
- Headless CI run reproduces local strict behavior on same commit.

## Bucket B2 — Waybill + Ship Runtime
### Inputs
- `scripts/ship_orders_api.py`
- `scripts/download_waybills_api.py`
- `core/integrations/kaspi_api_client.py`
- `tests/test_ship_orders_api.py`
- `tests/test_waybill_cli_runtime_compat.py`
- `tests/test_waybill_selection_filters.py`

### Proposed tests to add/strengthen
- `tests/test_ship_orders_api.py::test_ship_orders_requires_confirmed_assemble_before_count`
- `tests/test_ship_orders_api.py::test_ship_orders_refresh_path_marks_unconfirmed_as_error`
- `tests/test_waybill_selection_filters.py::test_waybill_selection_does_not_mark_api_only_when_all_urls_missing`
- `tests/test_waybill_cli_runtime_compat.py::test_store_aliases_supported_for_waybill_and_ship`

### Correct-fix shape
- Ship flow only increments shipped count after assembled/waybill confirmation.
- Unconfirmed orders remain retry/error and are surfaced in summary.
- Waybill stage explicitly reflects whether data is API-only, fallback, or partial.

### Acceptance tests
- Targeted waybill/ship tests red then green.
- Dry-run smoke command shows no false “shipped OK” on unconfirmed orders.

## Bucket B3 — Anchor/Workbook Resolution
### Inputs
- `scripts/check_anchor_health.py`
- `scripts/run_strict_daily_preflight.py`
- `config/anchors/README.md`
- `docs/DAILY_SOP.md`
- `tests/test_check_anchor_health.py`
- `tests/test_run_strict_daily_preflight.py`

### Proposed tests to add/strengthen
- `tests/test_check_anchor_health.py::test_fails_when_symlink_target_missing`
- `tests/test_check_anchor_health.py::test_fails_when_content_lag_exceeds_threshold`
- `tests/test_run_strict_daily_preflight.py::test_passes_workbook_env_to_validate_params`
- `tests/test_run_strict_daily_preflight.py::test_fails_on_future_mtime_skew`

### Correct-fix shape
- Anchor script checks symlink validity + file freshness + content lag and exits non-zero on violation.
- Preflight passes workbook env deterministically to strict validation subprocess.

### Acceptance tests
- Targeted anchor/preflight tests red then green.
- `check_anchor_health.py` green only on healthy anchors.

## Bucket B4 — Write-Gating Semantic Enforcement
### Inputs
- `config/write_side_gating_manifest.yaml`
- `scripts/validate_write_side_gating.py`
- `tests/test_write_side_gating_contract.py`
- `tests/test_validate_write_side_gating.py`

### Proposed tests to add/strengthen
- `tests/test_validate_write_side_gating.py::test_fails_when_manifest_has_missing_apply_flag_contract`
- `tests/test_validate_write_side_gating.py::test_fails_when_env_gate_not_enforced_in_script`
- `tests/test_write_side_gating_contract.py::test_default_mode_is_non_mutating`
- `tests/test_write_side_gating_contract.py::test_requires_env_and_apply_together`

### Correct-fix shape
- Validator enforces both syntax and semantics (env gate + `--apply` + ordering before write).
- Manifest coverage is complete for declared write scripts.

### Acceptance tests
- Targeted write-gating tests red then green.
- `validate_params --strict` fails if any write script drifts from contract.

## Bucket B5 — Docs Authority + CI Drift Guard
### Inputs
- `docs/00_START_HERE.md`
- `docs/DAILY_SOP.md`
- `docs/CI_HEADLESS_PLAN.md`
- `docs/WRITE_SIDE_GATING_CONTRACT.md`
- docs contract tests

### Proposed tests to add/strengthen
- `tests/test_docs_authority_contract.py::test_daily_sop_points_to_anchor_readme`
- `tests/test_docs_authority_contract.py::test_ci_headless_plan_matches_required_job_chain`

### Correct-fix shape
- One authoritative path chain for anchors and ops commands.
- Docs and workflow contract remain synchronized.

### Acceptance tests
- docs contract tests red then green.
- `scripts/lint_docs.sh` green.

## D) Sequential Execution Order (single-worktree, low conflict)
1. B1 fixture contract
2. B2 waybill/ship runtime
3. B3 anchor resolution
4. B4 write-gating semantics
5. B5 docs authority sync
6. Full local gate chain
7. Headless CI run + evidence capture
8. Promotion merge + post-merge gate replay

## E) Rollback Strategy by Bucket
- Revert bucket commit(s) in reverse order.
- Re-run minimum guard gates after each rollback:
  - `python3 scripts/validate_params.py --strict`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
  - `scripts/lint_docs.sh`

## F) Stop-the-Line Criteria
- Any bucket introduces fail-open behavior for write-side paths.
- Local green cannot be reproduced in headless CI for same SHA.
- Evidence artifacts missing for claimed gate pass.
- Any fix depends on DB apply/write action not covered by gated tests.
