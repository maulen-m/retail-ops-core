# Anchors

This folder stores local anchor pointers for daily strict validation.

## Workbook anchor symlink

Create/update:

```bash
ln -sfn "~/Docs/Autonomous_business 2/excel_ui/SALES_KSP_CRM_V3.xlsx" \
  "~/Docs/Autonomous_business/config/anchors/SALES_KSP_CRM_LATEST.xlsx"
```

`run_strict_daily_preflight.py` launchd job reads this path via:

- `AB_CRM_WORKBOOK_PATH=~/Docs/Autonomous_business/config/anchors/SALES_KSP_CRM_LATEST.xlsx`
