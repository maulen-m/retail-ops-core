# PLAN_BOARD_V8_DAILY_OPS_AUTOPILOT_TRUTH_SCALE_2026-02-24

## Purpose
Execute Board V8 with fail-closed discipline to improve daily ops autonomy, correctness guarantees, and truth scaling while preserving write safety.

## Canonical References
- `docs/00_START_HERE.md`
- `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`
- `docs/ops/KASPI_DAILY_OPS_ORCHESTRATOR_RUNBOOK.md`
- `docs/DAILY_SOP.md`
- `docs/OPS_ROLLOUT_EVIDENCE_BOARD_V7_DAILY_OPS_SPEED_PARITY_2026-02-23.md`

## Global Constraints
- Single-agent sequential execution in one branch.
- Fail-closed only: no silent fallback to green.
- No write/apply execution without env gate + `--apply` + backup + rollback evidence.
- Every phase must have RED->GREEN targeted test evidence.

## Phase List
- `V8-T0` Plan authority + docs contract.
- `V8-C1` `fact_sales_v16` strict mapping-gap closure.
- `V8-C2` CRM identity repair canary gating and backup proof.
- `V8-H1` checkpoint/resume + cache (opt-in) + parity/benchmark.
- `V8-O1` daily green/red report generator + strict schema validator.
- `V8-A1` scheduler hook for daily report (read-only default, pinned `.venv`).
- `V8-S1` multi-store resilience contract with partial artifacts on failure.
- `V8-PROMOTE` full gate replay + PR promotion + oracle pack.

## Phase Details
### V8-T0
- Goal: lock board docs and fail-first docs contract tests.
- Outputs:
  - `docs/PLAN_BOARD_V8_DAILY_OPS_AUTOPILOT_TRUTH_SCALE_2026-02-24.md`
  - `docs/OPS_ROLLOUT_EVIDENCE_BOARD_V8_DAILY_OPS_AUTOPILOT_TRUTH_SCALE_2026-02-24.md`
  - `tests/test_board_v8_docs_contract.py`
  - `exports/validation/board_v8_2026-02-25/V8-T0_PLAN_AUTHORITY/targeted_tests_{red,green}.md`
- DoD: contract test green and docs lint green.

### V8-C1
- Goal: strict `fact_sales_v16` gap stopline reaches zero for supported historical mappings.
- Outputs:
  - `scripts/build_fact_sales_v16_from_api.py` enhancements
  - tests for strict gap closure and ambiguity stopline
  - before/after gap artifacts under `exports/validation/board_v8_2026-02-25/V8-C1/`
- DoD: strict mode green on resolved fixture and strict fail on ambiguous mapping.

### V8-C2
- Goal: strengthen CRM identity repair canary without enabling unsafe writes.
- Outputs:
  - canary script and/or strengthened patch gating
  - apply-path tests for env gating and backup proof
  - evidence under `exports/validation/board_v8_2026-02-25/V8-C2/`
- DoD: DRY-RUN default remains; apply path blocked without env gate; apply path yields backup proof.

### V8-H1
- Goal: add checkpoint/resume and opt-in cache while preserving parity.
- Outputs:
  - `scripts/run_kaspi_daily_ops.py` checkpoint/cache support
  - checkpoint/cache parity tests
  - benchmark artifacts `benchmark_timings.json` and `benchmark_timings.md`
- DoD: parity tests green and cache disabled by default.

### V8-O1
- Goal: deterministic daily report (`GREEN`/`RED`) with strict validator.
- Outputs:
  - `scripts/generate_daily_ops_report.py`
  - `scripts/validate_daily_ops_report.py`
  - `exports/daily/2026-02-25/daily_ops_report.json`
  - `exports/daily/2026-02-25/daily_ops_report.md`
- DoD: schema validator passes on generated report and fails on malformed report.

### V8-A1
- Goal: scheduler hook for daily report with pinned `.venv` runtime and read-only default.
- Outputs:
  - `config/com.example.kaspi-daily-ops-report.plist`
  - scheduler contract test
  - installer script wiring
- DoD: contract tests confirm label, schedule, pinned interpreter, and no `/usr/bin/env` python launcher.

### V8-S1
- Goal: resilience contract where any red store returns non-zero while preserving partial artifacts.
- Outputs:
  - store resilience tests
  - report/orchestrator fields proving per-store results are persisted
- DoD: red store causes exit 1; summary/report artifacts still emitted.

### V8-PROMOTE
- Goal: promote only with full local+CI gate evidence.
- Outputs:
  - `exports/validation/board_v8_2026-02-25/full_gates_green_final.md`
  - merged PR metadata stamped in evidence doc
  - offline oracle pack path recorded in `.claude/SESSION_LOG.md`
- DoD: `gates` + `headless-gates` PASS and evidence doc stamped.

## Global Gates
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`
- `python3 scripts/ops_status.py --project-root <REPO_PATH>`
- `python3 scripts/validate_daily_ops_report.py --strict --path exports/daily/<YYYY-MM-DD>/daily_ops_report.json`

## Rollback (board-level)
- Code rollback: `git revert <merge_sha>`
- Local recovery for any apply canary: restore latest pre-apply backup and rerun minimum gates.

## Stop-line criteria
- Any targeted test or global gate fails.
- Any write path reachable without env gate plus explicit `--apply`.
- Any parity mismatch between baseline and optimized flow.
- Any validator silently downgrades a red condition to warning-only.
