# PLAN_OWNER_TRUTH_DIVERGENCE_RECOVERY_AND_OWNER_OUTPUTS_2026-03-11

## Goal

Recover from the current divergence stop, clear the remaining truth and governance blockers, and reconnect the branch to decision-grade owner outputs in this order:

1. Owner Profit Daily
2. Cash Risk Daily
3. PO / SKU Daily

## Scope boundary

Allowed:
- divergence reconciliation and checkpointing
- identity coverage investigation and repair
- ACMEWEAR order `832677455` DB-absence investigation and repair if proven deterministic
- live owner-truth reruns and evidence refresh
- owner-facing output generation and trust artifacts

Not allowed:
- WebUI source acquisition or new scrape
- replay fallback in live mode
- manual fabrication of `daily_ops_report.json`
- any DB write without backup, env gate, `--apply`, before/after diffs, and rollback note
- any quarantine or tolerance change to hide ACMEWEAR `832677455`

## Current measured baseline

- branch: `codex/TASK-webui-owner-truth-operationalization-v1`
- head: `25b5c1425e7b4a8164b29104362690b4fddbbef7`
- rollback anchor: `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`
- `validate_params --strict --as-of 2026-03-09`: PASS
- `validate_recent_identity_coverage --as-of 2026-03-09`: PASS
- `validate_webui_archive_vs_current_db --strict`: PASS
  - `missing_in_db_orders=0`
- latest persisted live blocker:
  - `run_owner_truth_daily --mode live --as-of 2026-03-09 --strict`: FAIL
  - `error_code=VALIDATE_ADS_SIDECAR_READINESS_FAIL`
  - freshness report points to stale external marketing DB source

## Phase breakdown

### D0 — Divergence Reconcile + Freeze

Acceptance:
- current worktree/head/status recorded
- current blocker state compared against stale bundle narrative
- checkpoint artifact exists

Commands:
- `git rev-parse --abbrev-ref HEAD`
- `git rev-parse HEAD`
- `git status --short`
- `AB_CRM_WORKBOOK_PATH=config/anchors/SALES_KSP_CRM_LATEST.xlsx python3 scripts/validate_params.py --strict --as-of 2026-03-09`
- `python3 scripts/validate_recent_identity_coverage.py --as-of 2026-03-09 --strict`
- `python3 scripts/validate_webui_archive_vs_current_db.py --start 2026-01-01 --end 2026-02-28 --ledger-root exports/order_status_ledger/webui_status_ledger_20260306_full_parse --output-dir exports/validation/webui_archive_single_truth/2026-03-11 --strict`

Stop condition:
- if actual blocker classes differ from the fresh handoff, stop after divergence-pack refresh and do not continue into D1-D4

### D1 — Governance Drift Case File

Goal:
- classify why `UNIVERSAL` and `STOREB` now fail identity coverage

Outputs:
- identity gap JSON/MD report
- root-cause memo
- repair decision

Test strategy:
- if validator logic changes, add/update `tests/test_validate_recent_identity_coverage_contract.py` before code edits

### D2 — ACMEWEAR DB-Absence Case File

Goal:
- prove whether `832677455` is a real deterministic repair target

Outputs:
- case JSON/MD
- copied DB comparison report
- repair decision

Test strategy:
- if DB comparison logic changes, add/update `tests/test_validate_webui_archive_vs_current_db_contract.py` before code edits

### D3 — Narrow Repair Phases

Goal:
- close only the blockers proven in D1/D2

Rules:
- smallest deterministic path only
- full write gating if DB writes are required

### D4 — Full Live Green Proving

Acceptance:
- `run_owner_truth_daily --mode live --as-of 2026-03-09 --strict`: PASS
- `system_doctor --strict --project-root . --as-of 2026-03-09`: GREEN
- second rerun semantically stable

### O1 — Owner Profit Daily

Acceptance:
- `exports/owner/2026-03-09/owner_profit_daily.json`
- `exports/owner/2026-03-09/owner_profit_daily.md`
- trust report exists and is decision-grade

### O2 — Cash Risk Daily

Acceptance:
- `exports/owner/2026-03-09/cash_risk_daily.json`
- `exports/owner/2026-03-09/cash_risk_daily.md`
- trust report exists and is decision-grade

### O3 — PO / SKU Daily

Acceptance:
- `exports/owner/2026-03-09/po_sku_daily.json`
- `exports/owner/2026-03-09/po_sku_daily.md`
- trust report exists and is decision-grade

### R1 — Merge / Release / Oracle Refresh

Acceptance:
- merge manifest green
- `full_gates_green_live_ops.md` refreshed
- Oracle pack uses `ArchiveSales_ALL_STORES_statusdate_mapped.csv`

### S1 — Deferred Scale Queue Lock

Acceptance:
- deferred scale work explicitly documented as out of merge scope

## Global verification gates

- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/lint_docs.sh`
- `python3 scripts/check_release_hygiene.py --strict --project-root .`
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_anchor_health.py --project-root .`
- `./.venv/bin/python scripts/ops_status.py --project-root .`
- `AB_CRM_WORKBOOK_PATH=config/anchors/SALES_KSP_CRM_LATEST.xlsx python3 scripts/validate_params.py --strict --as-of 2026-03-09`
- `python3 scripts/validate_recent_identity_coverage.py --as-of 2026-03-09 --strict`
- `python3 scripts/validate_webui_archive_vs_current_db.py --start 2026-01-01 --end 2026-02-28 --ledger-root exports/order_status_ledger/webui_status_ledger_20260306_full_parse --output-dir exports/validation/webui_archive_single_truth/2026-03-11 --strict`
- `./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`
- `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09`

## Rollback

- git rollback: restore from checkpoint patch or revert later commits
- DB rollback: restore from the backup recorded in D3 if any write is executed
