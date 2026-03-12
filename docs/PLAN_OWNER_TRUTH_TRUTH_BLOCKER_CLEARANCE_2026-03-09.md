# Plan: Owner Truth Truth-Blocker Clearance 2026-03-09

## Scope

Clear the truth-layer blockers that still keep `codex/TASK-webui-owner-truth-operationalization-v1` in `DEFER`:

1. restore `exports/po_dashboard_data.json`
2. make workbook-anchor enforcement mandatory for production-grade live proving
3. clear `on_delivery_freeze` with explicit write gating
4. rerun:
   - `python3 scripts/validate_params.py --strict --as-of 2026-03-09`
   - `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09`
   - `./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`

Out of scope:

- any new WebUI scrape
- replay-mode changes
- source remediation
- unrelated docs/plan cleanup

## Baseline

- branch: `codex/TASK-webui-owner-truth-operationalization-v1`
- head: `25b5c1425e7b4a8164b29104362690b4fddbbef7`
- live blocker is operational red, not harness drift
- current strict failures:
  - `validate_params.py --strict --as-of 2026-03-09`
  - `system_doctor.py --strict --project-root . --as-of 2026-03-09`

## Phase TBC1 — Workbook Anchor Enforcement

### Goal

Prevent production-grade live and doctor runs from silently skipping workbook-anchor validation when `AB_CRM_WORKBOOK_PATH` is absent.

### Implementation

- encode live/strict workbook-anchor requirement in:
  - `scripts/run_owner_truth_daily.py`
  - `scripts/system_doctor.py`
- use the anchored workbook path already bootstrapped under `config/anchors/`
- fail closed if no anchored workbook is available

### Tests first

- extend `tests/test_run_owner_truth_daily_contract.py`
  - live mode must pass workbook anchor env to strict validator steps
  - live mode must fail closed if the workbook anchor is unavailable
- extend `tests/test_system_doctor_contract.py`
  - strict doctor must pass workbook anchor env into `validate_params.py`
  - strict doctor must fail closed if live-grade anchor is required and missing

## Phase TBC2 — PO Dashboard Artifact Restoration

### Goal

Restore `exports/po_dashboard_data.json` without introducing fallback artifacts.

### Implementation

- try the existing generator path first:
  - `python3 scripts/generate_po_dashboard_data.py`
- if generation needs code changes, add tests before editing
- write a phase-local report summarizing the exact generator command and artifact path

### Tests first

- only if code changes are needed:
  - add targeted contract coverage for generator output path / fail-closed behavior

## Phase TBC3 — On-Delivery Freeze Clearance

### Goal

Remove real residual `INVENTORY_ON_DELIVERY_COST` balances using the existing reconcile path and preserve an exact rollback trail.

### Implementation

1. run read-only analysis first
2. emit before snapshot / diff artifacts
3. create DB backup
4. apply only with:
   - `ENABLE_CASHFLOW_WRITE=1`
   - `--apply`
5. emit after snapshot / diff artifacts and rollback note

### Tests first

- extend `tests/test_on_delivery_settlement_reconcile.py` only if the existing reconcile script requires logic changes
- otherwise keep code unchanged and rely on existing idempotence coverage

## Phase TBC4 — Strict Replay of the Blocked Gates

### Goal

Rerun only the blocked truth gates and capture exact outcomes.

### Commands

- `python3 scripts/validate_params.py --strict --as-of 2026-03-09`
- `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09`
- `./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`

### Acceptance

- `validate_params.py --strict --as-of 2026-03-09` passes
- `system_doctor.py --strict --project-root . --as-of 2026-03-09` passes or isolates only the known live operational shipment blockers
- live daily run either:
  - passes, or
  - fails only on the already-known real current operational inputs

## Stopline Rules

- no DB write without backup + env gate + `--apply` + before/after diffs + rollback note
- no replay fallback for live mode
- no new scrape
- no tolerance widening
- no hidden workbook-anchor skip in production-grade runs
