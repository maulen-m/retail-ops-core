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

### 4. Run Forecast Engine (Phase 6)
```bash
# Generate demand forecasts for all SKUs
python scripts/run_forecast_engine.py

# Run with specific horizons
python scripts/run_forecast_engine.py --horizon 7,14,30
```

### 5. Review Auto-PO Suggestions (Phase 6)
```bash
# Generate automatic PO drafts
python scripts/run_auto_po.py --dry-run

# Create actual draft (requires approval)
python scripts/run_auto_po.py --trigger ROP

# Approve pending PO drafts
python scripts/po_approval_cli.py list
python scripts/po_approval_cli.py approve <draft_id>
```

### 6. Review PO Suggestions
1. Open `exports/YYYY-MM-DD/po_suggestions.csv`
2. Filter for `status = REORDER`
3. Review suggested quantities and size splits
4. Place orders as needed

---

## Phase 8: Multi-Channel Operations

### WB (Wildberries) Sales Ingestion

**When to Run:** After receiving WB weekly sales reports

```bash
# Download WB sales report from WB seller portal
# Save as: data_raw/WB_Sales_YYYY-MM-DD.xlsx

# Ingest WB sales
python scripts/ingest_channel_sales.py data_raw/WB_Sales_2025-12-06.xlsx --channel WB

# Or with verbose output
python scripts/ingest_channel_sales.py data_raw/WB_Sales_2025-12-06.xlsx --channel WB --verbose
```

**Expected Columns (Russian):**
- `Артикул продавца` → sku_key
- `Дата продажи` → order_date
- `Цена розничная` → seller_price (RUB)
- `Кол-во` → quantity
- `Вайлдберриз реализовал` → net_revenue (RUB)

### Channel Metrics Build

```bash
# Build channel metrics for today
python scripts/build_channel_metrics.py

# Backfill historical metrics (run once after initial WB data import)
python scripts/build_channel_metrics.py --backfill --days 30
```

### Expansion Analysis (Weekly)

```bash
# Score Kaspi SKUs for WB expansion potential
python scripts/run_expansion_analysis.py

# Filter by minimum score
python scripts/run_expansion_analysis.py --min-score 60

# Show only EXPAND recommendations
python scripts/run_expansion_analysis.py --recommendation EXPAND

# Export to CSV
python scripts/run_expansion_analysis.py --export
```

**Recommendation Meanings:**

| Recommendation | Score Range | Action |
|----------------|-------------|--------|
| **EXPAND** | 75+ | Launch on WB immediately |
| **TEST** | 50-74 | Small test batch (10-20 units) |
| **HOLD** | 30-49 | Monitor, revisit next quarter |
| **SKIP** | <30 | Not suitable for WB |

### Transfer Analysis

```bash
# Check for inventory imbalances between channels
python scripts/run_transfer_analysis.py

# Only critical/high urgency
python scripts/run_transfer_analysis.py --critical-only

# Send Telegram alert for critical transfers
python scripts/run_transfer_analysis.py --alert

# Export recommendations to CSV
python scripts/run_transfer_analysis.py --export
```

### WB Economics Reference

| Parameter | Value | Notes |
|-----------|-------|-------|
| Commission | 24.5% | Clothing category |
| Logistics | 408₽ | Per-unit proxy (actual varies by warehouse) |
| Tax | 3% | Kazakhstan tax on net revenue |
| FX Rate | 6.6 | RUB/KZT (update in wb_economics.py if needed) |

**Breakeven Calculation:**
```
WB Net Revenue = Price × (1 - 24.5%) - 408₽
KZT Revenue = WB Net Revenue × 6.6 × (1 - 3%)
Profit = KZT Revenue - COGS
```

---

## Phase 6 Features

### Forecast Engine
```bash
# View forecast for a specific SKU
python scripts/run_forecast_engine.py --sku-filter LINE52

# Backtest forecast accuracy
python scripts/run_forecast_backtest.py --days 30
```

### Data Quality Checks
```bash
# Run data quality report
python scripts/report_data_quality.py

# With Telegram alert
python scripts/report_data_quality.py --send-alert
```

