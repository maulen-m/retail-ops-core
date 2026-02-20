# PLAN_SINGLE_TRUTH_OPS_NEXT_V2_9_PROMOTION_GLOBAL_GREEN_WRITE_PILOT_2026-02-20

## 0) Objective
Promote the v2.8 branch only after deterministic global-green evidence is achieved across local gates and headless CI, then run a write-side pilot in fail-closed mode without executing any live apply/write actions in this planning scope.

## 1) Scope and Constraints
- Scope: planning + execution map for phases `P0..P5`.
- This plan itself performs no DB/apply writes.
- Any future write-side execution must require both env gate and `--apply` and be covered by tests.
- Ads integration is out of scope in this sequence.

## 2) Pytest Bucket Strategy (triage-first, max 5 buckets)
Use these buckets during implementation so failures are isolated and reversible:

1. `B1_CI_FIXTURE_CONTRACT`
- Focus: fixture bootstrap parity with headless CI.
- Typical files: `scripts/prepare_ci_headless_fixture.py`, `.github/workflows/single_truth_headless.yml`, `tests/test_prepare_ci_headless_fixture.py`, `tests/test_ci_headless_workflow_contract.py`.

2. `B2_WAYBILL_SHIP_RUNTIME`
- Focus: assemble/waybill runtime correctness and no false-green shipping counts.
- Typical files: `scripts/ship_orders_api.py`, `scripts/download_waybills_api.py`, `core/integrations/kaspi_api_client.py`, `tests/test_ship_orders_api.py`, `tests/test_waybill_cli_runtime_compat.py`, `tests/test_waybill_selection_filters.py`.

3. `B3_ANCHOR_WORKBOOK_RESOLUTION`
- Focus: anchor path/freshness/content checks used in strict preflight.
- Typical files: `scripts/check_anchor_health.py`, `scripts/run_strict_daily_preflight.py`, `tests/test_check_anchor_health.py`, `tests/test_run_strict_daily_preflight.py`.

4. `B4_WRITE_GATING_MANIFEST_ENFORCEMENT`
- Focus: manifest coverage and semantic gating integrity.
- Typical files: `config/write_side_gating_manifest.yaml`, `scripts/validate_write_side_gating.py`, `tests/test_write_side_gating_contract.py`, `tests/test_validate_write_side_gating.py`.

## 3) Phase Plan

## P0 — Promotion Readiness Snapshot
### Goal
Create a deterministic readiness snapshot for PR #3 (`codex/TASK-ops-rollout-v2-8-promotion-observability-write-pilot`) with explicit PASS/FAIL state per required gate.

### Inputs
- Branch head under promotion.
- `docs/CI_HEADLESS_PLAN.md`
- Existing evidence docs:
  - `docs/OPS_ROLLOUT_EVIDENCE_V2_7_INTEGRATION_2026-02-20.md`
  - `docs/OPS_ROLLOUT_EVIDENCE_V2_8_EXECUTION_2026-02-20.md`

### Outputs (exact paths)
- `exports/validation/ops_rollout_v2_9_p0_readiness_<YYYY-MM-DD>/baseline_gates.md`
- `exports/validation/ops_rollout_v2_9_p0_readiness_<YYYY-MM-DD>/headless_ci_status.md`
- `exports/validation/ops_rollout_v2_9_p0_readiness_<YYYY-MM-DD>/failure_inventory.md`
- `docs/OPS_ROLLOUT_EVIDENCE_V2_9_PROMOTION_READINESS_<YYYY-MM-DD>.md`

### DoD
- Every required gate is labeled PASS/FAIL with log path.
- Local vs CI differences are explicitly explained or flagged stop-line.

### Validation/Gates
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_single_truth_system.py`
- `scripts/lint_docs.sh`
- `scripts/check_no_db_tracked.sh`
- Headless CI workflow `single_truth_headless` status captured.

### Rollback
- Docs-only rollback: `git revert <p0_commit_sha>`.

### Stop-the-line
- Same commit shows contradictory local PASS and CI FAIL without root-cause evidence.
- Missing logs for any reported gate outcome.

## P1 — Global Pytest Green Repair Map
### Goal
Make pytest deterministic and green using bucketed fixes, without loosening assertions or turning failures into silent skips.

### Inputs
- `P0` failure inventory.
- Bucket strategy (B1..B4).

### Outputs (exact paths)
- `docs/TASK_BREAKDOWN_V2_9_PYTEST_GREEN_AND_PROMOTION_2026-02-20.md`
- `exports/validation/ops_rollout_v2_9_p1_pytest_green_<YYYY-MM-DD>/bucket_plan.md`
- `exports/validation/ops_rollout_v2_9_p1_pytest_green_<YYYY-MM-DD>/targeted_red_green_matrix.md`

### DoD
- Each failing test mapped to one bucket and one owner commit.
- Proposed fix order minimizes merge conflicts and cross-bucket coupling.

### Validation/Gates
- Targeted bucket tests (red then green, per bucket).
- Re-run full pytest after all buckets:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`

### Rollback
- Revert per-bucket commit(s) independently.

