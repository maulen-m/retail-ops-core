# PLAN_2_WEEK_EXECUTION_BOARD_A_C_B_V4_CAPITAL_SCALE_2026-02-21

## Purpose
Move from TASK-394 post-promotion hardening to capital-scale operational reliability by prioritizing: production dry-run confidence, PO money-gate consolidation, failure-injection proof, daily drift observability, and staged scale controls.

This plan is fail-closed and promotion-grade: unknown truth blocks publication/automation.

## Canonical References
- Prior board: `docs/PLAN_2_WEEK_EXECUTION_BOARD_A_C_B_V3_POST_PROMOTION_2026-02-21.md`
- Prior execution evidence: `docs/OPS_ROLLOUT_EVIDENCE_TASK_394_BOARD_V3_EXECUTION_2026-02-21.md`
- Stock snapshot ops: `docs/ops/STOCK_SNAPSHOT_RUNBOOK.md`
- Ads sidecar ops: `docs/marketing/ADS_SIDECAR_OPS_RUNBOOK.md`
- Offer linkage strict cutover: `docs/offer/OFFER_LINKAGE_STRICT_CUTOVER_PLAN.md`
- PO money gate contract: `docs/po/PO_MONEY_GATE_CONTRACT.md`
- Optional write canary: `docs/ops/WRITE_CANARY_PLAN_V1.md`

## Global Constraints
- Fail-closed always: unknown/missing/stale inputs stop publication and automation.
- No DB/network apply writes in this board unless explicitly covered by a dedicated write-canary phase and dual-gate tests.
- All write paths must require both env gate + explicit `--apply`.
- Active docs must avoid personal absolute paths; use repo-relative paths or `<REPO_PATH>` placeholders.
- Keep execution sequential in one branch/worktree to minimize integration risk.

## Phase Map
- `T0_PROMOTION_TASK394`
- `C1_PROD_DRY_RUN`
- `C2_PO_MONEY_GATE_CONSOLIDATION`
- `H1_FAILURE_INJECTION`
- `O1_DAILY_DRIFT_PACK`
- `A1_WRITE_CANARY_OPTIONAL`
- `S1_SCALE_MULTI_STORE`

---

## T0_PROMOTION_TASK394
### Goal
Reconcile and lock promotion baseline from TASK-394 so all downstream work starts from a single audited checkpoint.

### Inputs
- `docs/OPS_ROLLOUT_EVIDENCE_TASK_394_BOARD_V3_EXECUTION_2026-02-21.md`
- `exports/validation/board_v3_post_promotion_2026-02-21/`

### Outputs
- `docs/OPS_ROLLOUT_EVIDENCE_TASK_395_BOARD_V4_PROMOTION_2026-02-21.md` (initialized and linked)
- Baseline pointers recorded under `exports/validation/board_v4_<YYYY-MM-DD>/T0_promotion_task394/`

### Definition of Done
1. Prior green evidence and rollback are linked and reproducible.
2. V4 evidence doc includes explicit “inherits TASK-394 baseline” statement.
3. Any unresolved contradiction is logged in `.claude/ISSUES.md` before phase close.

### Validation / Gates
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`

### Rollback
- Revert V4 docs-only commits for T0 and re-run docs lint + db tracked guard.

### Stop-the-line
- Missing/unverifiable TASK-394 evidence path.
- Contradiction between V3 evidence and current contracts.

---

## C1_PROD_DRY_RUN
### Goal
Prove production path is safe in dry-run mode with fail-closed statuses and no hidden apply paths.

### Inputs
- Scheduler validate-only contracts
- Shipment preflight contracts
- Ops status and anchor health outputs

### Outputs
- Dry-run replay artifact set under `exports/validation/board_v4_<YYYY-MM-DD>/C1_prod_dry_run/`
- Updated ops notes in V4 evidence doc

### Definition of Done
1. Dry-run path produces deterministic status and health summary.
2. No write/apply side effects observed.
3. Stop-line check commands are documented and repeatable.

### Validation / Gates
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`
- `python3 scripts/ops_status.py --project-root <REPO_PATH>`
- `/tmp` cwd replay for import/path robustness

### Rollback
- Revert C1 changes and restore prior scheduler/docs wiring.

### Stop-the-line
- Any dry-run execution mutates DB/files unexpectedly.
- Any stop-line command fails or diverges between repo-root and `/tmp`.

---

## C2_PO_MONEY_GATE_CONSOLIDATION
### Goal
Ensure PO generation/publication cannot bypass money-gate prerequisites.

### Inputs
- `docs/po/PO_MONEY_GATE_CONTRACT.md`
- PO generation entrypoints and validators

