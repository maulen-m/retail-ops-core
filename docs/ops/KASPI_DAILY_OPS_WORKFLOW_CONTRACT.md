# Kaspi Daily Ops Workflow Contract

## Purpose
Lock the operational contract for daily order import and waybill workflow so changes cannot silently break production behavior.

This contract is fail-closed: workflow regressions must surface as test failures or non-zero runtime exits.

## Canonical Entrypoints
- `scripts/run_kaspi_import_scheduler.py`
- `scripts/run_google_ops_board_publish_scheduler.py --force-source-refresh`
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
  - every `60` seconds
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
- Scheduled daily shipping refresh must run direct Kaspi export + validation + DB sync + ActiveOrders enrichment + Google Ops Board publish without entering the Excel CRM workflow. `excel_ui/run_full_import.command` remains a legacy/manual back-office surface and is not a scheduled shipping prerequisite.
- Current-order line entries must not silently stop while headers keep advancing.
  The direct refresh has a separately gated entry-persistence stage: when
  `ENABLE_KASPI_CURRENT_ORDER_ENTRY_SYNC=1`, the strict ActiveOrders exporter
  writes a deterministic order-entry sidecar from the entry payloads it already
  fetched for the exact Board-included pending/overdue shipping scope. After
  header sync, the scheduler pins that sidecar's payload SHA-256 and applies it
  under the existing `ENABLE_KASPI_ENRICHMENT=1` write gate. The consumer makes
  no API calls, inserts only missing exact entries in one transaction, accepts
  an existing entry only when its identity/core fields/canonical raw JSON are
  identical, rejects extra entries for a covered order, and proves non-target
  stability plus exact readback before commit. This shipping-critical sidecar
  intentionally replaces the duplicate per-order enrichment loop only for the
  Board shipping scope; broader historical/all-stage enrichment remains a
  separately approved back-office/backfill lane. Without the exact high-level
  gate, installed behavior remains unchanged. A zero/mismatched/partial entry
  response, target-date/store/order/hash conflict, or missing header fails the
  refresh closed. A proven all-store zero-order run remains valid.
- Current-order lifecycle events must not silently stop while order headers keep
  advancing. The direct refresh has a separately gated append-only capture
  stage: when `ENABLE_KASPI_CURRENT_ORDER_STATUS_EVENT_SYNC=1`, the scheduler
  passes the existing lower-level `ENABLE_ORDER_STATUS_EVENT_WRITE=1` gate to
  `sync_kaspi_orders`. Each newly observed order, each existing order lacking a
  baseline event, and each change in canonical `(stage_code, raw_state,
  raw_status)` must append exactly one predecessor-bound idempotent
  `order_status_event` in the same transaction as its header change. This must
  preserve transitions that share one internal status (for example
  `CANCELLING -> CANCELLED`). Missing schema, an insert failure, or an
  unknown/unsupported stage must fail that store sync closed and roll back all
  of that store's header changes. An unchanged canonical tuple must append
  nothing. Without the
  exact scheduler gate, installed behavior remains unchanged. Historical
  catch-up uses the existing backup-first materializer under its own apply gate;
  routine capture must not rescan the complete historical order table.
  The same high-level gate is forwarded by both the direct Board/import refresh
  and the DB-only shipped-truth scheduler; neither path may honor an ambient
  lower-level write gate when the high-level opt-in is absent.
- A forced shipping-source refresh must never report success when the shared Google Ops Board lock is busy. The import owner retries the explicit temporary-failure result for a bounded window, then fails nonzero; a quiet publish backstop may still skip cleanly when another canonical owner holds the lock.
- Until seven consecutive scheduled business-day CRM shadow-parity results are GREEN and the separately gated direct sales-fact cutover is approved, the guarded CRM workbook writer remains active only as the `00:30` nightly back-office sidecar. It does not publish the Board, write the production DB, send messages, or participate in READY closeout. `com.example.crm-db-sync` remains the unchanged downstream compatibility reader during this parity window.
- The canonical ActiveOrders source refresh must fail on any incomplete enabled-store/API pagination. When all required reads complete but the filtered result is empty, it must replace the prior source with a current-day header-only canonical workbook so the publisher can remove stale board rows without weakening source authority.

## Standing Daily Shipping Authority

Deployment and activation are a separate one-time controlled change. A local patch, test run, documentation change, or commit does not activate production schedulers or write gates.

After the owner explicitly approves that one-time deployment and activation and running-state validation is green, the configured daily shipping automation has standing authority within this contract. The employee's completed size entries plus `Run_Control.ready_for_closeout = READY` are sufficient to run canonical closeout.

No per-day, per-batch, per-order, carried-order, or Telegram approval phrase is a runtime prerequisite. Daily execution must never block merely because a new owner permission phrase is absent. Telegram commands remain optional fallback controls, not part of the employee's normal workflow.

