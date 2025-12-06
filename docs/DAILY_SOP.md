# Daily Standard Operating Procedure (SOP)

## Overview
This document outlines the daily routine for operating the Autonomous Inventory/PO System.

---

## Morning Routine (9:00 AM)

### 1. Check System Health
```bash
# Verify database integrity
python scripts/test_schema.py

# Check current fact_sales state
sqlite3 db/app.db "SELECT COUNT(*), MIN(order_date), MAX(order_date) FROM fact_sales;"
```

### 2. Download Today's Inventory
1. Export current stock from Kaspi seller dashboard
2. Save as `excel/Current_stock_YYYY-MM-DD.xlsx`
3. Verify file has columns: SKU_ID, SKU_key, MY_SIZE, Current_stock

### 3. Run Daily Pipeline
```bash
# Full pipeline with alerts
python scripts/run_daily_pipeline.py

# Preview mode (no writes)
python scripts/run_daily_pipeline.py --dry-run

# Skip alerts during testing
python scripts/run_daily_pipeline.py --no-alerts
```

**Pipeline Steps:**
1. Ingest inventory snapshot → `fact_inventory_snapshot_size`
2. Calculate SKU metrics → D30, SS_total, ROP, Status
3. Export PO suggestions → `exports/YYYY-MM-DD/po_suggestions.csv`
4. Send REORDER alerts (Telegram)

### 4. Review PO Suggestions
1. Open `exports/YYYY-MM-DD/po_suggestions.csv`
2. Filter for `status = REORDER`
3. Review suggested quantities and size splits
4. Place orders as needed

---

## PO Interpretation Guide

### Status Meanings

| Status | Total vs ROP | Current vs ROP | Action Required |
|--------|--------------|----------------|-----------------|
| **REORDER** | Total < ROP | - | Place order NOW |
| **WAIT** | Total >= ROP | Current < ROP | Inbound covers - monitor |
| **OK** | - | Current >= ROP | No action needed |

### Size Split Columns
- `size_S` through `size_4XL`: Recommended units per size
- Based on 90-day historical sales mix
- Round up for fast movers (D30 > 5), down for slow movers

### ROIC Prioritization
```
Sort by: roic_pct DESC
```
- Higher ROIC = better capital efficiency
- Prioritize high-ROIC SKUs when capital is constrained
- Review low-ROIC SKUs for potential discontinuation

### PO Suggestion Fields
| Field | Description |
|-------|-------------|
| `sku_key` | Style-level SKU identifier |
| `d30` | Average daily demand (30-day) |
| `current_stock` | On-hand units |
| `inbound_stock` | Units in transit |
| `total_stock` | current + inbound |
| `rop` | Reorder point threshold |
| `status` | REORDER / WAIT / OK |
| `suggested_order` | Recommended order quantity |
| `roic_pct` | Monthly return on invested capital |

---

## Error Recovery Procedures

### Pipeline Fails at Ingestion

**Symptom:** "File not found" or parsing error

```bash
# Check file exists and format
ls -la excel/Current_stock_*.xlsx

# Verify file structure
python -c "
import pandas as pd
df = pd.read_excel('excel/Current_stock_2025-12-06.xlsx')
print(df.columns.tolist())
print(df.head())
"

# Try with verbose output
python scripts/ingest_inventory_snapshot.py excel/file.xlsx --verbose
```

### Missing SKUs in Metrics

**Symptom:** SKU not appearing in PO suggestions

```bash
# Check if SKU exists in dim_sku
sqlite3 db/app.db "SELECT * FROM dim_sku WHERE sku_key LIKE '%LINE52%';"

# Check if SKU has cost/weight data
sqlite3 db/app.db "SELECT sku_key, base_cost_cny, weight_kg FROM dim_sku WHERE base_cost_cny = 0;"
```

**Fix:** Add missing SKU to dimension tables:
```bash
# Edit config/dim_sku.yaml and re-run bootstrap
python scripts/bootstrap_db.py
```

### Telegram Alerts Not Sending

**Symptom:** No alerts despite REORDER status

1. Check `.env` configuration:
```bash
grep TELEGRAM .env
# Should have: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
```

2. Test connection:
```bash
python -c "from core.alerts.telegram import test_connection; test_connection()"
```

3. Check cooldown (24 hours default):
```bash
sqlite3 db/app.db "
SELECT sku_key, alert_date, alert_time, status
FROM fact_alert_log
WHERE alert_date >= date('now', '-1 day')
ORDER BY alert_time DESC
LIMIT 10;"
```

### Database Locked Error

**Symptom:** "database is locked" error

```bash
# Check for running processes
ps aux | grep python | grep -v grep

# Kill stuck processes if needed
pkill -f "python scripts/"

# Retry operation
python scripts/run_daily_pipeline.py
```

---

## Weekly Checklist

### Monday
- [ ] Review past week's PO accuracy
- [ ] Check for new SKUs to add to dim_sku
- [ ] Verify Kaspi store credentials working
- [ ] Review any alert failures in fact_alert_log

### Friday
- [ ] Export weekly summary
```bash
python scripts/run_sku_metrics.py --csv exports/weekly_summary.csv
```
- [ ] Archive old exports
```bash
mv exports/2025-11-* archives/
```
- [ ] Backup database
```bash
cp db/app.db backups/app_$(date +%Y%m%d).db
```
- [ ] Review slow-movers (D30 < 0.5) for potential discontinuation

---

## Key Files Reference

| Purpose | File |
|---------|------|
| Schema | `db/schema.sql` |
| Database | `db/app.db` |
| SKU Master | `dim_sku` table |
| Sales Data | `fact_sales` table |
| Daily Aggregates | `fact_sales_daily` table |
| Inventory | `fact_inventory_snapshot_size` table |
| Alerts Log | `fact_alert_log` table |

## Key Scripts

| Script | Purpose |
|--------|---------|
| `run_daily_pipeline.py` | Full daily automation |
| `ingest_inventory_snapshot.py` | Import inventory Excel |
| `build_daily_aggregates.py` | Rebuild sales aggregates |
| `run_sku_metrics.py` | Calculate all SKU metrics |
| `export_po_suggestions.py` | Generate PO recommendations |
| `run_reorder_alerts.py` | Send Telegram alerts |

---

## Troubleshooting Quick Reference

| Issue | First Check | Quick Fix |
|-------|-------------|-----------|
| No PO suggestions | `fact_sales_daily` empty | Run `build_daily_aggregates.py` |
| Wrong D30 values | Date range in query | Verify `order_date` format |
| Status always OK | Inventory not loaded | Run `ingest_inventory_snapshot.py` |
| ROIC = 0 | Zero profit or COGS | Check `dim_sku` cost/weight |
| Alerts repeating | Cooldown not working | Check `fact_alert_log` |

---

## Contact / Escalation
- System issues: Review `.claude/ISSUES.md`
- Architectural questions: Review `.claude/DECISIONS.md`
- Task history: Review `.claude/TASKS.md`

---

*Document version: 1.0*
*Last updated: 2025-12-06*