### Outputs
- Consolidation evidence under `exports/validation/board_v4_<YYYY-MM-DD>/C2_po_money_gate/`
- Contract clarifications if edge cases are discovered

### Definition of Done
1. PO pipeline blocks on any red prerequisite.
2. Emergency bypass semantics are explicit and time-bounded.
3. Contract tests cover bypass prevention and fail-closed behavior.

### Validation / Gates
- `python3 scripts/validate_po_money_gate.py --json`
- `python3 scripts/generate_po_dashboard_data.py`
- Relevant pytest suites for PO money gate + generate flow

### Rollback
- Revert enforcement deltas while preserving validator visibility.

### Stop-the-line
- Any path generates PO outputs while gate is red.

---

## H1_FAILURE_INJECTION
### Goal
Demonstrate fail-closed behavior using intentional negative-path tests (missing anchor, stale source, invalid mapping, gating bypass attempt).

### Inputs
- Anchor-health checks
- Strict validators
- Existing contract test suites

### Outputs
- Red/green evidence under `exports/validation/board_v4_<YYYY-MM-DD>/H1_failure_injection/`

### Definition of Done
1. Fail-first evidence captured for each critical negative scenario.
2. Recovery path returns to deterministic green.
3. No warn-only downgrade for stop-line checks.

### Validation / Gates
- Targeted pytest fail-first/green suites for each injected scenario
- Re-run strict chain after each recovery

### Rollback
- Revert only injection harness/test updates if they destabilize baseline.

### Stop-the-line
- Any injected failure passes unexpectedly.
- Recovery cannot restore green chain deterministically.

---

## O1_DAILY_DRIFT_PACK
### Goal
Operationalize daily drift-pack generation as primary observability artifact for integrity operations.

### Inputs
- Existing drift-pack scripts and status classifier
- Strict validator outputs

### Outputs
- Daily artifacts under `exports/validation/daily/<YYYY-MM-DD>/`
- Linked status summary in V4 evidence doc

### Definition of Done
1. Drift-pack generated with deterministic schema and status buckets.
2. Operators can map each red/yellow status to an owning contract.
3. No duplicate/conflicting drift entrypoints in active docs.

### Validation / Gates
- Drift pack builder command and fixture tests
- Docs lint and authority-chain tests

### Rollback
- Revert drift-pack wiring to prior stable entrypoint.

### Stop-the-line
- Drift pack missing key integrity dimensions or misclassifies stop-line as non-blocking.

---

## A1_WRITE_CANARY_OPTIONAL
### Goal
Prepare optional write-canary readiness without executing apply actions.

### Inputs
- `docs/ops/WRITE_CANARY_PLAN_V1.md`
- Write-side gating manifest and validator

### Outputs
- Readiness checklist in V4 evidence doc
- Optional contract/test refinements only

### Definition of Done
1. No write canary execution performed.
2. Dual-gate guarantees proven by tests.
3. Kill-switch and rollback steps remain explicit.

### Validation / Gates
- `python3 scripts/validate_write_side_gating.py`
- Write-side gating tests

### Rollback
- Revert canary-readiness docs/tests if any ambiguity opens apply path.

### Stop-the-line
- Any write path becomes reachable without env gate + `--apply`.

---

## S1_SCALE_MULTI_STORE
### Goal
Harden multi-store reliability at operational scale with deterministic health semantics.

### Inputs
- Multi-store sync/waybill workflows
- Shipment health contracts and preflight

### Outputs
- Multi-store scale evidence under `exports/validation/board_v4_<YYYY-MM-DD>/S1_scale_multi_store/`
- Updated ops runbook deltas only if required

### Definition of Done
1. Multi-store path produces deterministic per-store health states.
2. Blocked stores do not silently degrade global status.
3. Retry/circuit-break behavior is observable and actionable.

### Validation / Gates
- Targeted multi-store tests (sync + waybill + shipment health)
- Required global gate chain replay

### Rollback
- Revert scale-specific tuning while retaining fail-closed defaults.

### Stop-the-line
- Any store-level hard failure is masked as global success.

---

## Required Global Gate Chain (Promotion Candidate)
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`
- `python3 scripts/ops_status.py --project-root <REPO_PATH>`

## Missing Attachments / Inputs Policy
If a required input/artifact is missing:
1. Stop phase execution immediately.
2. Log exact missing path and impact in `.claude/ISSUES.md`.
3. Record a locking decision in `.claude/DECISIONS.md`:
   - either safe fallback path (still fail-closed),
   - or explicit block until attachment is restored.
4. Do not downgrade gates to warn-only.
