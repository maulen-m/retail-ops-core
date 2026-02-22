# PLAN_2_WEEK_EXECUTION_BOARD_A_C_B_V5_PROD_WRITE_SCALE_2026-02-22

## Purpose
Execute the next board with fail-closed production reliability, promotion-grade evidence, and write-side safety. Preserve workflow reliability for:
- `excel_ui/run_full_import.command`
- `excel_ui/run_build_waybills.command`

## Canonical References
- `docs/PLAN_2_WEEK_EXECUTION_BOARD_A_C_B_V4_CAPITAL_SCALE_2026-02-21.md`
- `docs/OPS_ROLLOUT_EVIDENCE_TASK_395_BOARD_V4_PROMOTION_2026-02-21.md`
- `config/anchors/README.md`
- `docs/marketing/ADS_SIDECAR_OPS_RUNBOOK.md`
- `docs/ops/STOCK_SNAPSHOT_RUNBOOK.md`
- `docs/ops/WRITE_CANARY_PLAN_V1.md`
- `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`

## Global Constraints
- Fail-closed only; no warn-only downgrade for stop-line checks.
- No DB/network apply writes in this board.
- Write paths remain gated by env + explicit `--apply`.
- Tests-first for every behavior change (RED -> GREEN evidence required).
- Evidence artifacts required per phase under `exports/validation/board_v5_2026-02-22/<PHASE_ID>/`.

## Phase Order
- `V5-T0_PLAN_AUTHORITY`
- `V5-C1_PROD_DRY_RUN`
- `V5-H1_API_STATE_TRANSITION`
- `V5-O1_DRIFT_PACK_SLOS`
- `V5-A1_WRITE_CANARY_READINESS`
- `V5-S1_MULTI_STORE_SCALE`

---

## V5-T0_PLAN_AUTHORITY
### Goal
Establish V5 as the active authoritative plan and lock references.

### Inputs
- V4 plan and V4 promotion evidence

### Outputs
- This V5 plan doc
- V5 evidence skeleton doc

### Definition of Done
1. V5 phases, gates, rollback, and stop-line criteria are explicit.
2. References use repo-relative paths/placeholders only.
3. Docs lint is green.

### Validation / Gates
- `bash scripts/lint_docs.sh`

### Rollback
- `git revert <v5-doc-commit>`

### Stop-line
- Missing or contradictory source authority.

---

## V5-C1_PROD_DRY_RUN
### Goal
Prove dry-run production checks remain deterministic and fail-closed.

### Inputs
- Scheduler validate-only
- Anchor health
- Ops status

### Outputs
- Dry-run evidence bundle under `V5-C1_PROD_DRY_RUN/`

### Definition of Done
1. Validate-only and health checks pass from repo root.
2. No apply/write path invoked.
3. Dry-run status is reproducible.

### Validation / Gates
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`
- `python3 scripts/ops_status.py --project-root <REPO_PATH>`

### Rollback
- Revert C1 changes and re-run C1 gates.

### Stop-line
- Any dry-run check fails or becomes non-deterministic.

---

## V5-H1_API_STATE_TRANSITION
### Goal
Lock API state transition behavior for assemble + waybill retrieval contracts.

### Inputs
- `core/integrations/kaspi_api_client.py`
- `scripts/ship_orders_api.py`
- `scripts/download_waybills_api.py`

### Outputs
- Tests + code proving stable transition/confirmation/fallback behavior

### Definition of Done
1. Assemble confirmation path remains deterministic.
2. Fallback target orders not in prefetch are still processed.
3. Targeted tests and operational stop-line checks are green.

### Validation / Gates
- Targeted pytest suite (assemble/waybill/fallback)
- `python3 scripts/report_waybill_status.py --since-days 3 --include-overdue --strict-stopline`

### Rollback
- Revert H1 commit(s) and re-run targeted suite.

### Stop-line
- Any regression that allows false assemble success or missing waybill PDFs without failure.

---

## V5-O1_DRIFT_PACK_SLOS
### Goal
Define and enforce daily drift-pack SLO expectations for operators.

### Inputs
- Existing drift pack builder and outputs

### Outputs
- SLO contract doc section + tests
- Evidence of pass/fail classification expectations

### Definition of Done
1. SLO contract includes hard thresholds and action states.
2. Tests guard against silent SLO contract removal.

### Validation / Gates
- Targeted pytest for SLO contract presence
- `bash scripts/lint_docs.sh`

### Rollback
- Revert O1 changes and re-run docs lint/tests.

### Stop-line
- Drift-pack contract ambiguity or missing action guidance.

---

## V5-A1_WRITE_CANARY_READINESS
### Goal
Confirm write canary readiness remains apply-gated and docs-aligned (without executing writes).

### Inputs
- `docs/ops/WRITE_CANARY_PLAN_V1.md`
- `config/write_side_gating_manifest.yaml`
- `scripts/validate_write_side_gating.py`

### Outputs
- Readiness evidence and contract tests

### Definition of Done
1. Manifest validation passes.
2. No ungated write path discovered.
3. Readiness artifact recorded with explicit no-apply statement.

### Validation / Gates
- `python3 scripts/validate_write_side_gating.py`
- Targeted pytest for canary contract references

### Rollback
- Revert A1 changes and re-run write-side validation.

### Stop-line
- Any write path reachable without env gate + `--apply`.

---

## V5-S1_MULTI_STORE_SCALE
### Goal
Lock multi-store scheduler and workflow scale contract for import + waybill deadline jobs.

### Inputs
- `config/com.example.kaspi-import.plist`
- `config/com.example.kaspi-waybill-deadline.plist`
- `scripts/install_scheduler.sh`

### Outputs
- Multi-store schedule contract evidence

### Definition of Done
1. Scheduler contracts remain pinned to required times.
2. Installer behavior remains deterministic.
3. Contract tests are green.

### Validation / Gates
- Targeted scheduler contract pytest
- `bash scripts/lint_docs.sh`

### Rollback
- Revert S1 scheduler changes and reinstall previous launchd config.

### Stop-line
- Scheduler timing drift from approved contract.

---

## Final Promotion Gates (required)
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`
- `python3 scripts/ops_status.py --project-root <REPO_PATH>`

## Rollback (global)
1. `git revert <newest_v5_commit> ... <oldest_v5_commit>`
2. Re-run minimum recheck gates:
   - `python3 scripts/validate_params.py --strict`
   - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
   - `bash scripts/lint_docs.sh`
   - `bash scripts/check_no_db_tracked.sh`
