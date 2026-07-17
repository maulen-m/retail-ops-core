# Daily Kaspi Order Processing Workflow

## Overview

This document describes the daily workflow for processing Kaspi orders, from import to courier handover.
Authoritative schedule/source-of-truth for automation timing:
`docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`.

After one-time deployment activation, the employee does only two system actions each day:

1. Fill or confirm `SalesRaw_Today.MY_SIZE` for every required row.
2. Set `Run_Control.ready_for_closeout = READY`.

Import, exact order reconciliation, Kaspi assembly, waybill download, bundle construction, and internal Telegram delivery are then automatic. No daily owner approval phrase, agent conversation, Telegram command, or separate approval for a carried-forward order is required.

## Schedule (GMT+5 Kazakhstan Time)

| Time | Activity | Automation |
|------|----------|------------|
| 11:00 | First order import | Automated (launchd) |
| 11:00-17:00 | Employee size entry in Google Ops Board | Manual |
| 17:00 | Same-day cutoff for every active Kaspi store | - |
| 15:02 | Second order import | Automated (launchd) |
| 15:02-17:00 | Employee size entry for newly visible same-day and next-day rows | Manual |
| 16:01 | Third order import | Automated (launchd) |
| 17:02 | Fourth order import (`post-cutoff DB freshness`) | Automated (launchd) |
| After stable `READY` | Exact reconciliation; nonzero scope assembles/builds/sends, proven zero scope records completion without a bundle | Automated |
| 17:00-18:00 | Package preparation when a bundle is received | Manual |
| 18:00-18:30 | Courier handover + deadline check | Manual |
| 19:15 | Shipped-truth DB sync fallback | Automated (launchd) |
| 09:30 next day | Morning shipped-truth DB sync fallback | Automated (launchd) |

## Detailed Steps

### 1. Morning Import (11:00)

The automated import runs at 11:00 GMT+5:
- Downloads orders from Kaspi API (all stores)
- Filters for status "Ожидает передачи курьеру"
- Synchronizes DB truth and publishes the Google Ops Board
- Preserves any employee-entered values in editable board columns

The Excel CRM is a legacy/back-office compatibility surface and is not part of the canonical employee workflow. Its guarded writer runs once at `00:30` as an isolated nightly sidecar while seven-day direct-feeder parity is collected; it never gates Board sizing or READY closeout.

### 2. Size Entry (11:00-12:00)

For every row in `SalesRaw_Today`:

1. Fill or confirm `MY_SIZE`.
2. When every required row is complete, set `Run_Control.ready_for_closeout = READY`.

The watcher stamps `ready_set_at` once. Together, `target_date + ready_set_at` identify the immutable daily request.

### 3. Automatic Closeout After `READY`

The canonical closeout reconciles fresh active eligible orders with every unresolved prior shipping obligation. That union has no age expiry. It is written to one exact required-orders file, SHA-256 pinned, and used unchanged for Kaspi assembly, waybill download, and bundle construction.

Canonical DB apply is owned only by closeout and requires a schema-version-2 row/size scope bound to the exact `target_date + ready_set_at`, enabled stores, orders, DB row IDs, line keys, and `MY_SIZE` values. The legacy scheduled size-writeback slots are preview-only.

For a nonzero scope, live delivery accepts only a schema-v4 manifest passed by exact path and SHA-256. Its batch hash binds the complete request/order/line/count payload, each PDF must have exact request-bound provenance, and Telegram uses a channel-wide lock. Older or modification-time-discovered manifests are diagnostic-only. A proven zero scope performs no assembly, PDF download/build, manifest creation, or Telegram send; it writes a terminal marker bound to the exact READY identity and empty required-orders file/hash. Uncertain obligations can never become zero-order success.

`excel_ui/run_build_waybills_v2.command` and direct builder commands are legacy/manual recovery tools, not employee steps.

### 4. Delivery Distribution

The canonical path, once the separately approved deployment is activated and running-state validation is green, is Google Ops Board closeout with Telegram-only bundle delivery. This document does not assert that the production scheduler is currently installed, loaded, or running. WhatsApp tooling is legacy diagnostic/manual-only and is never a canonical closeout, retry, or fallback channel. Recovery resumes the pinned Telegram ledger and never resends confirmed PDF keys.

If the reconciled required-order count is nonzero, the employee receives the complete internal bundle and packs it. If it is zero, no bundle is sent. No daily approval is required after the one-time deployment activation has been approved and validated.

**Sending order (automatic):**
1. SPECIAL_multi_line (highest priority)
2. SPECIAL_multi_qty
3. NORMAL_singles

### 5. SLA Cutoff Check (17:00)

**CRITICAL:** Orders created at or before `17:00` for every active Kaspi store must ship same day.

Check for late orders:
- Any order with `planned_delivery_date` = today
- Status still "Ожидает передачи курьеру"

