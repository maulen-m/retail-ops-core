# Kaspi Daily Ops Workflow Contract

## Purpose
Lock the operational contract for daily order import and waybill workflow so changes cannot silently break production behavior.

This contract is fail-closed: workflow regressions must surface as test failures or non-zero runtime exits.

## Canonical Entrypoints
- `excel_ui/run_full_import.command`
- `excel_ui/run_merged_build_waybills.command`
- `excel_ui/run_google_ops_board_closeout.command`
- `scripts/run_kaspi_daily_ops.py`
- `scripts/run_daily_autopilot.py`
- `scripts/benchmark_kaspi_daily_ops.py`
- `scripts/waybill_telegram_control_bot.py`

## Canonical Scheduler Contracts
- `config/com.example.kaspi-import.plist`
  - `11:00` daily import run
  - `15:02` daily import run
  - `16:01` daily import run
  - `17:02` daily import run
- `config/com.example.kaspi-waybill-deadline.plist`
  - `18:30` daily Google Ops Board closeout run
- `config/com.example.waybill-telegram-control.plist`
  - every `15` seconds
  - Telegram /status, Telegram /ready, and Telegram /halt fallback control for the same closeout gate
- `config/com.example.kaspi-daily-ops-report.plist`
  - `19:10` daily daily-ops report run
- `config/com.example.kaspi-shipped-truth-sync.plist`
  - `09:30` morning shipped-truth DB sync fallback
  - `19:15` evening shipped-truth DB sync fallback
  - runs only `scripts/run_kaspi_shipped_truth_sync_scheduler.py`, which calls `scripts/sync_kaspi_orders.py --states KASPI_DELIVERY,ARCHIVE`
  - must not touch Excel CRM, Google Sheets, waybill PDFs, Telegram, or WhatsApp
- installer: `scripts/install_scheduler.sh`
- automation pause/resume control:
  - manifest: `config/business_automation_manifest.json`
  - CLI: `scripts/manage_business_automation.py`
  - runbook: `docs/ops/BUSINESS_AUTOMATION_CONTROL_RUNBOOK.md`
  - default daily scope: `daily-ops`
  - mutation requires both `ENABLE_BUSINESS_AUTOMATION_CONTROL=1` and `--apply`
  - evidence root: `exports/automation_control/`

## Active Daily Polling Roster
- Universal
- AcmeWear
- STORE-B

Daily import/waybill polling must use this active roster.

## Archived Historical Store Identities
- 11KZ
- Store-C

These stores are archived by OD-027. Store identities, token env names, merchant IDs,
and historical rows stay preserved, but daily polling is stopped until the owner explicitly
reactivates a store. Any store mapping or lifecycle change requires updating this contract
and corresponding tests before merge.

## Same-Day Cutoff Contract
- Google Ops Board same-day operational selection is DB-first and keeps store-aware machinery available.
- Current cutoff: every active Kaspi store includes same-day pending orders created at or before `17:00`.
- Owner-approved PP1 late-window rule: Universal (`30000001_PP1`) and STORE-B (`30000002_PP1`) PP1 warehouse orders share the same all-store `17:00` Asia/Almaty cutoff; they must not fall back to any legacy `16:00` cutoff.
- Google Ops Board, waybill download, bundle build, and closeout validation paths must normalize `30000001_PP1` to `UNIVERSAL` and `30000002_PP1` to `STOREB` before store comparisons, grouping, or manifest matching.
- The `17:02` import exists for DB freshness, all-store 17:00 late-window visibility, and next-day visibility; it must not expand same-day Google Ops Board eligibility after the 17:00 cutoff.
- `excel_ui/run_full_import.command` must publish the Google Ops Board whenever export + DB sync + ActiveOrders enrichment are green, even if CRM Step 2 later turns the overall import workflow red.

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
- keep the automated 18:30 closeout DB-first:
  - final size writeback from `SalesRaw_Today.MY_SIZE`
  - DB-first shipping via `scripts/ship_orders_api.py --selection-source db`
  - DB-first waybill download / build / Telegram-primary delivery
  - WhatsApp fallback only when Telegram confirms zero PDFs and the failure is non-ambiguous
- keep closeout watcher churn bounded:
  - Google READY must trigger a `60` second debounce, then launch the canonical closeout scheduler
  - the watcher must not own closeout health or browser/API smoke; `scripts/run_google_ops_board_closeout.py` owns the single closeout health profile immediately before external closeout actions
  - recoverable READY-block status writes must be idempotent; repeated identical missing/invalid-size blockers must not rewrite `Run_Control` every poll
  - final `18:57` auto-fill is copy-only from visible valid `PROBABLE_SIZE`; blank values must report `MISSING_PROBABLE_SIZE`, invalid values must report `INVALID_PROBABLE_SIZE`, and neither may be inferred from product names or size engines
- keep source and runtime observability durable:
  - ActiveOrders source snapshots live at `exports/google_ops_board/source_snapshots/<YYYY-MM-DD>/source_snapshot.json`
  - daily closeout index lives at `exports/google_ops_board/daily_index/<YYYY-MM-DD>.json`
  - scheduled Kaspi API call ledgers default to `runtime/api_ledger/kaspi_api_<YYYY-MM-DD>.jsonl` and must be JSONL, redacted, and endpoint-family based, never token/parameter dumps
  - publish, import, closeout, closeout watcher, and prewindow health schedulers must preserve explicit ledger overrides and otherwise pass the default daily ledger to child processes
