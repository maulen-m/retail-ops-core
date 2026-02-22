# Kaspi Daily Ops Workflow Contract

## Purpose
Lock the operational contract for daily order import and waybill workflow so changes cannot silently break production behavior.

This contract is fail-closed: workflow regressions must surface as test failures or non-zero runtime exits.

## Canonical Entrypoints
- `excel_ui/run_full_import.command`
- `excel_ui/run_build_waybills.command`

## Canonical Scheduler Contracts
- `config/com.example.kaspi-import.plist`
  - `11:00` daily import run
  - `16:03` daily import run
- `config/com.example.kaspi-waybill-deadline.plist`
  - `18:30` daily waybill deadline run
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
- keep fail-closed behavior in `run_build_waybills.command` (`HARD_FAIL` -> non-zero exit)
- keep strict stop-line report (`--strict-stopline`)
- keep fallback selection path in waybill download (`--fallback-crm`) to avoid missing PDFs for non-prefetched target IDs
- keep scheduler timings in sync with this contract and launchd plists

## Test Gate Ownership
- `tests/test_kaspi_import_scheduler_contract.py`
- `tests/test_kaspi_waybill_deadline_scheduler_contract.py`
- `tests/test_run_full_import_command_step2.py`
- `tests/test_run_build_waybills_command_stopline.py`
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