### 6. Afternoon Import (15:02)

Second automated import captures:
- mid-day orders for same-day sizing through the `17:00` cutoff
- later orders for next-day visibility

### 6.1 Late Catch-Up Import (16:01)

Third automated import captures:
- additional late-arriving orders after the `15:02` pass
- the same next-day prep window, with no manual fetch required

### 6.2 Post-Cutoff DB Freshness Import (17:02)

Fourth automated import captures:
- late-window orders for DB freshness and Google Ops Board visibility
- while keeping every active store on the current `17:00` same-day cutoff contract

### 6.3 Shipped-Truth DB Refresh (post-closeout, 19:15, 09:30)

Shipped truth is not populated by Google Sheet publishing. After closeout delivery completes, the closeout script runs a DB-only Kaspi status sync for `KASPI_DELIVERY` + `ARCHIVE` states. Launchd also runs fallback shipped-truth syncs at `19:15` and next-day `09:30`.

This path updates `fact_orders_kaspi.actual_shipment_date` / `courier_transmission_date` without touching Excel CRM, Google Sheets, waybill PDFs, Telegram, or WhatsApp.

### 7. Package Preparation (17:00-18:00)

See [PACKAGING_RULES.md](PACKAGING_RULES.md) for:
- Heavy item handling
- Package counting ("Количество мест")
- Multi-item order consolidation

### 8. Courier Handover (18:00-18:40)

1. Verify all packages match waybills
2. Count total packages per manifest
3. Hand to Kaspi courier

Kaspi handover-state verification is automation-owned through the passive handover watcher and shipped-truth sync; seller-portal confirmation is not a canonical employee system action.

## SLA Rules

| Order Received | Ship By | Status |
|----------------|---------|--------|
| Every active store through 17:00 | Same day | On-time |
| Orders after 17:00 | Next day | On-time |

**Note:** The Google Ops Board same-day selection is store-aware and DB-first; see `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md` for the authoritative current cutoff table.

## Error Handling

### Import Failed
1. Check logs: `logs/import_stderr.log`
2. Verify API credentials in `.env`
3. Run manually: `python scripts/export_api_orders.py --all-stores`

### Missing Orders

A missing or omitted order must not be silently dropped or require a new approval. It remains in the local shipping-obligation ledger and is freshly reconciled on the next daily run. If fresh Kaspi truth still shows it packable, it joins that day's exact required-order set automatically. Unknown, failed, malformed, or identity-mismatched API truth retains the obligation and blocks closeout.

### Delivery Send Failed
1. Check `exports/google_ops_board/daily_index/<date>.json`
2. Check the latest closeout `delivery_send_report.json`
3. Resume the same exact request through the canonical scheduler
4. Retry only unconfirmed PDF keys from the pinned manifest

Recovery must never force-fresh, choose a newer manifest by modification time, resend a confirmed PDF key, or use WhatsApp as a canonical fallback.

## File Locations

```
excel_ui/
├── SALES_KSP_CRM_V3.xlsx       # Master CRM
├── ActiveOrders/               # Downloaded orders (archived after import)
├── Kaspi_orders/
│   ├── Today/                  # Current day's output
│   │   ├── {date}_{store}_qnt{n}/
│   │   │   ├── NORMAL_singles/
│   │   │   ├── SPECIAL_multi_line/
│   │   │   └── SPECIAL_multi_qty/
│   │   └── sent_pdfs.json      # legacy WhatsApp tracking
│   └── Archive/                # Previous days
└── backups/                    # CRM backups (7 days)

logs/
├── app.log                     # Application logs
├── errors.log                  # Error-only logs
├── import_stdout.log           # Scheduled import output
└── import_stderr.log           # Scheduled import errors
```

## Automation Scripts

| Script | Purpose | Schedule |
|--------|---------|----------|
| `run_kaspi_import_scheduler.py` | Direct API source refresh, DB enrichment, and Board publish; no CRM | 11:00, 15:02, 16:01, 17:02 (launchd) |
| `run_google_ops_board_closeout_watch_scheduler.py` | Stamp/observe stable `READY` and launch closeout | Every 60 seconds in watch window; Run_Control-only while HOLD |
| `run_google_ops_board_closeout_scheduler.py` | Serialize and resume the exact daily request | Triggered by watcher; 18:30 backstop |
| `run_google_ops_board_closeout.py` | Size writeback through pinned Telegram delivery | Canonical closeout entrypoint |
| `run_build_waybills_v2.command` | Legacy manual bundle recovery | Manual only |
| `run_send_whatsapp.command` | Legacy diagnostic recovery | Manual only; never canonical closeout |

## Contacts

- **Telegram Error Alerts:** Sent to chat_id `687884487`
- **Kaspi Support:** Via seller portal
