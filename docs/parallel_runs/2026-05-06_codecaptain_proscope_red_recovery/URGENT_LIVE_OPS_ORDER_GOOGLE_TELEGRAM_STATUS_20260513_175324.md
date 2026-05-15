# Urgent Live Ops Order / Google Board / Telegram Status

Generated: `2026-05-13 17:53:24 +05`

Gate: `YELLOW_WAITING_FOR_EMPLOYEE_SIZES_READY_BUTTON`

## Operator Situation

- The owner asked to urgently activate order fetching, order processing, Google Board append, and Telegram PDF delivery readiness for `2026-05-13`.
- Live order fetch/import and Google Ops Board publish have already run.
- Employee is currently filling `MY_SIZE` assignments in Google Ops Board.
- Telegram delivery must not be forced before the Google board is complete and `Run_Control.ready_for_closeout=READY`.

## Current Confirmed State

- Evidence root: `~/Docs/Autonomous_business/exports/live_ops/urgent_order_google_telegram_20260513_173521`
- Google board current target date: `2026-05-13`
- SalesRaw rows on board: `53`
- Closeout dry-run at `20260513_175221` was correctly blocked by readiness gate.
- Current readiness sample:
  - `run_control_ready_value=HOLD`
  - `run_control_ready_ok=false`
  - `blank_size_count=47` at dry-run check, then watcher log showed progress to `45`
  - `invalid_size_count=0`
  - `pending_db_writeback_count=5`
- No active closeout lock exists under `runtime/locks`.
- Google closeout watcher is loaded as `com.example.google-ops-board-closeout-watch`, interval `15` seconds, last exit code `0`.
- Telegram control bot is loaded/running as `com.example.waybill-telegram-control`, interval `15` seconds, last exit code `0`.

## Takeoff Contract

When the employee finishes filling sizes and sets `Run_Control.ready_for_closeout=READY`, the watcher path is expected to:

1. Confirm today's `Run_Control` row is for `2026-05-13`.
2. Confirm `READY`.
3. Confirm there are no blank `MY_SIZE` values and no invalid sizes.
4. Wait the `60` second READY debounce before closeout, unless the `18:57` fallback condition applies.
5. Run closeout with `--resume`.
6. Apply final Google size writeback into DB.
7. Download waybill PDFs.
8. Build daily merged waybill bundles.
9. Send delivery through Telegram first via `send_waybills_delivery.py`.
10. Run post-delivery shipped-truth sync.

## Evidence Artifacts

- Import / Google evidence root: `~/Docs/Autonomous_business/exports/live_ops/urgent_order_google_telegram_20260513_173521`
- Current dry-run closeout report: `~/Docs/Autonomous_business/exports/live_ops/urgent_order_google_telegram_20260513_173521/13_closeout_readiness_dry_run_current.json`
- Current readiness report: `~/Docs/Autonomous_business/exports/google_ops_board/workflow_runs/2026-05-13/20260513_175221_2026-05-13_closeout/readiness_report.json`
- Current size writeback dry-run: `~/Docs/Autonomous_business/exports/live_ops/urgent_order_google_telegram_20260513_173521/14_size_writeback_dry_run_current.json`
- Watcher stdout: `~/Docs/Autonomous_business/runtime_logs/google_ops_board_closeout_watch_stdout.log`
- Watcher stderr: `~/Docs/Autonomous_business/runtime_logs/google_ops_board_closeout_watch_stderr.log`
- Telegram control stdout: `~/Docs/Autonomous_business/runtime_logs/waybill_telegram_control_stdout.log`
- Telegram control stderr: `~/Docs/Autonomous_business/runtime_logs/waybill_telegram_control_stderr.log`

## Human Action Still Needed

- Employee finishes `MY_SIZE` values in Google Ops Board.
- Employee presses the Google board READY control only after size entry is complete.

No additional owner approval is required for the automation to take off under the already-approved live-ops request. The only remaining gate is operational readiness from the sheet.