### Portfolio Analytics
```bash
# Run portfolio review
python scripts/run_portfolio_review.py

# Check for kill candidates
python scripts/run_portfolio_review.py --show-kills
```

### Day-of-Week Patterns
```bash
# Analyze DOW patterns
python scripts/report_dow_analysis.py

# Shows weekend lift, pattern strength per SKU
```

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
- [ ] Run forecast backtest: `python scripts/run_forecast_backtest.py`
- [ ] Review kill candidates in portfolio

### Wednesday (Phase 6)
- [ ] Run data quality report: `python scripts/report_data_quality.py`
- [ ] Check DOW patterns for anomalies
- [ ] Expire stale PO drafts: `python scripts/expire_po_drafts.py`

### Friday
- [ ] Export weekly summary
```bash
python scripts/run_sku_metrics.py --csv exports/weekly_summary.csv
```
- [ ] Generate executive summary
```bash
python scripts/export_executive_summary.py
```
- [ ] Archive old exports
```bash
mv exports/2025-11-* archives/
```
- [ ] Backup database
```bash
python scripts/backup_db.py
```
- [ ] Run health check
```bash
python scripts/health_check.py
```
- [ ] Review slow-movers (D30 < 0.5) for potential discontinuation
- [ ] Review portfolio ROIC: `python scripts/run_portfolio_review.py`

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

### Core Pipeline
| Script | Purpose |
|--------|---------|
| `run_daily_pipeline.py` | Full daily automation |
| `ingest_inventory_snapshot.py` | Import inventory Excel |
| `build_daily_aggregates.py` | Rebuild sales aggregates |
| `run_sku_metrics.py` | Calculate all SKU metrics |
| `export_po_suggestions.py` | Generate PO recommendations |
| `run_reorder_alerts.py` | Send Telegram alerts |

### Forecast (Phase 6)
| Script | Purpose |
|--------|---------|
| `run_forecast_engine.py` | Generate demand forecasts |
| `run_forecast_backtest.py` | Test forecast accuracy |
| `export_accuracy_trends.py` | Export MAPE trends |

### Auto-PO (Phase 6)
| Script | Purpose |
|--------|---------|
| `run_auto_po.py` | Generate PO drafts |
| `po_approval_cli.py` | Approve/reject drafts |
| `expire_po_drafts.py` | Expire stale drafts |
| `report_po_analytics.py` | PO approval analytics |

### Analytics (Phase 6)
| Script | Purpose |
|--------|---------|
| `run_portfolio_review.py` | Portfolio ROIC analysis |
| `report_dow_analysis.py` | Day-of-week patterns |
| `report_stockout_costs.py` | Lost sales estimation |
| `report_data_quality.py` | Anomaly detection |
| `export_executive_summary.py` | Management summary |

### Infrastructure (Phase 6)
| Script | Purpose |
|--------|---------|
| `health_check.py` | System health verification |
| `backup_db.py` | Database backup with gzip |
| `send_daily_digest.py` | Telegram daily summary |

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

## Phase 9.5: Kaspi Order Automation

### Order Sync (Daily)

**When to Run:** Every morning and before processing shipments

```bash
# Check current order status
python scripts/manage_kaspi_orders.py status --store UNIVERSAL

# Sync orders from Kaspi API (dry run first)
python scripts/sync_kaspi_orders.py --store UNIVERSAL --dry-run

# Actual sync
python scripts/sync_kaspi_orders.py --store UNIVERSAL

# View synced orders
python scripts/manage_kaspi_orders.py list --store UNIVERSAL --status NEW
```

### Order Processing Workflow

**Morning workflow:**

```bash
# 1. Show suggested workflow
python scripts/manage_kaspi_orders.py workflow --store UNIVERSAL

# 2. Accept NEW orders (dry run first)
python scripts/manage_kaspi_orders.py accept-all --store UNIVERSAL --dry-run
python scripts/manage_kaspi_orders.py accept-all --store UNIVERSAL --confirm

# 3. Assemble ACCEPTED orders
python scripts/manage_kaspi_orders.py assemble-all --store UNIVERSAL --dry-run
python scripts/manage_kaspi_orders.py assemble-all --store UNIVERSAL --confirm

# 4. Download waybills
python scripts/download_waybills.py --store UNIVERSAL

# 5. Ship READY orders
python scripts/manage_kaspi_orders.py ship-all --store UNIVERSAL --dry-run
python scripts/manage_kaspi_orders.py ship-all --store UNIVERSAL --confirm
```

