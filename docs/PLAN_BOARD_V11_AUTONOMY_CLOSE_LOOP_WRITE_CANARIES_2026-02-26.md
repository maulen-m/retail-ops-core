# PLAN_BOARD_V11_AUTONOMY_CLOSE_LOOP_WRITE_CANARIES_2026-02-26

## Purpose
Close the loop on daily autonomy with fail-closed controls for:
- deterministic `as_of` authority,
- machine-validated exceptions with remediation ownership,
- DB-only write canary framework (no production writes),
- Kaspi API write-like transition validation that rejects HTTP-only success.

## Canonical References
- `AGENTS.md`
- `docs/authority/INDEX.md`
- `docs/DAILY_SOP.md`
- `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`
- `docs/ops/KASPI_DAILY_OPS_ORCHESTRATOR_RUNBOOK.md`
- `docs/ops/SYSTEM_DOCTOR_RUNBOOK.md`

## Global Constraints
- Fail-closed on missing/stale/invalid required input.
- No production DB or live API writes in this board.
- Any write-like logic must require env gate + `--apply` + backup + rollback proof.
- Single-truth ladder: update owning docs before code/tests.

## Phases

### V11-T0 Baseline
Goal: reproduce strict baseline twice and record deterministic evidence.

DoD:
- baseline transcripts exist:
  - `exports/validation/board_v11_<date>/V11-T0_baseline/baseline_run_1.md`
  - `exports/validation/board_v11_<date>/V11-T0_baseline/baseline_run_2.md`
  - `exports/validation/board_v11_<date>/V11-T0_baseline/baseline_comparison.md`
- red/green evidence files exist for baseline capture.

### V11-R1 As-Of Authority
Goal: all strict scripts resolve the same deterministic `as_of` when CLI `--as-of` is not provided.

Deliverables:
- `docs/ops/AS_OF_DATE_AUTHORITY_CONTRACT.md`
- `scripts/resolve_as_of_date.py`
- `tests/test_as_of_date_authority_contract.py`

DoD:
- strict scripts converge on same `as_of` source logic.
- divergence triggers test failure.

### V11-R2 Exceptions Schema
Goal: every exception is machine-actionable and validated.

Deliverables:
- `docs/ops/EXCEPTIONS_SCHEMA_CONTRACT.md`
- `scripts/validate_exceptions_schema.py`
- structured exception rows emitted by `scripts/run_daily_autopilot.py`
- `tests/test_exceptions_schema_contract.py`

DoD:
- required exception fields: `id/domain/severity/owner/recommended_action/evidence_paths/rc/reason`.
- critical exceptions are fail-closed and surfaced.

### V12 Write Canary (DB-only)
Goal: prove canary write framework safety with bounded scope and rollback proof.

Deliverables:
- `docs/ops/WRITE_CANARY_RUNBOOK_V2.md`
- `scripts/run_write_canary.py`
- `tests/test_write_canary_contract.py`
- canary artifacts under `exports/canary/<date>/`

DoD:
- dry-run default,
- apply requires `ENABLE_WRITE_CANARY_APPLY=1` + `--apply`,
- backup + diff summary + rollback proof generated,
- idempotence proven by second apply with zero inserts.

### V13 Kaspi State Transition Contract
Goal: reject any write-like action reported as success without confirmed post-state transition.

Deliverables:
- `docs/ops/KASPI_API_STATE_TRANSITION_CONTRACT.md`
- `scripts/validate_kaspi_state_transition.py`
- `tests/test_kaspi_state_transition_contract.py`

DoD:
- strict validation fails on HTTP-only success.
- exceptions artifact produced at `exports/exceptions/<date>/api_state_transition_exceptions.json`.

### V11-PROMOTE
Goal: produce promotion-grade evidence and run all mandatory gates.

Required final artifacts:
- `docs/OPS_ROLLOUT_EVIDENCE_BOARD_V11_AUTONOMY_CLOSE_LOOP_WRITE_CANARIES_2026-02-26.md`
- `exports/validation/board_v11_<date>/full_gates_green_final.md`

Required gate chain:
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `python3 scripts/system_doctor.py --strict --project-root ~/Docs/Autonomous_business`

Rollback:
- `git revert <merge_sha>`
- for canary-only DB artifacts: restore `exports/canary/<date>/db_canary.sqlite` from `db_backup_pre_canary.sqlite`

Stop-line:
- any gate failure,
- any missing required artifact,
- any write path reachable without env gate + `--apply`,
- any state-transition success claimed without confirmation.