This standing authority is limited to the canonical daily shipping chain: narrow size writeback, exact required-order Kaspi assembly, waybill download, bundle construction, internal Telegram delivery, and DB-only shipped-truth refresh. It does not authorize unrelated order changes, stock, prices, offers, customer messages, cash, ads, or other external state.

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
  - canonical DB apply only through a closeout-generated `schema_version = 2` scope bound to exact `target_date + ready_set_at`, enabled stores/orders, DB row IDs, line keys, and pinned `MY_SIZE` values; live Sheet rows must still match, while legacy scheduled slots remain preview-only
  - exact required-order shipping via `scripts/ship_orders_api.py --required-orders-file <PINNED_JSON>`
  - the same required-order file drives waybill download / build / Telegram-only delivery
  - an exactly zero pinned required-order count creates no assembly, PDF download/build, manifest, or Telegram send; apply writes a terminal zero-order marker bound to the exact READY identity and empty required-orders path/SHA-256
  - uncertain or unresolved active obligations block and can never be converted into zero-order completion
  - canonical daily closeout must not invoke WhatsApp or open a browser
- keep closeout watcher churn bounded:
  - Google READY must trigger a `60` second debounce, then launch the canonical closeout scheduler
  - the watcher must not own closeout health or browser/API smoke; `scripts/run_google_ops_board_closeout.py` owns the single closeout health profile immediately before external closeout actions
  - recoverable READY-block status writes must be idempotent; repeated identical missing/invalid-size blockers must not rewrite `Run_Control` every poll
  - final `18:57` auto-fill is copy-only from visible valid `PROBABLE_SIZE`; blank values must report `MISSING_PROBABLE_SIZE`, invalid values must report `INVALID_PROBABLE_SIZE`, and neither may be inferred from product names or size engines
- keep source and runtime observability durable:
  - ActiveOrders source snapshots live at `exports/google_ops_board/source_snapshots/<YYYY-MM-DD>/source_snapshot.json`
  - when current-order entry sync is enabled, the source snapshot is written
    last as the commit marker and fingerprints the workbook, entry sidecar,
    apply receipt, and prewrite DB backup; missing or incomplete receipt proof
    prevents publication
  - the subsequent publish cycle must read back that exact strong commit marker and must not replace it with a weaker workbook-only snapshot
  - publication is terminally successful only after strict live Board readback proves exact target-date/order-line parity and preservation of every nonblank employee size
  - daily closeout index lives at `exports/google_ops_board/daily_index/<YYYY-MM-DD>.json`
  - scheduled Kaspi API call ledgers default to `runtime/api_ledger/kaspi_api_<YYYY-MM-DD>.jsonl` and must be JSONL, redacted, and endpoint-family based, never token/parameter dumps
  - publish, import, closeout, closeout watcher, and prewindow health schedulers must preserve explicit ledger overrides and otherwise pass the default daily ledger to child processes
- keep no-op writes cheap:
  - ActiveOrders enrichment with no fact-row or dimension change must not create a DB backup or update timestamps
  - the canonical source refresh creates one verified prewrite DB backup before
    header/entry/identity writes; the sidecar consumer must reuse that backup
    and must not create a second copy
  - size writeback with zero planned DB updates must not create a DB backup
  - publisher must report and skip no-op tab rewrites where generated rows already match live rows
- keep product attribution exact and request-bound:
  - every visible Board `_db_row_id` must rebind to the same order, store, and SKU in `fact_orders_kaspi`
  - the rebound row must have one active SKU-compatible exact store/article core; missing, inactive, incompatible, ambiguous, or cross-store conflicting article identity blocks before READY
  - generic SKU/offer/family fallback and order overrides cannot replace or bypass the exact row/article identity gate
  - an unsafe eligible row must still be published by exact identity as `Kaspi_name_core = ATTRIBUTION_REQUIRED` with a deterministic `UNSAFE_PRODUCT_ATTRIBUTION` exception; visibility success is not closeout readiness
  - closeout/full health keeps that row blocking before any DB write, shipping, PDF, Telegram, or shipped-truth stage
- keep Telegram fallback control equivalent to the Google Sheet ready button:
  - Telegram /ready may trigger closeout only after the same no-missing-size / no-invalid-size gate and `60` second debounce
  - Telegram /delivery_status reports current manifest/ledger confirmation counts
  - Telegram /resume_delivery resumes the closeout scheduler only when delivery is incomplete and the sizing gate is green
  - Telegram /final_table is status-only and resends the final totals table from the existing manifest/ledger without resending any PDFs or starting closeout
  - Telegram /halt cancels any pending Telegram debounce and writes `Run_Control.ready_for_closeout = HOLD`
  - commands must be restricted by `TELEGRAM_WAYBILL_ALLOWED_USER_IDS` or local runtime file `runtime/state/waybill_telegram_allowed_users.txt`
  - the fallback-control poll is supervised every `60` seconds; persistent loop mode is not production authority until nonzero poll exits propagate and log handles are released safely
