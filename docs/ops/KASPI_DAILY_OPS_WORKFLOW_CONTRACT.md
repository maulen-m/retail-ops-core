# Kaspi Daily Ops Workflow Contract

## Purpose
Lock the operational contract for daily order import and waybill workflow so changes cannot silently break production behavior.

This contract is fail-closed: workflow regressions must surface as test failures or non-zero runtime exits.

## Canonical Entrypoints
- `excel_ui/run_full_import.command`
- `excel_ui/run_merged_build_waybills.command`
- `scripts/run_kaspi_daily_ops.py`
- `scripts/run_daily_autopilot.py`
- `scripts/benchmark_kaspi_daily_ops.py`

## Canonical Scheduler Contracts
- `config/launchd_templates/com.example.kaspi-import.plist.tmpl`
  - `11:00` daily import run
  - `16:03` daily import run
- `config/launchd_templates/com.example.kaspi-waybill-deadline.plist.tmpl`
  - `18:30` daily waybill deadline run
- `config/launchd_templates/com.example.kaspi-daily-ops-report.plist.tmpl`
  - `19:10` daily daily-ops report run
- renderer: `scripts/render_launchd_plists.py`
- installer: `scripts/install_scheduler.sh`

## Multi-Store Scale Roster
- Universal
- AcmeWear
- 11KZ
- Store-C
- STORE-B

All daily import/waybill logic must preserve this roster. Any store mapping change requires
updating this contract and corresponding tests before merge.

## Workflow-Critical Components (Do Not Drift)
- API client write/read behavior:
  - `core/integrations/kaspi_api_client.py`
- Waybill download selection + fallback handling:
  - `scripts/download_waybills_api.py`
- Shipping assemble confirmation logic:
  - `scripts/ship_orders_api.py`
- Bundle build + strict health evaluation:
  - `scripts/build_daily_waybills.py`
  - `scripts/report_waybill_status.py`

## Non-Negotiable Runtime Rules
- keep fail-closed behavior in `run_merged_build_waybills.command` (`HARD_FAIL` -> non-zero exit)
- keep strict stop-line report (`--strict-stopline`)
- keep ship-until-shipped carry-forward contract:
  - pending orders that miss one day must continue to surface on later daily runs until shipped or terminally cancelled/returned
  - `scripts/ship_orders_api.py` defaults to overdue carry-forward mode; strict today-only shipping is opt-in only
  - `scripts/import_orders_to_crm.py --include-overdue` may append only previous-day missed pending orders into CRM (`append_date - 1`), while preserving the original Kaspi planned handover date
  - overdue pending assembly backlog must remain visible as a stop-line until shipped; shipping health stays non-green while overdue/stale pending backlog remains after a live shipping run
  - `scripts/ship_orders_api.py` must emit a dedicated backlog report with age buckets + exact overdue IDs under `reports/kaspi_pending_backlog/<YYYY-MM-DD>/`
- keep fallback selection path in waybill download (`--fallback-crm`) to avoid missing PDFs for non-prefetched target IDs
- keep profile contract in daily ops orchestrator:
  - `today-fast`: `report_waybill_status.py --since-days 1` (no `--include-overdue`)
  - `catch-up`: `report_waybill_status.py --since-days 3 --include-overdue`
- keep scheduler timings in sync with this contract and launchd plists
- keep daily report contract fail-closed:
  - `scripts/generate_daily_ops_report.py`
  - `scripts/validate_daily_ops_report.py --strict`
- keep post-ocean-drop reliability gates fail-closed:
  - `scripts/validate_business_insides_economics_ready.py --as-of <YYYY-MM-DD> --strict`
  - `scripts/validate_ops_selection_parity.py --as-of <YYYY-MM-DD> --strict`
    - import-vs-waybill selector overflow allowance is explicit and bounded only via `AB_OPS_SELECTION_MAX_IMPORT_OVERFLOW` (default `5` in `system_doctor` orchestration).
    - rationale: allows deterministic exclusion of terminal/not-ready rows in waybill selection while still failing on larger drift.
    - current operating evidence: the `2026-03-07` real run closed at `import=85`, `waybill_selected=80`, `overflow=5`; larger drift remains fail-closed.
    - release-anchor proving may materialize repo-local selector artifacts from a frozen seed before this validator runs; manual runtime-log fabrication is not allowed.
  - `scripts/validate_scheduler_heartbeat.py --as-of <YYYY-MM-DD> --strict`
  - `scripts/validate_shipped_truth_crm_waybill.py --since <YYYY-MM-DD> --until <YYYY-MM-DD> --strict`
- keep autopilot exception queue contract fail-closed:
  - `scripts/run_daily_autopilot.py --strict`
  - `exports/exceptions/<YYYY-MM-DD>/exceptions.{json,md}`

## Shipped Count Rule (Do Not Drift)
- Shipped truth for parity checks is anchored on API `courierTransmissionDate`.
- Historical shipped checks must include API states `KASPI_DELIVERY` + `ARCHIVE`.
- `KASPI_DELIVERY`-only shipped counting is not valid for historical daily parity.

## Promotion Governance
- Promotion checklist authority: `docs/ops/PROMOTION_MINIMUM_STANDARD.md`.
- Any timing/contract change to this workflow must update:
  - this contract doc
  - matching launchd plist(s)
  - matching scheduler contract tests

## Test Gate Ownership
- `tests/test_kaspi_import_scheduler_contract.py`
- `tests/test_kaspi_waybill_deadline_scheduler_contract.py`
- `tests/test_kaspi_daily_ops_report_scheduler_contract.py`
- `tests/test_run_full_import_command_step2.py`
- `tests/test_run_assemble_daily_command.py`
- `tests/test_run_build_waybills_command_stopline.py`
- `tests/test_run_merged_build_waybills_command_contract.py`
- `tests/test_ship_orders_api.py`
- `tests/test_import_orders_to_crm.py`
- `tests/test_waybill_selection_filters.py`
- `tests/test_kaspi_api_client.py`
- `tests/test_kaspi_daily_ops_workflow_contract_doc.py`

If any of the files above is changed, run the relevant targeted tests before merge.

## Production Dry-Run Checks
Run these before operational runs when validating environment/health without applying write-side actions:

```bash
bash scripts/install_single_truth_ops_scheduler.sh --validate-only
python3 scripts/check_anchor_health.py --project-root <REPO_PATH>
python3 scripts/ops_status.py --project-root <REPO_PATH>
```

These checks are not complete unless the repo root has:

- anchor symlinks under `config/anchors/`
- a readable `.env` with required `KASPI_TOKEN_*` keys for the active store roster
- the frozen release validation root when replaying a historical green anchor