### Stop-the-line
- A fix introduces a skip/xfail without explicit rationale and approval note.
- A bucket change modifies write behavior outside gate contract.

## P2 — Headless CI Contract Lock
### Goal
Ensure CI required job chain mirrors local promotion gates and yields reproducible artifacts for every failure.

### Inputs
- `.github/workflows/single_truth_headless.yml`
- `scripts/prepare_ci_headless_fixture.py`
- `docs/CI_HEADLESS_PLAN.md`

### Outputs (exact paths)
- `exports/validation/ops_rollout_v2_9_p2_ci_contract_<YYYY-MM-DD>/ci_contract_diff.md`
- `exports/validation/ops_rollout_v2_9_p2_ci_contract_<YYYY-MM-DD>/ci_artifact_manifest.md`
- Updated `docs/CI_HEADLESS_PLAN.md` if gate chain or artifact paths change.

### DoD
- CI job sequence includes all required jobs from `docs/CI_HEADLESS_PLAN.md`.
- CI uploads enough logs to replay failing commands locally.
- Two consecutive green CI runs on same head SHA are recorded.

### Validation/Gates
- Workflow validation via PR checks.
- Local parity recheck with required gate chain.

### Rollback
- `git revert <ci_workflow_commit_sha>`

### Stop-the-line
- CI omits a required strict gate job.
- CI passes while local equivalent command fails on same commit and fixture.

## P3 — Promotion / Merge Safety
### Goal
Promote PR #3 into production branch only with full evidence and explicit rollback path.

### Inputs
- Green results from P0-P2.
- PR metadata (link, commit set).

### Outputs (exact paths)
- `docs/OPS_ROLLOUT_EVIDENCE_V2_9_PROMOTION_INTEGRATION_<YYYY-MM-DD>.md`
- `exports/validation/ops_rollout_v2_9_p3_promotion_<YYYY-MM-DD>/post_merge_gates.md`

### DoD
- Evidence doc records PR link, merged commit SHA(s), and gate results with log paths.
- Post-merge required gates are green on target branch.

### Validation/Gates
- Same required gate chain as P0 on merge commit.
- Headless CI green on merge commit.

### Rollback
- Revert merge commit, or revert listed promotion commits in reverse order.

### Stop-the-line
- Any post-merge required gate fails.
- Evidence doc missing rollback instructions.

## P4 — Write-Side Pilot (Fail-Closed Proof)
### Goal
Validate one representative write-capable flow is impossible to execute in apply mode unless env+CLI+manifest contract is satisfied.

### Inputs
- `config/write_side_gating_manifest.yaml`
- `scripts/validate_write_side_gating.py`
- chosen pilot script (single script only)

### Outputs (exact paths)
- `docs/WRITE_PILOT_V1_<YYYY-MM-DD>.md`
- `exports/validation/ops_rollout_v2_9_p4_write_pilot_<YYYY-MM-DD>/write_guard_matrix.md`
- tests in gating suites documenting blocked/unblocked semantics.

### DoD
- Test evidence proves default mode cannot write.
- Missing env gate OR missing `--apply` OR missing manifest rule always exits non-zero.
- No live apply executed in pilot validation sequence.

### Validation/Gates
- `python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_write_side_gating_contract.py tests/test_validate_write_side_gating.py`
- `python3 scripts/validate_params.py --strict`

### Rollback
- Revert pilot-specific commits.

### Stop-the-line
- Any path demonstrates write-side effect in default mode.
- Manifest token exists but semantic enforcement missing in script logic.

## P5 — Observability Scale + Daily Drift Pack Promotion Policy
### Goal
Standardize daily observability output and promotion evidence requirements so operators can diagnose drift quickly and promotions remain auditable.

### Inputs
- `scripts/build_single_truth_drift_pack.py`
- `scripts/ops_status.py`
- `docs/DAILY_SOP.md`
- `docs/OPS_ROLLOUT_EVIDENCE_V2_9_PROMOTION_POLICY_2026-02-20.md`

### Outputs (exact paths)
- `exports/validation/daily/<YYYY-MM-DD>/drift_pack/` (run artifact target)
- `docs/OPS_ROLLOUT_EVIDENCE_V2_9_PROMOTION_POLICY_2026-02-20.md`
- SOP section updates pointing to evidence policy and artifact locations.

### DoD
- Promotion evidence policy is explicit and reusable.
- Daily drift pack output location and interpretation rules are documented.

### Validation/Gates
- `scripts/lint_docs.sh`
- docs contract tests (if added for authority chain).

### Rollback
- Revert policy/SOP doc commits.

### Stop-the-line
- Evidence template allows reporting green without log paths.
- Drift pack statuses not tied to actionable next step.

## 4) Global Fail-Closed Rules for Implementation Run
- Never downgrade stop-line checks to warnings to force green.
- No write/apply execution without explicit env gate + `--apply` + pre-tested path.
- Every ambiguous behavior must become an explicit assumption with a detection test.

## 5) Global Rollback Skeleton (implementation run)
1. Revert newest-to-oldest commits for affected phase only.
2. Re-run minimum safety gates:
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `scripts/lint_docs.sh`
3. If promotion already merged: revert merge commit and re-run headless CI.
