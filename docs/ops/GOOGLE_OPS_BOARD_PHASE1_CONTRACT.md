# Google Ops Board Phase 1 Contract

## Purpose
Lock the DB-first Google Sheets ops board behavior so daily publisher, enrichment, and writeback changes cannot silently reshape the employee workflow.

## Canonical Truth
- `db/app.db` remains the canonical truth.
- Google Sheets is the employee ops UI only.
- Excel CRM is no longer the daily employee intermediary.
- `MY_SIZE` is employee-entered observed size only.
- `PROBABLE_SIZE` is computed in Python/DB only and published as a value, never as a Google Sheets formula.

## Canonical Entrypoints
- `scripts/enrich_kaspi_orders_from_activeorders.py`
- `scripts/sync_google_ops_board.py`
- `scripts/sync_google_ops_board_sizes_to_db.py`
- `scripts/run_google_ops_board_closeout.py`
- `scripts/run_google_ops_board_publish_scheduler.py`
- `scripts/run_google_ops_board_size_writeback_scheduler.py`
- `scripts/run_google_ops_board_closeout_watch_scheduler.py`
- `scripts/run_google_ops_board_closeout_scheduler.py`
- `excel_ui/run_full_import.command`
- `excel_ui/run_google_ops_board_publish.command`
- `excel_ui/run_google_ops_board_size_writeback.command`
- `excel_ui/run_google_ops_board_closeout.command`

## Canonical Tabs and Ownership
- Primary editable surface: `SalesRaw_Today`
- Employee-editable column: `SalesRaw_Today.MY_SIZE`
- Explicit closeout control surface: `Run_Control`
- `Run_Control.ready_for_closeout` accepts only `HOLD` or `READY`
- Workbook tab order must start with:
  - `SalesRaw_Today`
  - `Run_Control`
- `SalesRaw_Today` is a UI-only CRM-like slice, not a workbook formula surface.
- `SalesRaw_Today` omits `Phone`; Kaspi no longer provides reliable phone values in the current daily path.
- Helper columns are hidden and system-owned.
- Other tabs (`Orders_Today`, `Needs_Size`, `Shipping_Queue`, `Exceptions`, `Shipped_Today`) are derived support views only.

## Canonical Scheduler Contracts
- Import success path:
  - immediate after successful import - Google Ops Board publish
- `config/com.example.google-ops-board-publish.plist`
  - `14:01` to `17:11` every 10 minutes publish backstop
- `config/com.example.google-ops-board-size-writeback.plist`
  - `17:15`, `17:30`, `17:45`, `18:00`, `18:15` size writeback
- `config/com.example.google-ops-board-closeout-watch.plist`
  - every `60` seconds, with script-gated watch window `11:00` to `18:29`
  - if `Run_Control` is green early, arm a `90` second READY debounce
  - start closeout only if the board is still green after that debounce
- `config/com.example.kaspi-waybill-deadline.plist`
  - `18:30` Google Ops Board closeout backstop
- installer: `scripts/install_scheduler.sh`

## Non-Negotiable Runtime Rules
- Same-day `SalesRaw_Today` publishes use `upsert-preserve` semantics.
- Same-day `Run_Control` publishes also use `upsert-preserve` semantics.
- Same-day derived support tabs rewrite from fresh DB truth on each publish:
  - `Orders_Today`
  - `Needs_Size`
  - `Shipping_Queue`
  - `Exceptions`
  - `Shipped_Today`
- A same-day publish must not remove or restructure already-published live rows.
- A same-day publish may append only truly new rows.
- A same-day publish must append truly new rows only at the bottom of the current live block.
- A same-day publish may refresh system-owned fields in place while preserving employee-entered `MY_SIZE`.
- Metadata tabs may be rewritten on each publish:
  - `README`
  - `Config_Do_Not_Edit`
- next-day rollover must archive the previous board snapshot before resetting operational tabs.
- next-day rollover must then rebuild the live board from fresh DB truth for the new target day.
- Overdue status is fail-closed and narrow:
  - source of truth: waybill carry-forward selector
  - employee-facing values: `OVERDUE` or `TODAY`
  - do not mark rows overdue just because `planned_shipment_date < target_date`
