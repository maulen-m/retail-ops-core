# PLAN_OWNER_OUTPUTS_BUSINESS_ACTIVATION_2026-03-12

## Goal

Turn the current green owner-truth runtime into an owner-usable 3-day operating package without reopening source-truth or historical blocker work.

## Baseline

- branch: `codex/TASK-webui-owner-truth-operationalization-v1`
- starting head: `6e1cbc3190793c6edd166fa1bd1847ddd25c06e1`
- rollback anchor: `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`
- current green gates:
  - `validate_params.py --strict --as-of 2026-03-09`
  - `validate_webui_archive_vs_current_db.py --range-policy full_range_owner_truth --strict`
  - `run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`
  - `system_doctor.py --strict --project-root . --as-of 2026-03-09`

## Execution order

1. `N0` Canonical Green Baseline Stamp
2. `N1` Owner Daily Brief Gap Audit
3. `N2` Cash Risk Daily Expansion
4. `N3` PO / SKU Daily Expansion
5. `N4` Owner Daily Brief Productionization
6. `N5` 3-Day Review Cycle Hardening
7. `N6` Optional Profit Semantics Unlock
8. `N7` Deferred Scheduler/Import Proving
9. `N8` Deferred Scale Queue Lock

## Guardrails

- no DB writes unless a brand-new defect is proven and separately planned
- no WebUI source reopening
- no replay-only fallback in live mode
- no fabricated runtime artifacts
- preserve current green gates throughout

## Expected deliverables

- clearer `Cash Risk Daily`
- clearer `PO / SKU Daily`
- owner-usable `owner_daily_brief`
- one reliable `run_owner_review_cycle.py` path
- refreshed scorecard evidence
