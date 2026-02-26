# PLAN_H5_PROVING_RUN_AND_BUSINESS_INSIDES_TUNING_2026-02-26

## Purpose
Execute H5 proving-run kickoff with fail-closed daily gates, then harden BUSINESS_INSIDES sales visibility/freshness signals so operators do not read false-zero surfaces.

## Scope
- In scope:
  - H5 contract normalization + daily runbook + artifact validator.
  - Day-0 proving execution and stop-line evidence.
  - BUSINESS_INSIDES freshness/surface hardening and parity validator.
- Out of scope:
  - Any live Kaspi write canary.
  - Any production DB apply write.

## Phase H5-A — Contract + Validator
### Deliverables
- `docs/ops/H5_OPERATIONAL_PROVING_RUN_CONTRACT.md` updated to authoritative artifact paths.
- `docs/ops/H5_DAILY_EXECUTION_RUNBOOK.md` with deterministic daily commands.
- `scripts/validate_h5_artifact_set.py` + contract tests.

### Acceptance
- Validator fails on missing/mismatched required artifact `as_of`.
- Validator passes on complete artifact set.

## Phase H5-B — Day-0 Proving Replay
### Commands (strict)
- `python3 scripts/system_doctor.py --strict --project-root . --as-of <DAY>`
- `python3 scripts/validate_as_of_consistency.py --strict --project-root . --as-of <DAY>`
- `python3 scripts/triage_exceptions.py --exceptions exports/exceptions/<DAY>/exceptions.json --playbook docs/ops/EXCEPTION_PLAYBOOK.md --allowlist config/exceptions_allowlist.json --strict`
- `python3 scripts/validate_h5_artifact_set.py --strict --project-root . --as-of <DAY>`

### Acceptance
- Produce replay transcript + explicit day status (GREEN/RED) with stop-line reason when RED.

## Phase BI-1 — BUSINESS_INSIDES Sales Surface Hardening
### Deliverables
- `scripts/generate_business_insides.py` updates:
  - expose `observed_days_last_7_calendar`.
  - expose `latest_sale_date_available`.
  - expose `sales_truth_freshness_days`.
  - render `Sales Truth Freshness` section.
  - render `Latest Observed Sales Days (Truth)` section.
- No business math source changes (still canonical `view_sales_*_truth`).

### Acceptance
- If recent 7-day window has no sales-truth rows, markdown must show stale signal and latest observed truth days.

## Phase BI-2 — BUSINESS_INSIDES Parity Validator
### Deliverables
- `scripts/validate_business_insides_sales_parity.py`.
- tests for fresh PASS and stale strict FAIL.

### Acceptance
- Strict mode fails when freshness lag exceeds threshold or required recent-sales condition is not met.
- Validator emits machine-readable report under `exports/daily/<day>/`.

## Gates
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `python3 scripts/system_doctor.py --strict --project-root <REPO_PATH>`

## Stop-the-line
- Any failed gate.
- Any missing required H5 artifact.
- Any attempt to weaken fail-closed behavior without stronger contract tests.