- keep delivery completion ledger-based:
  - `Run_Control.last_orchestrator_status = OK` alone is not a green end state
  - Telegram completion requires all manifest `pdf_key` values confirmed in `telegram_send_ledger.json`
  - confirmed Telegram `pdf_key` values are immutable across every recovery mode
  - `api_started` or `unsure` entries block delivery until evidence reconciliation
  - target date `2026-07-10` is permanently excluded from send, resume, final-table, and fallback delivery actions by machine-readable owner decision
  - this date exclusion prevents sending a July-10 manifest; it does not discharge any omitted order that remains active and packable in a later fresh request
  - Telegram and legacy WhatsApp each use a non-blocking channel-wide lock under `MERGED/SEND`; contention stops that channel before send and never creates a cross-channel fallback
- keep shipped-truth refresh DB-only and post-delivery:
  - closeout must run `shipped_truth_sync` after successful delivery send and checkpoint it separately from `delivery_send`
  - if `shipped_truth_sync` fails, rerunning closeout with `--resume` must reuse the completed delivery checkpoint and retry only the shipped-truth sync stage
  - fallback launchd runs at `19:15` and next-day `09:30`
  - shipped-truth sync must fetch recent `KASPI_DELIVERY` + `ARCHIVE` states so `courierTransmissionDate` can populate `fact_orders_kaspi.actual_shipment_date` / `courier_transmission_date`
- keep strict stop-line report (`--strict-stopline`)
- keep ship-until-shipped carry-forward contract:
  - pending orders that miss one day must continue to surface on later daily runs until shipped or terminally cancelled/returned
  - obligation identity is the canonical `(store_code, order_id)` pair
  - the required daily scope is the union of fresh source-backed eligible orders and every unresolved prior obligation
  - fresh current-target orders enter the exact required daily scope without being durably registered first; the closeout may persist source-backed reconciliation updates to obligations that already existed before this request, but it registers new current-target obligations only after the shipping stage succeeds
  - when an approved exclusion makes the required scope zero, new current-target obligations may be registered only after the terminal zero-order closeout succeeds; a failed or aborted pass must not create entries whose `first_seen_target_date` is that pass's target date
  - obligation-detail reconciliation defaults to at most `60` exact reads and `120` seconds per pass, with positive overrides through `OBLIGATION_DETAIL_MAX_EXACT_READS` and `OBLIGATION_DETAIL_MAX_SECONDS`; budget exhaustion is fail-closed and non-sticky, so that pass must not persist its candidate ledger or poison a same-`READY` retry
  - obligations have no date or lookback expiry
  - packable active truth keeps or reactivates an obligation
  - cancelling or return-requested truth suspends packing but retains the obligation
  - source-backed physical handover, completed/issued, cancelled, or returned truth discharges the obligation
  - absence, API failure, malformed detail, identity mismatch, or unknown stage retains the obligation and makes closeout non-green
  - deferring or excluding one send date prevents that date's manifest from sending; it does not discharge unresolved orders from a later fresh request
  - broad `ship_orders_api.py` overdue/date selectors are manual compatibility surfaces; canonical closeout uses the exact required-order file
  - Legacy CRM compatibility only: `scripts/import_orders_to_crm.py --include-overdue` may append only `append_date - 1` missed pending rows while preserving the original planned handover date. This compatibility bound does not limit the no-expiry obligation ledger or canonical closeout scope.
  - overdue pending assembly backlog must remain visible as a stop-line until shipped; shipping health stays non-green while overdue/stale pending backlog remains after a live shipping run
  - an unresolved order does not expire after 5, 14, or 120 days; retain it until fresh source-backed physical handover or terminal cancellation/return truth discharges it
  - internal `SHIPPED` or `COMPLETED` alone is not physical handover evidence
  - `scripts/ship_orders_api.py` must emit a dedicated backlog report with age buckets + exact overdue IDs under `reports/kaspi_pending_backlog/<YYYY-MM-DD>/`
- keep the exact request and artifact contract:
  - `READY` must have a nonblank `ready_set_at`, stamped exactly once when first observed
  - immutable request identity is exactly `target_date + ready_set_at`
  - the same completed identity skips; the same incomplete identity resumes
  - a new `ready_set_at` is a new request and must not reuse external stages from another identity
  - force-fresh execution is forbidden
  - one required-orders JSON path and SHA-256 must drive shipping, download, and build
  - every required order is exact-read from Kaspi; partial selection or uncertain truth fails closed
  - build must create exactly one new immutable schema-v4 send manifest for a nonzero scope; lower schemas are inspection-only
  - schema-v4 `batch_hash` commits the complete send-authorizing payload: PDF/source-line entries, request identity, required-order/obligation/line hashes, terminal-exclusion flag, order-ID sets, and counts
  - canonical live delivery requires the explicit manifest path and raw-file SHA-256; latest/mtime discovery, hash mismatch, or post-preflight TOCTOU drift halts before send
  - every PDF requires exact provenance binding store/order identity, required-orders SHA-256, READY identity, filename/size/SHA-256, completeness, and current waybill-URL hash; missing, stale, mismatched, extra, or incomplete provenance blocks build
  - checkpoint pins manifest path/SHA-256, batch hash, obligation-scope hash, ledger path, PDF-scope hash, request identity, and required-orders path/SHA-256
  - no recovery path may select a manifest by modification time
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
