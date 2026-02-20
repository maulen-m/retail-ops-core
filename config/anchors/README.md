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
- content freshness thresholds:
  - `AB_CRM_WORKBOOK_MAX_LAG_DAYS` (default `1`)
  - `AB_CRM_WORKBOOK_MAX_FUTURE_CONTENT_DAYS` (default `0`)

Create/update inbound truth pointer:

```bash
ln -sfn "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx" \
  "~/Docs/Autonomous_business/config/anchors/INBOUND_CALENDAR_LATEST.xlsx"
```

Strict single-truth validator uses inbound pointer via:

- `AB_INBOUND_WORKBOOK_PATH` (if set), otherwise
- `~/Docs/Autonomous_business/config/anchors/INBOUND_CALENDAR_LATEST.xlsx`

## Authority + operator checks

- This file is the single authority for anchor path contracts.
- Deterministic health check command:

```bash
python3 ~/Docs/Autonomous_business/scripts/check_anchor_health.py \
  --project-root ~/Docs/Autonomous_business
```

- Combined operator status command:

```bash
python3 ~/Docs/Autonomous_business/scripts/ops_status.py \
  --project-root ~/Docs/Autonomous_business
```
