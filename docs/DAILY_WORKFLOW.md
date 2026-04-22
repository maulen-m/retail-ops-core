# Daily Kaspi Order Processing Workflow

## Overview

This document describes the daily workflow for processing Kaspi orders, from import to courier handover.
Authoritative schedule/source-of-truth for automation timing:
`docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`.

## Schedule (GMT+5 Kazakhstan Time)

| Time | Activity | Automation |
|------|----------|------------|
| 11:00 | First order import | Automated (launchd) |
| 11:00-15:00 | Order processing, waybill generation | Manual |
| 15:00-15:01 | Final same-day check | Manual |
| 15:01 | SLA cutoff (same-day orders) | - |
| 15:02 | Second order import | Automated (launchd) |
| 15:02-16:00 | Next-day order prep | Manual |
| 16:01 | Third order import | Automated (launchd) |
| 16:01-17:00 | Post-cutoff / next-day order prep | Manual |
| 17:02 | Fourth order import (`post-cutoff DB freshness`) | Automated (launchd) |
| 17:00-18:00 | Package preparation | Manual |
| 18:00-18:30 | Courier handover + deadline check | Manual |
| 19:15 | Shipped-truth DB sync fallback | Automated (launchd) |
| 09:30 next day | Morning shipped-truth DB sync fallback | Automated (launchd) |

## Detailed Steps

### 1. Morning Import (11:00)

The automated import runs at 11:00 GMT+5:
- Downloads orders from Kaspi API (all stores)
- Filters for status "Ожидает передачи курьеру"
- Imports to CRM (`SALES_KSP_CRM_V3.xlsx`)
- Phone numbers are populated automatically (Phase 12)

**Manual verification:**
1. Open `excel_ui/SALES_KSP_CRM_V3.xlsx`
2. Check new orders appear in `tb_SalesRaw` table
3. Verify phone numbers in column I

### 2. Size Entry (11:00-12:00)

For each new order:
1. Locate size in "Название товара в Kaspi Магазине" column
2. Enter size in column D (HEIGHT) or appropriate column
3. Mark processed orders

### 3. Waybill Generation (12:00-15:00)

Run waybill builder:
```bash
# Double-click or run (V2 - optimized):
./excel_ui/run_build_waybills_v2.command
```

This generates:
- `excel_ui/Kaspi_orders/Today/{date}_{store}_qnt{n}/`
- PDF waybills in NORMAL/SPECIAL folders
- Manifest CSV files

### 4. Delivery Distribution

Current production path is Google Ops Board closeout with Telegram-primary bundle delivery and WhatsApp fallback only when Telegram confirms zero PDFs. Legacy manual WhatsApp send remains a recovery path, not the primary daily path:
```bash
# Double-click or run:
./excel_ui/run_send_whatsapp.command
```

**Sending order (automatic):**
1. SPECIAL_multi_line (highest priority)
2. SPECIAL_multi_qty
3. NORMAL_singles

### 5. SLA Cutoff Check (15:00-15:01)

**CRITICAL:** Orders created before `15:01:00` must ship same day.

Check for late orders:
- Any order with `planned_delivery_date` = today
- Status still "Ожидает передачи курьеру"

### 6. Afternoon Import (15:02)

Second automated import captures:
- Orders created at or after `15:01:00`
- These are for next-day shipping

### 6.1 Late Catch-Up Import (16:01)

Third automated import captures:
- additional late-arriving orders after the `15:02` pass
- the same next-day prep window, with no manual fetch required

### 6.2 Post-Cutoff DB Freshness Import (17:02)

Fourth automated import captures:
- post-cutoff orders for DB freshness and next-day visibility
- while keeping `AcmeWear` on the current `16:01` same-day cutoff contract
- and keeping the remaining stores on the current `16:00` same-day cutoff contract

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
4. Confirm handover in Kaspi seller portal

## SLA Rules

| Order Received | Ship By | Status |
|----------------|---------|--------|
| Before 15:01:00 | Same day | On-time |
| 15:01:00 exactly | Next day | On-time |
| After 15:01:00 | Next day | On-time |

**Note:** `15:01:00` is the exact handover cutoff boundary. Orders at `15:00:59` are same-day; orders at `15:01:00` move to next day.

## Error Handling

### Import Failed
1. Check logs: `logs/import_stderr.log`
2. Verify API credentials in `.env`
3. Run manually: `python scripts/export_api_orders.py --all-stores`

### Missing Orders
1. Check `excel_ui/Kaspi_orders/Today/missing_orders.csv`
2. These orders couldn't match to waybill PDFs
3. Process manually via Kaspi seller portal

### Delivery Send Failed
1. Check `exports/google_ops_board/daily_index/<date>.json`
2. Check the latest closeout `delivery_send_report.json`
3. If Telegram partially sent, resume Telegram only
4. Use WhatsApp only as explicit fallback/recovery

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
| `run_full_import.command` | Import orders from API | 11:00, 15:02, 16:01, 17:02 (launchd) |
| `run_build_waybills_v2.command` | Generate waybill PDFs (V2 - optimized) | Manual |
| `run_send_whatsapp.command` | Legacy WhatsApp recovery send | Manual |

## Contacts

- **Telegram Error Alerts:** Sent to chat_id `687884487`
- **Kaspi Support:** Via seller portal
