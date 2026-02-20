# PLAN_SINGLE_TRUTH_OPS_NEXT_V2_8_PROMOTION_OBSERVABILITY_WRITE_PILOT_2026-02-20

## Objective
Stabilize post-v2.7 promotion by making headless CI deterministic for strict validation, improve observability artifacts, and keep write-side gating fail-closed.

## Scope
- In scope:
  - deterministic headless fixture bootstrap (anchors + DB + strict-validation artifacts),
  - CI contract updates for fixture-backed strict checks,
  - import/runtime safety fix that unblocks collection-time failures,
  - promotion evidence docs for v2.8 rollout.
- Out of scope:
  - ads attribution rollout,
  - DB/apply write workflows,
  - unrelated failing suites in mainline business logic.

## Non-Negotiables
1. Tests-first + fail-first before behavior changes.
2. Fail-closed behavior only.
3. No write/apply DB flows added.
4. Preserve anchor authority in `config/anchors/README.md`.

## Primary Next Gate After Promotion
- `single_truth_headless` workflow must be runnable deterministically from clean checkout using fixture bootstrap.
- Evidence must include:
  - red targeted tests before fix,
  - green targeted tests after fix,
  - baseline + final gate attempts under `exports/validation/ops_rollout_v2_8_promotion_observability_write_pilot_<DATE>/`.

## Phases
### P0 Baseline
- Capture baseline gate failures and runtime context.

### P1 Tests-first contracts
- Add fail-first coverage for:
  - fixture bootstrap strict artifacts (`db/app.db`, dashboard payload, business-insides snapshot, dim-sku-light workbook),
  - CI workflow env/path contract for fixture-sourced dim-sku workbook,
  - import safety contract for `scripts/build_daily_waybills.py`.

### P2 Implementation
- Expand `scripts/prepare_ci_headless_fixture.py` to build strict-ready fixture stack.
- Update `.github/workflows/single_truth_headless.yml` to use fixture dim-sku workbook and verify `db/app.db` presence.
- Fix import-time runtime behavior in `scripts/build_daily_waybills.py`.
- Align stagecode fixture expectations in `scripts/run_contract_suite.py`.

### P3 Verification + Evidence
- Re-run targeted tests to green.
- Run full gate chain and classify outcomes (green vs blocked by pre-existing failures).
- Publish v2.8 rollout evidence doc with exact artifact paths and rollback.

## Rollback
1. `git revert <newest_commit> ... <oldest_commit>`
2. Re-run minimum:
   - `python3 scripts/validate_params.py --strict`
   - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_prepare_ci_headless_fixture.py tests/test_ci_headless_workflow_contract.py tests/test_build_daily_waybills_import_guard.py tests/test_contract_suite.py`
