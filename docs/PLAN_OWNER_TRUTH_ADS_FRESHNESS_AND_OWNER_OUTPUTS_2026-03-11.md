# Plan: Owner Truth Ads Freshness And Owner Outputs (2026-03-11)

## Objective

Recover from the stale-blocker divergence using the actual current blocker state, clear ads-sidecar readiness with the smallest safe path, then reconnect the branch to owner-facing outputs in this order:

1. Owner Profit Daily
2. Cash Risk Daily
3. PO / SKU Daily

## Confirmed current state

- Branch/worktree: `codex/TASK-webui-owner-truth-operationalization-v1`
- Preferred head: `25b5c1425e7b4a8164b29104362690b4fddbbef7`
- `validate_recent_identity_coverage.py --strict`: `PASS`
- `validate_webui_archive_vs_current_db.py --strict`: `PASS`
- Current persisted live blocker: `VALIDATE_ADS_SIDECAR_READINESS_FAIL`
- Current root cause: `ADS_SOURCE_STALE`

## Constraints

- No new WebUI scrape
- No replay-only fallback in live mode
- No manual fabrication of `daily_ops_report.json`
- No truth-side DB repair unless a new defect is proven and a separate write-gated plan is opened

## Phase breakdown

### A0 — Current-State Refresh Checkpoint

- Reproduce the current blocker set.
- Freeze the dirty delta with a patch artifact.
- Emit reconciliation artifacts under `exports/validation/owner_truth_ads_freshness_recovery/2026-03-11/`.

### A1 — Ads Source Freshness Recovery

- Use the canonical external ads refresh path first.
- Prefer the smallest successful refresh window that updates source freshness without changing repo DB state.
- If the source cannot be refreshed from canonical workflow, emit explicit external-blocker evidence.

### A2 — Conditional Live-vs-Apply Readiness Split

- Only if A1 cannot clear the blocker operationally.
- Add a narrow contract split:
  - live readiness = current sidecar usable for decision surfaces
  - apply readiness = external ads DB freshness required for sidecar refresh
- Tests first.

### A3 — Full Live Green Proving

- Rerun:
  - `run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`
  - `system_doctor.py --strict --project-root . --as-of 2026-03-09`
- Run twice and compare for semantic stability.

### O1 — Owner Profit Daily

- Emit one trustworthy owner profit daily file with explicit trust banner and the standard economics fields.

### O2 — Cash Risk Daily

- Emit one trustworthy cash risk daily file with trust banner.

### O3 — PO / SKU Daily

- Emit one trustworthy PO / SKU daily file with trust banner.

### R1 — Merge / Release / Oracle Refresh

- Only after A3 and O1 are green.

### S1 — Deferred Scale Queue Lock

- Explicitly exclude unrelated scale work from this merge scope.

## Test strategy

- No code change in A0 or A1 unless the canonical source-refresh path proves insufficient.
- If A2 is required, add or update tests before edits:
  - `tests/test_validate_ads_sidecar_readiness_contract.py`
  - `tests/test_run_owner_truth_daily_contract.py`
  - `tests/test_system_doctor_contract.py`
- If A3 does not reach green, stop without generating owner outputs or merge evidence.