**Single order operations:**

```bash
# Accept single order
python scripts/manage_kaspi_orders.py accept 123456 --store UNIVERSAL

# Assemble single order
python scripts/manage_kaspi_orders.py assemble 123456 --store UNIVERSAL

# Ship single order
python scripts/manage_kaspi_orders.py ship 123456 --store UNIVERSAL

# Cancel order
python scripts/manage_kaspi_orders.py cancel 123456 --store UNIVERSAL --reason OUT_OF_STOCK
```

### Size Assignment

**Auto-assign sizes to orders:**

```bash
# Check size assignment status
python scripts/assign_sizes.py --status --store UNIVERSAL

# Auto-assign using probability cascade (dry run)
python scripts/assign_sizes.py --auto --store UNIVERSAL --dry-run

# Actual assignment
python scripts/assign_sizes.py --auto --store UNIVERSAL

# Export orders needing manual size entry
python scripts/assign_sizes.py --export-pending --store UNIVERSAL
```

**Size determination cascade:**

| Priority | Source | Confidence | When Used |
|----------|--------|------------|-----------|
| 1 | CUSTOMER | HIGH | Customer provided height/weight |
| 2 | OFFER_MODE | HIGH/MEDIUM | ≥5 sales for offer, ≥60% mode share |
| 3 | STYLE_MODE | HIGH/MEDIUM | ≥10 sales for style, ≥40% mode share |
| 4 | DEFAULT | LOW | Product type default (L for clothing) |

**Import customer parameters:**

```bash
# Generate template CSV
python scripts/import_customer_params.py --template

# Import customer height/weight
python scripts/import_customer_params.py data_raw/customer_params.csv

# Recalculate sizes after import
python scripts/import_customer_params.py data_raw/customer_params.csv --recalc
```

### Waybill Management

```bash
# Check waybill download stats
python scripts/download_waybills.py --stats

# Download pending waybills
python scripts/download_waybills.py --store UNIVERSAL

# Force redownload
python scripts/download_waybills.py --store UNIVERSAL --force

# Clean old waybills (30+ days)
python scripts/download_waybills.py --clean --days 30
```

### Order Alerts

Order alerts are sent automatically via Telegram:

| Alert Type | Trigger | Cooldown |
|------------|---------|----------|
| NEW_ORDERS | New orders synced | 1 hour |
| SHIPMENT_READY | Orders ready with waybills | 4 hours |
| DEADLINE_WARNING | Orders approaching deadline | 12 hours |

### Size Probability Rebuild

**Run weekly or after major data changes:**

```bash
# Rebuild size probability tables
python scripts/build_size_probability.py --rebuild

# Check coverage stats
python scripts/build_size_probability.py --stats

# Export size distributions
python scripts/build_size_probability.py --export
```

### Important Notes

1. **ENABLE_KASPI_WRITE=0** by default — write operations disabled
2. **Universal store only** for initial testing
3. Bulk operations require `--confirm` flag
4. Telegram confirmation required for bulk ops (≥5 orders)
5. All status changes logged to `fact_orders_kaspi`

### Order Status Reference

| Internal Status | Kaspi Status | Next Action |
|-----------------|--------------|-------------|
| NEW | NEW | Accept |
| ACCEPTED | ACCEPTED_BY_MERCHANT | Assemble |
| READY | ASSEMBLY | Ship (when waybill ready) |
| SHIPPED | KASPI_DELIVERY | Monitor delivery |
| COMPLETED | COMPLETED | Done |
| CANCELLED | CANCELLED | Review reason |

---

## Contact / Escalation
- System issues: Review `.claude/ISSUES.md`
- Architectural questions: Review `.claude/DECISIONS.md`
- Task history: Review `.claude/TASKS.md`
- Kaspi API issues: See `docs/KASPI_API_INTEGRATION.md`

---

*Document version: 4.0 (Phase 9.5)*
*Last updated: 2025-12-07*
