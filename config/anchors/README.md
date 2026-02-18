# Anchors

This folder stores local anchor pointers for daily strict validation.

## Workbook anchor symlink

Canonical workbook source (refresh daily):

- `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`
- `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx` (inbound/payment truth)

Create/update symlink pointer:

```bash
ln -sfn "~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx" \
  "~/Docs/Autonomous_business/config/anchors/SALES_KSP_CRM_LATEST.xlsx"
```

`run_strict_daily_preflight.py` launchd job reads this path via:

- `AB_CRM_WORKBOOK_PATH=~/Docs/Autonomous_business/config/anchors/SALES_KSP_CRM_LATEST.xlsx`

Create/update inbound truth pointer:

```bash
ln -sfn "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx" \
  "~/Docs/Autonomous_business/config/anchors/INBOUND_CALENDAR_LATEST.xlsx"
```

Strict single-truth validator uses inbound pointer via:

- `AB_INBOUND_WORKBOOK_PATH` (if set), otherwise
- `~/Docs/Autonomous_business/config/anchors/INBOUND_CALENDAR_LATEST.xlsx`
