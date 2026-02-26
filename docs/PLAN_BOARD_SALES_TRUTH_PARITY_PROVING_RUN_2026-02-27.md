# PLAN_BOARD_SALES_TRUTH_PARITY_PROVING_RUN_2026-02-27

## Purpose
Close the sales/shipments trust gap by enforcing deterministic parity between BUSINESS_INSIDES shipment-state metrics and waybill selection state, then wire this into strict proving-run gates.

## Scope
- Branch: `codex/TASK-sales-truth-parity-proving-run`
- Phases:
  - `P0_sales_vs_waybill_parity`
  - `P1_asof_snapshot_consistency`
  - `P2_line_grain_identity_enrichment` (only if needed)
  - `P3_business_insides_metric_clarity`
  - `P4_proving_run_contract_gates`

## Phase Plan

### P0 Sales vs Waybill Parity
- Add `scripts/validate_sales_vs_waybill_parity.py`.
- Fail when BUSINESS_INSIDES waybill-state units/orders exceed source waybill selection cache counts for same `as_of`/store.
- Write artifacts:
  - `exports/daily/<as_of>/sales_vs_waybill_parity.json`
  - `exports/daily/<as_of>/sales_vs_waybill_parity.md`
- Wire into strict path (`system_doctor --strict`).

DoD:
- Validator fails on mismatch fixtures.
- Validator passes on known-good fixtures.
- System doctor includes this check.

### P1 As-Of Snapshot Consistency
- Extend `scripts/validate_as_of_consistency.py` to enforce:
  - BUSINESS_INSIDES JSON snapshot as_of match.
  - If waybill selection cache exists, `target_date == as_of`.
- Update authority docs for convergence set.

DoD:
- Mixed-date snapshot/cache is blocked in strict mode.
- Contract tests cover pass/fail cases.

### P2 Line-Grain Identity Enrichment
- Execute only if parity fix requires schema/pipeline enrichment.

DoD:
- If skipped, record explicit risk decision and rationale.

### P3 BUSINESS_INSIDES Metric Clarity
- Separate metric semantics in snapshot:
  - `Units Delivered (COMPLETED)` from canonical sales truth views.
  - `Orders/Units Shipped (Waybill Selection)` from waybill snapshot state.
- Emit BUSINESS_INSIDES JSON sidecar:
  - `config/business_insides/BUSINESS_INSIDES_<as_of>.json`
  - `config/business_insides/snapshots/BUSINESS_INSIDES_<as_of>.json`

DoD:
- Markdown labels are explicit and non-conflated.
- JSON payload includes `waybill_snapshot` and `units_delivered` fields.

### P4 Proving-Run Contract Gates
- Add one-command proving runner:
  - `scripts/run_h5_proving_day.py`
- Enforce artifact completeness includes parity artifact:
  - `scripts/validate_h5_artifact_set.py` requires `sales_vs_waybill_parity.json`.
- Update H5 runbook/contract docs.

DoD:
- One command executes doctor + as_of consistency + exceptions triage + H5 artifact gate.
- Non-zero exit on any step failure.
- Deterministic summary artifacts produced.

## Mandatory Gates
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`

## Stop-the-Line
- Any gate fails.
- Any mixed-date artifact set in strict mode.
- Any parity breach (`business > waybill snapshot`).
- Any write path enabled by default.

## Rollback
- Code rollback: `git revert <commit_sha>`.
- Data rollback: not required (no DB apply writes in this board).
- Gate recheck after rollback: rerun full mandatory gate chain.

## Evidence Root
- `exports/validation/board_sales_truth_parity_2026-02-27/`
