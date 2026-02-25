# PLAN_BOARD_V10_ENDGAME_E2E_AUTONOMY_2026-02-26

## Purpose
Turn Board V9 diagnostics into hard, fail-closed controls across PO, inventory, cashflow, API/waybill, and docs governance.

Target state: 14 consecutive daily cycles with all hard gates green.

## Authority Stack
- `AGENTS.md`
- `docs/00_START_HERE.md`
- `.claude/OPERATING.md`
- `docs/DAILY_SOP.md`
- `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`
- `docs/ops/KASPI_DAILY_OPS_ORCHESTRATOR_RUNBOOK.md`
- `docs/inventory/Master_Inventory_Rules_v8.md`

## Global Constraints
- Fail-closed by default. Missing inputs are hard failures.
- Dry-run default. Any apply path requires env gate + `--apply` + backup + rollback proof.
- Business formulas are single-truth from owning docs before code changes.
- Every phase needs RED→GREEN evidence under `exports/validation/board_v10_<YYYY-MM-DD>/...`.

## Phase V10-T0 — Baseline + System Doctor Snapshot
### Goal
Reproduce deterministic baseline and strict System Doctor output for board date.

### Outputs
- `exports/validation/board_v10_<YYYY-MM-DD>/V10-T0_baseline/baseline_run_1.md`
- `exports/validation/board_v10_<YYYY-MM-DD>/V10-T0_baseline/baseline_run_2.md`
- `exports/validation/board_v10_<YYYY-MM-DD>/V10-T0_baseline/baseline_comparison.md`
- `exports/validation/board_v10_<YYYY-MM-DD>/V10-T0_baseline/environment_snapshot.json`
- `exports/diagnostics/<YYYY-MM-DD>/system_health.json`
- `exports/diagnostics/<YYYY-MM-DD>/system_health.md`

### DoD
- Two baseline runs are reproducible.
- `system_doctor --strict` is green and artifacts exist.

### Stop-line
- Baseline drift with same inputs.

## Phase V10-C1 — Portfolio Completeness Gate
### Goal
Make "green" meaningful by requiring complete portfolio coverage.

### Outputs
- `docs/validation/PORTFOLIO_COMPLETENESS_CONTRACT.md`
- `scripts/build_portfolio_completeness_report.py`
- `exports/daily/<YYYY-MM-DD>/portfolio_completeness_report.json`
- `exports/daily/<YYYY-MM-DD>/portfolio_completeness_report.md`
- `tests/test_portfolio_completeness_contract.py`

### DoD
- Portfolio scope is explicit.
- Missing stock/demand/econ for active portfolio causes strict failure.

### Stop-line
- Any publish path remains green while portfolio completeness is red.

## Phase V10-C2 — PO PLAN vs REAL Contract
### Goal
Prevent phantom PO labels and enforce explicit `PLAN` vs `REAL` semantics.

### Outputs
- `scripts/validate_dashboard_plan_real_contract.py`
- `tests/test_dashboard_plan_real_po_contract.py`
- `docs/validation/DASHBOARD_CONTRACT.md` (updated contract notes)

### DoD
- No `PO-N` label without materialized REAL record.
- PLAN labels are explicit and test-enforced.

### Stop-line
- Any ambiguous PO label in dashboard outputs.

## Phase V10-C3 — Schema Unification Gate
### Goal
Prevent runtime schema surprises by validating required schema before operations.

### Outputs
- `scripts/validate_schema.py` (strict coverage updates)
- `tests/test_validate_schema_gate.py`
- `docs/ops/DB_MIGRATIONS_RUNBOOK.md`

### DoD
- Schema check fails loudly on missing required tables/columns.
- System Doctor includes schema gate in strict path.

### Stop-line
- Runtime path depends on missing schema and continues.

## Phase V10-H1 — Cashfloor + Commitments Gate
### Goal
Block decision-grade outputs and write-side actions when conservative cash floor is breached.

