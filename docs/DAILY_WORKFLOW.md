# Daily Kaspi Order Processing Workflow

## Overview

This document describes the daily workflow for processing Kaspi orders, from import to courier handover.

## Schedule (GMT+5 Kazakhstan Time)

| Time | Activity | Automation |
|------|----------|------------|
| 11:00 | First order import | Automated (launchd) |
| 11:00-15:45 | Order processing, waybill generation | Manual |
| 15:45-16:00 | Final check, late orders | Manual |
| 16:00 | SLA cutoff (same-day orders) | - |
| 16:00 | Second order import | Automated (launchd) |
| 16:00-17:00 | Next-day order prep | Manual |
| 17:00-18:00 | Package preparation | Manual |
| 18:00-18:40 | Courier handover | Manual |

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

### 4. WhatsApp Distribution (15:00-15:45)

Send waybills to packing team:
```bash
# Double-click or run:
./excel_ui/run_send_whatsapp.command
```

**Sending order (automatic):**
1. SPECIAL_multi_line (highest priority)
2. SPECIAL_multi_qty
3. NORMAL_singles

### 5. SLA Cutoff Check (15:45-16:00)

**CRITICAL:** Orders received by 16:00:00 must ship same day.

Check for late orders:
- Any order with `planned_delivery_date` = today
- Status still "Ожидает передачи курьеру"

### 6. Afternoon Import (16:00)

Second automated import captures:
- Orders received after 11:00
- These are for next-day shipping

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
| Before 16:00:00 | Same day | On-time |
| 16:00:00 exactly | Same day | On-time (inclusive) |
| After 16:00:00 | Next day | On-time |

**Note:** 16:00:00 is the exact cutoff. Orders at 16:00:00 are same-day; 16:00:01 is next-day.

## Error Handling

### Import Failed
1. Check logs: `logs/import_stderr.log`
2. Verify API credentials in `.env`
3. Run manually: `python scripts/export_api_orders.py --all-stores`

### Missing Orders
1. Check `excel_ui/Kaspi_orders/Today/missing_orders.csv`
2. These orders couldn't match to waybill PDFs
3. Process manually via Kaspi seller portal

### WhatsApp Send Failed
1. Script stops on first failure
2. Run with `--resume` to continue from last successful send
3. Check WhatsApp Web is logged in

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
│   │   └── sent_pdfs.json      # WhatsApp tracking
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
| `run_full_import.command` | Import orders from API | 11:00, 16:00 (launchd) |
| `run_build_waybills_v2.command` | Generate waybill PDFs (V2 - optimized) | Manual |
| `run_send_whatsapp.command` | Send PDFs to WhatsApp | Manual |

## Contacts

- **Telegram Error Alerts:** Sent to chat_id `687884487`
- **Kaspi Support:** Via seller portal