- `SalesRaw_Today.Status` drives sheet formatting:
  - red fill when `Status = OVERDUE`
  - amber fill when `MY_SIZE` is blank
  - green fill when `MY_SIZE` is filled
- `SalesRaw_Today` and `Run_Control` are managed protected sheets:
  - `SalesRaw_Today`: only `MY_SIZE` stays editable for operators
  - `Run_Control`: only `ready_for_closeout`, `ready_set_by`, `ready_set_at`, and `notes` stay editable for operators
- `SalesRaw_Today` row order is operator-first:
  - sort by `OrderID`
  - then by display `STORE_NAME`
  - then by `Kaspi_name_core`
- `SalesRaw_Today.STORE_NAME` drives store grouping color:
  - `AcmeWear` = yellow
  - `Universal` = green
  - `STORE-B` = no fill
- `SalesRaw_Today.Kaspi_name_core` uses workbook-matched visual grouping for the main recurring cores:
  - `6в1_Черный_+Сумка`
  - `Принт_5в1_черный`
  - `Line51`
- `Kaspi_name_core` must resolve from DB identity before any text-extraction fallback:
  - exact `(store_code, kaspi_offer_name)` mapping first
  - `sku_key` mapping second
  - extractor fallback last
- ActiveOrders export may enrich DB identity/details before publish:
  - source: `excel_ui/ActiveOrders/ActiveOrders.xlsx`
  - apply gate: `ENABLE_KASPI_ACTIVEORDERS_DB_WRITE=1`
- Size writeback stays narrow and explicit:
  - source: `SalesRaw_Today.MY_SIZE`
  - target: `fact_orders_kaspi.assigned_size`
  - apply gate: `ENABLE_GOOGLE_OPS_BOARD_DB_WRITE=1`
  - every applied writeback creates:
    - a fresh DB backup under `runtime/backups/`
    - a timestamped JSON report under `exports/google_ops_board/<YYYY-MM-DD>/`
  - later writebacks may replace earlier assigned sizes; traceability lives in the per-run backup path plus the old/new values captured in the JSON report
- Closeout is hybrid-gated and fail-closed:
  - `Run_Control.target_date` must match the operational target date
  - `Run_Control.ready_for_closeout` must be `READY`
  - `SalesRaw_Today` must have no blank `MY_SIZE`
  - invalid size values block the run
- If the board becomes green before `18:30`, the minute-level watcher may trigger closeout immediately.
- The watcher must ignore a transient `READY` misclick:
  - first READY detection only arms the debounce
  - the board must remain green for `90` seconds before closeout starts
- After a successful closeout for the target date:
  - later scheduled size writebacks must skip
  - the `18:30` backstop must skip
- Closeout and scheduled writeback automation share one lock:
  - do not let closeout and scheduled writeback mutate state concurrently
- Closeout must fail before shipping if active stores are missing token or merchant UID context.
- The automated closeout path is DB-first:
  - final size writeback
  - DB-first shipping
  - DB-first waybill download
  - bundle build
  - WhatsApp send
- Every closeout run writes a dedicated evidence folder under:
  - `exports/google_ops_board/workflow_runs/<YYYY-MM-DD>/<run_id>/`
- Publish apply gate remains explicit:
  - `ENABLE_GOOGLE_OPS_BOARD_WRITE=1`
- Closeout apply gate remains explicit:
  - `ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT=1`

## Archive Contract
- Previous-day rollover archive is written under:
  - `exports/google_ops_board/archive/<YYYY-MM-DD>/google_ops_board_rollover_<timestamp>.json`

## Test Gate Ownership
- `tests/test_enrich_kaspi_orders_from_activeorders.py`
- `tests/test_google_ops_board.py`
- `tests/test_sync_google_ops_board_contract.py`
- `tests/test_google_ops_board_scheduler_contract.py`
- `tests/test_run_full_import_command_step2.py`

If scheduler cadence, overdue semantics, publish behavior, or writeback ownership changes, update this contract and the matching tests first.