- keep no-op writes cheap:
  - size writeback with zero planned DB updates must not create a DB backup
  - publisher must report and skip no-op tab rewrites where generated rows already match live rows
- keep Telegram fallback control equivalent to the Google Sheet ready button:
  - Telegram /ready may trigger closeout only after the same no-missing-size / no-invalid-size gate and `60` second debounce
  - Telegram /delivery_status reports current manifest/ledger confirmation counts
  - Telegram /resume_delivery resumes the closeout scheduler only when delivery is incomplete and the sizing gate is green
  - Telegram /final_table is status-only and resends the final totals table from the existing manifest/ledger without resending any PDFs or starting closeout
  - Telegram /halt cancels any pending Telegram debounce and writes `Run_Control.ready_for_closeout = HOLD`
  - commands must be restricted by `TELEGRAM_WAYBILL_ALLOWED_USER_IDS` or local runtime file `runtime/state/waybill_telegram_allowed_users.txt`
- keep delivery completion ledger-based:
  - `Run_Control.last_orchestrator_status = OK` alone is not a green end state
  - Telegram completion requires all manifest `pdf_key` values confirmed in `telegram_send_ledger.json`
  - WhatsApp fallback completion requires explicit `delivery_send_report.json` evidence plus all manifest `pdf_key` values confirmed in `send_ledger.json`
- keep shipped-truth refresh DB-only and post-delivery:
  - closeout must run `shipped_truth_sync` after successful delivery send and checkpoint it separately from `delivery_send`
  - if `shipped_truth_sync` fails, rerunning closeout with `--resume` must reuse the completed delivery checkpoint and retry only the shipped-truth sync stage
  - fallback launchd runs at `19:15` and next-day `09:30`
  - shipped-truth sync must fetch recent `KASPI_DELIVERY` + `ARCHIVE` states so `courierTransmissionDate` can populate `fact_orders_kaspi.actual_shipment_date` / `courier_transmission_date`
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
- keep business automation pause/resume centralized through `scripts/manage_business_automation.py`; do not manually rediscover or hand-run one-off `launchctl bootout/bootstrap` sequences for routine proof windows or daily-ops restoration
- daily shipping restoration may use `scripts/run_daily_shipping_enablement.py enable --apply`
  for the fast LaunchAgent resume and `scripts/run_daily_shipping_enablement.py validate`
  for the separate post-17:00 DB-first closeout-health + Google-board validate-only
  proof; routine shipping green must not depend on the local CRM workbook
- keep frozen proof windows explicit: `verify --scope daily-ops --expect paused` must be green before boundary-sensitive proof work starts
- keep daily operations restoration explicit: `verify --scope daily-ops --expect running` must be green before claiming order import, Google Ops Board, closeout watcher, Telegram control, and shipped-truth automation are live again
- keep daily report contract fail-closed:
  - `scripts/generate_daily_ops_report.py`
  - `scripts/validate_daily_ops_report.py --strict`
- keep post-ocean-drop reliability gates fail-closed:
  - `scripts/validate_business_insides_economics_ready.py --as-of <YYYY-MM-DD> --strict`
  - `scripts/validate_ops_selection_parity.py --as-of <YYYY-MM-DD> --strict`
    - import-vs-waybill selector overflow allowance is explicit and bounded only via `AB_OPS_SELECTION_MAX_IMPORT_OVERFLOW` (default `5` in `system_doctor` orchestration).
    - rationale: allows deterministic exclusion of terminal/not-ready rows in waybill selection while still failing on larger drift.
    - current operating evidence: the `2026-03-07` real run closed at `import=85`, `waybill_selected=80`, `overflow=5`; larger drift remains fail-closed.
  - `scripts/validate_scheduler_heartbeat.py --as-of <YYYY-MM-DD> --strict`
  - `scripts/validate_shipped_truth_crm_waybill.py --since <YYYY-MM-DD> --until <YYYY-MM-DD> --strict`
- keep autopilot exception queue contract fail-closed:
  - `scripts/run_daily_autopilot.py --strict`
  - `exports/exceptions/<YYYY-MM-DD>/exceptions.{json,md}`

## Shipped Count Rule (Do Not Drift)
- Shipped truth for parity checks is anchored on API `courierTransmissionDate`.
- Historical shipped checks must include API states `KASPI_DELIVERY` + `ARCHIVE`.
- `KASPI_DELIVERY`-only shipped counting is not valid for historical daily parity.
- Google Sheet publish and daily report jobs do not create shipped truth; the DB-only shipped-truth sync path owns that population.

## Promotion Governance
- Promotion checklist authority: `docs/ops/PROMOTION_MINIMUM_STANDARD.md`.
- Any timing/contract change to this workflow must update:
  - this contract doc
  - matching launchd plist(s)
  - matching scheduler contract tests

## Test Gate Ownership
- `tests/test_kaspi_import_scheduler_contract.py`
- `tests/test_kaspi_shipped_truth_sync_scheduler.py`
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