### Outputs
- `scripts/validate_cashfloor.py`
- `docs/cashflow/CASHFLOOR_GATE_CONTRACT.md`
- `exports/daily/<YYYY-MM-DD>/cashfloor_gate.json`
- `tests/test_cashfloor_gate_contract.py`

### DoD
- Deterministic conservative cashfloor evaluation.
- Strict red blocks decision-grade status.

### Stop-line
- Any apply path allowed while conservative cashfloor is below floor.

## Phase V10-H2 — Transfer Ledger Translation
### Goal
Translate transfer ledger into normalized cashflow events with idempotence and no double-counting.

### Outputs
- `scripts/translate_transfer_ledger_to_cashflow.py`
- `docs/cashflow/TRANSFER_LEDGER_TRANSLATION_CONTRACT.md`
- `exports/daily/<YYYY-MM-DD>/transfer_ledger_translation_report.json`
- `tests/test_transfer_ledger_translation_idempotent.py`
- `tests/test_no_double_count_contract.py`

### DoD
- Re-runs are idempotent.
- Double-count protection is contract-tested.

### Stop-line
- Re-run changes totals without source changes.

## Phase V10-A1 — Daily Autopilot + Exception Queue
### Goal
Single command produces daily report + diagnostics + exceptions with non-zero on hard failures.

### Outputs
- `scripts/run_daily_autopilot.py`
- `exports/exceptions/<YYYY-MM-DD>/exceptions.json`
- `exports/exceptions/<YYYY-MM-DD>/exceptions.md`
- `tests/test_daily_autopilot_contract.py`

### DoD
- One command emits deterministic artifacts.
- Failures are explicit and non-zero.

### Stop-line
- Best-effort continue hides failures.

## Phase V10-O1 — Observability + Green Streak
### Goal
Track and publish strict gate streaks toward 14-day autonomy target.

### Outputs
- `scripts/build_green_streak_tracker.py`
- `exports/health/streak/<YYYY-MM-DD>/green_streak.json`
- `tests/test_green_streak_tracker_contract.py`
- `docs/ops/WEEKLY_HEALTH_SCORECARD_CONTRACT.md` (streak section)

### DoD
- Streak logic deterministic.
- Red day resets streak with linked evidence.

### Stop-line
- Streak marked green without gate transcript linkage.

## Phase V10-S1 — Scale (Performance + Parity)
### Goal
Improve throughput without changing business outputs.

### Outputs
- Updated perf/parity tests and artifacts under `exports/perf/<YYYY-MM-DD>/`
- Updated budget notes in `docs/ops/DAILY_OPS_PERFORMANCE_BUDGETS.md`

### DoD
- Same-or-better parity on fetch/assemble/waybill/bundling outputs.
- Timings stay within documented budgets.

### Stop-line
- Speed optimization changes business outputs without parity proof.

## Phase V10-PROMOTE — Promotion + Oracle Pack
### Goal
Promote only with full green evidence and rollback readiness.

### Outputs
- `docs/OPS_ROLLOUT_EVIDENCE_BOARD_V10_ENDGAME_E2E_AUTONOMY_2026-02-26.md`
- `exports/validation/board_v10_<YYYY-MM-DD>/full_gates_green_final.md`
- Offline oracle pack path recorded in `claude/journal.md`

### DoD
- CI `gates` + `headless-gates` green.
- Evidence doc includes PR link, merge SHA, CI links, and rollback steps.

### Stop-line
- Promotion metadata missing or rollback instructions incomplete.

## Required Gate Chain
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`
- `python3 scripts/ops_status.py --project-root <REPO_PATH>`
- `python3 scripts/system_doctor.py --strict --project-root <REPO_PATH>`
- `python3 scripts/validate_daily_ops_report.py --strict --path exports/daily/<YYYY-MM-DD>/daily_ops_report.json` (if report exists)

## Missing Attachments Policy
- Missing required source: hard fail and record in evidence.
- Missing optional source: proceed with explicit assumption and add a test gate.
- Conflicts between sources: resolve using authority stack and record in `.claude/DECISIONS.md`.
