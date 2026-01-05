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

## Phase 8: Multi-Channel Operations (Archived)

This repo is **Kaspi-only**. Multi-channel/WB workflows are archived and out of scope.

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
- Phase 9.6: Uses size-aware allocation with guardrails (see below)
- Legacy mode: Based on 90-day historical sales mix

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

## Phase 9.6: Size-Aware PO Allocation

### Overview
Phase 9.6 introduces true size-level allocation that replaces the legacy 90-day historical mix approach.

**Key Improvements:**
- OOS-filtered demand calculation (excludes stockout days)
- Size mix guardrails (3% floor, 40% cap)
- Per-size safety stock and ROP
- ANY-size REORDER trigger
- 3-tier ROIC gate for approval
- New SKU age-based adjustments
- Low demand insurance

### Using Size-Aware Allocation

```bash
# Export PO suggestions with Phase 9.6 allocation
python scripts/export_po_suggestions.py --size-aware

# Legacy mode (for comparison)
python scripts/export_po_suggestions.py

# Validate allocation calculations
python scripts/validate_size_allocation.py --verbose

# Compare old vs new allocation
python scripts/compare_old_vs_new_allocation.py
```

### Phase 9.6 Columns in PO Export

| Column | Description |
|--------|-------------|
| `trigger_sizes` | Sizes that triggered the reorder (e.g., "M,L") |
| `roic_action` | ORDER_FULL / ORDER_WITH_FLAG / REVIEW_REQUIRED |
| `demand_confidence` | ACTUAL / MARGINAL / FALLBACK / NO_DATA |

### ROIC Gate Interpretation

| ROIC | Action | Meaning |
|------|--------|---------|
| ≥20% | ORDER_FULL | Auto-approve order |
| 10-20% | ORDER_WITH_FLAG | Approve but review margin |
| <10% | REVIEW_REQUIRED | Needs manual approval |

### Size Mix Guardrails

- **Floor**: 3% minimum per size (prevents starving slow sizes)
- **Cap**: 40% maximum per size (prevents over-concentration)
- Values are renormalized to sum to 100%

### Demand Confidence Levels

| Confidence | Good Days | Uplift | Meaning |
|------------|-----------|--------|---------|
| ACTUAL | ≥30 | None | High confidence in demand estimate |
| MARGINAL | 14-29 | 1.2× | Moderate confidence, slight buffer |
| FALLBACK | <14 | 1.5× | Low confidence, larger safety buffer |
| NO_DATA | 0 | N/A | No valid sales data |

### New SKU Age Factors

| Age (days) | Factor | Effect |
|------------|--------|--------|
| <30 | 0.75 | 25% reduction (unproven product) |
| 30-60 | 0.85 | 15% reduction |
| 60-90 | 0.95 | 5% reduction |
| ≥90 | 1.0 | Full order (established product) |

### Validation Script

Run regularly to ensure calculations match Master Rules:

```bash
# Full validation (7 checks)
python scripts/validate_size_allocation.py

# Verbose output
python scripts/validate_size_allocation.py --verbose

# Validate specific SKU
python scripts/validate_size_allocation.py --sku CL_OC_MEN_LINE52_BLACK --verbose
```

**Checks performed:**
1. Parameters match Master_Inventory_Rules_v8.md
2. Size mix bounds (3%-40%)
3. Safety stock formula
4. ROP calculation
5. Status logic (Check Total FIRST)
6. ROIC gate (v8 delivery matrix)
7. Total equals sum of sizes

### Comparison Report

Compare legacy vs Phase 9.6 allocation:

```bash
# Full comparison
python scripts/compare_old_vs_new_allocation.py

# Filter by SKU
python scripts/compare_old_vs_new_allocation.py --sku LINE52

# Export to CSV
python scripts/compare_old_vs_new_allocation.py --output exports/allocation_comparison.csv
```

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
- [ ] **Refresh anchor demand data** (see below)

#### Weekly: Refresh Anchor Demand Data

Run every Monday to keep PO recommendations accurate:

```bash
# Preview changes
python3 scripts/refresh_anchor_demand.py --dry-run

# Apply if reasonable (changes should be <50% for most SKUs)
python3 scripts/refresh_anchor_demand.py
```

This updates `D_size_mix_reference.xlsx` with 60-day rolling demand averages.
Closes the gap between stale anchor data and actual recent sales.

**When to skip:** If major promotions or stockouts distorted recent sales.

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
| `generate_po_dashboard_data.py` | Regenerate PO dashboard JSON/HTML |
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

## Phase 11: Daily Kaspi Order Workflow (Excel-Based)

### Overview

Phase 11 provides a simple Excel-based workflow for daily Kaspi order processing:
1. **Import orders** from ActiveOrders.xlsx to CRM
2. **Fill MY_SIZE** manually in Excel
3. **Build waybill bundles** organized by store and type

### Quick Start (Mac Double-Click)

Two `.command` files are provided for non-technical users:

```
excel_ui/run_import_orders.command   -- Import new orders
excel_ui/run_build_waybills.command  -- Build waybill bundles
```

Double-click to run. Terminal will show progress and results.

### Step 1: Import New Orders

**Preparation:**
1. Download `ActiveOrders*.xlsx` files from Kaspi seller dashboard
2. Place files in `excel_ui/ActiveOrders/` folder

**Run Import:**
```bash
# Using .command file
Double-click: excel_ui/run_import_orders.command

# Using CLI
python scripts/import_orders_to_crm.py --verbose

# Dry run (preview without writing)
python scripts/import_orders_to_crm.py --dry-run
```

**Import Logic:**
- Filters for status: "Ожидает передачи курьеру" (ready for shipment)
- Filters for: "Требуется подписание" = "Не требуется" (no signature)
- Filters for: planned date ≤ today
- Deduplicates against existing orders (column Y = OrderID)
- Preserves Excel formulas in CRM

**Output:**
- Orders appended to `excel_ui/SALES_KSP_CRM_V3.xlsx`
- Backup created: `SALES_KSP_CRM_V3.backup_YYYYMMDD_HHMMSS.xlsx`

### Step 2: Fill MY_SIZE in Excel

After importing orders, open CRM and fill the `MY_SIZE` column:

1. Open `excel_ui/SALES_KSP_CRM_V3.xlsx`
2. Find new orders (bottom of table, MY_SIZE = empty)
3. Fill MY_SIZE for each order based on:
   - Customer info (height/weight)
   - Order history
   - Product defaults

**Size Codes:**
- Kids: `22`, `24`, `26`, `28`, `30`, `32`, `34`
- Men: `S`, `M`, `L`, `XL`, `2XL`, `3XL`, `4XL`

**Save the file** before running waybill builder.

### Step 3: Build Waybill Bundles

**Preparation:**
1. Download waybill ZIPs from Kaspi (format: `waybill*.zip`)
2. Place ZIPs in `excel_ui/ActiveOrders/` folder
3. Ensure MY_SIZE is filled for all orders to process

**Run Builder:**
```bash
# Using .command file
Double-click: excel_ui/run_build_waybills.command

# Using CLI
python scripts/build_daily_waybills.py --verbose

# Dry run (preview without creating files)
python scripts/build_daily_waybills.py --dry-run

# Specific date
python scripts/build_daily_waybills.py --date 2025-12-10
```

**Output Structure:**
```
excel_ui/Kaspi_orders/Today/
├── build_log.csv           # All orders with status
├── missing_orders.csv      # Orders without waybill PDFs
├── package_summary.csv     # Package count by store
│
├── 10.12.25_AcmeWear_qnt50/
│   ├── NORMAL_singles/
│   │   └── Berserk_футболка_XL-1.pdf
│   ├── SPECIAL_multi_line/
│   │   └── Местовая-1_Prod1-M-1(1-2)_Prod2-L-1(2-2).pdf
│   ├── SPECIAL_multi_qty/
│   │   └── Местовая-1_Nike_L-3.pdf
│   ├── manifest_normal_singles.csv
│   ├── manifest_special_multi_line.csv
│   └── manifest_special_multi_qty.csv
│
├── 10.12.25_Universal_qnt100/
│   └── ...
└── 10.12.25_11KZ_qnt25/
    └── ...
```

### Order Types and Grouping

| Type | Condition | Filename Pattern |
|------|-----------|------------------|
| **NORMAL** | qty=1, single product | `{kaspi_name_core}_{size}-{qty}.pdf` |
| **MULTI_QTY** | qty>1 | `Местовая-N_{core}_{size}-{qty}.pdf` |
| **MULTI_LINE** | Same order, multiple products | `Местовая-N_{core1}-{sz1}-{q1}(1-N)_...pdf` |

### Package Counting Rules

| Condition | Packages |
|-----------|----------|
| NORMAL (qty=1) | 1 package |
| MULTI_QTY, qty≤3, not heavy | 1 package |
| MULTI_QTY, qty>3 or heavy | qty packages |
| MULTI_LINE, total qty≤3, no heavy | 1 package |
| MULTI_LINE with heavy items | Split by heavy |

**Heavy Items** (always separate packages):
- Костюм_мужской_Хус
- Line51
- Принт_5в1_черный
- Костюм_Ромбик_ДЕТСКИЙ
- Спортивный_3в1_детский_черный

### Store Mapping

| Kaspi Warehouse Code | Display Name |
|---------------------|--------------|
| 30137883_PP1 | AcmeWear |
| 30000001_PP1 | Universal |
| 30290083_PP1 | 11KZ |
| 30000002_PP1 | STORE-B |

### Manifest CSV Format

Each store folder contains 3 manifest files:
- `manifest_normal_singles.csv`
- `manifest_special_multi_qty.csv`
- `manifest_special_multi_line.csv`

**Columns:**
| Column | Description |
|--------|-------------|
| type | NORMAL / MULTI_QTY / MULTI_LINE |
| store | Store display name |
| order_id | Kaspi order number |
| kaspi_name_core | Core product name |
| size | MY_SIZE value |
| sku_key | SKU key |
| sku_id | Full SKU ID |
| quantity | Total quantity |
| kaspi_offer_name | Full Kaspi product name |
| output | Output file path |

### Troubleshooting

**No orders imported:**
- Check ActiveOrders files are in `excel_ui/ActiveOrders/`
- Check orders have status "Ожидает передачи курьеру"
- Check orders don't require signature
- Check planned date is today or earlier

**Orders missing in waybill build:**
- Check MY_SIZE is filled in CRM
- Check waybill ZIP contains the order's PDF
- Check build_log.csv for error details

**Missing waybills:**
- Check `missing_orders.csv` for list of orders without PDFs
- Download missing waybill ZIPs from Kaspi

**Formula errors in CRM:**
- Import only writes to columns Y-AZ (raw data)
- Formulas in A-X should auto-calculate
- If formulas break, restore from backup and re-import

**Wrong store grouping:**
- Check "Склад передачи КД" column in CRM
- Verify store code matches STORE_MAP

### Daily Checklist

**Morning:**
- [ ] Download ActiveOrders*.xlsx from Kaspi
- [ ] Download waybill*.zip files from Kaspi
- [ ] Place files in `excel_ui/ActiveOrders/`
- [ ] Run import: `run_import_orders.command`
- [ ] Open CRM, fill MY_SIZE for new orders
- [ ] Save CRM
- [ ] Run builder: `run_build_waybills.command`
- [ ] Print manifests from each store folder
- [ ] Pack orders according to manifests

**Verification:**
- [ ] Check `package_summary.csv` for correct counts
- [ ] Check `missing_orders.csv` is empty (or handle missing)
- [ ] Verify PDF count matches manifest count

---

## Phase 12: Automated API Shipping Workflow

### Overview

Phase 12 automates the Kaspi shipping workflow via API:
1. **Ship orders** - Set package count and move to "Передача" stage
2. **Download waybills** - Download PDFs via API (no manual ZIP downloads)
3. **Build bundles** - Group waybills by store/type

### Quick Start (Recommended)

**Single command does everything:**
```bash
# Double-click to run full workflow (V2 - optimized)
excel_ui/run_build_waybills_v2.command
```

This runs 3 steps automatically:
1. Ship orders (set package count via API)
2. Download waybills V2 (API-direct, no CRM read - saves 30-60s)
3. Build waybill bundles

### Prerequisites

**Environment:**
```bash
# Required in .env for API write operations
ENABLE_KASPI_WRITE=1
```

**Before running:**
1. Run import script first (`run_import_orders.command`)
2. Fill MY_SIZE column in `SALES_KSP_CRM_V3.xlsx`
3. Save the CRM file

### Step 1: Ship Orders via API

Sets "Количество мест" (package count) and moves orders from "Упаковка" to "Передача".

```bash
# Full run with output
python scripts/ship_orders_api.py --verbose

# Dry run (preview only)
python scripts/ship_orders_api.py --dry-run

# Single store
python scripts/ship_orders_api.py --store UNIVERSAL --verbose
```

**Package Count Logic:**
| Condition | Packages |
|-----------|----------|
| NORMAL (qty=1) | 1 package |
| MULTI_QTY, qty≤3, not heavy | 1 package |
| MULTI_QTY, qty>3 or heavy | qty packages |
| MULTI_LINE with heavy items | Heavy items get separate packages |

**Heavy Items** (always separate packages):
- Костюм_мужской_Хус
- Line51
- Принт_5в1_черный
- Костюм_Ромбик_ДЕТСКИЙ
- Спортивный_3в1_детский_черный
- CL_NEW-CLO2_MEN_SUIT-61_BLACK
- CL_NEW-CLO2_MEN_SUIT-51_BLACK_GREY
- CL_NK_MEN_LINE51_WHITE
- CL_OC_MEN_LINE52_BLACK

### Step 2: Download Waybills via API

Downloads waybill PDFs for TODAY's batch only (exact date match).

```bash
# Download today's waybills
python scripts/download_waybills_api.py --verbose

# Dry run (preview only)
python scripts/download_waybills_api.py --dry-run

# Specific date
python scripts/download_waybills_api.py --date 2025-12-10

# All historical orders (not just today)
python scripts/download_waybills_api.py --all-dates
```

**Output:**
```
excel_ui/ActiveOrders/waybills/
├── 742227930.pdf
├── 742227931.pdf
└── ...
```

**Filtering:**
- Only downloads for orders with MY_SIZE filled in CRM
- Default: Only orders where `planned_date == today`
- Use `--all-dates` for `planned_date <= today`

### Step 3: Build Waybill Bundles

Groups PDFs by store and type. Same as Phase 11, but uses API-downloaded waybills.

```bash
python scripts/build_daily_waybills.py --verbose
```

**Waybill Sources (priority order):**
1. API downloads: `excel_ui/ActiveOrders/waybills/*.pdf`
2. ZIP files: `excel_ui/ActiveOrders/waybill*.zip`

### Full Workflow Example

```bash
# 1. Import new orders (if not done)
python scripts/import_orders_to_crm.py --verbose

# 2. [MANUAL] Fill MY_SIZE in Excel, save file

# 3. Run automated shipping workflow
python scripts/ship_orders_api.py --verbose
python scripts/download_waybills_api.py --verbose
python scripts/build_daily_waybills.py --verbose

# Or just double-click:
excel_ui/run_build_waybills_v2.command
```

### CLI Reference

**ship_orders_api.py:**
| Flag | Description |
|------|-------------|
| `--dry-run` | Preview only, no API calls |
| `--verbose` | Show detailed progress |
| `--store STORE` | Process single store only |
| `--date YYYY-MM-DD` | Target specific date |

**download_waybills_api.py:**
| Flag | Description |
|------|-------------|
| `--dry-run` | Preview only, no downloads |
| `--verbose` | Show detailed progress |
| `--store STORE` | Process single store only |
| `--date YYYY-MM-DD` | Target specific date |
| `--all-dates` | Include historical orders |
| `--days N` | API lookback days (default: 14) |

### Troubleshooting Phase 12

**"No orders ready for shipping":**
- Check MY_SIZE is filled in CRM
- Check planned_date matches today
- Verify orders are in "Упаковка" stage

**"0 waybills downloaded":**
- Orders must be in "Передача" stage (run ship script first)
- Check CRM has matching orders with MY_SIZE
- Use `--all-dates` to include past orders

**API errors:**
- Verify `ENABLE_KASPI_WRITE=1` in `.env`
- Check API tokens are valid
- Review error messages in output

**Missing waybills in build:**
- Some orders may not have waybills yet (API delay)
- Check `missing_orders.csv` for details
- Fallback: Download ZIP from Kaspi dashboard

### Daily Checklist (Phase 12)

**Morning:**
- [ ] Download ActiveOrders*.xlsx from Kaspi
- [ ] Place files in `excel_ui/ActiveOrders/`
- [ ] Run import: `run_import_orders.command`
- [ ] Open CRM, fill MY_SIZE for new orders
- [ ] Save CRM
- [ ] Run: `run_build_waybills_v2.command` (does all 3 steps)
- [ ] Print manifests from each store folder
- [ ] Pack orders according to manifests

**Verification:**
- [ ] Check ship script output for errors
- [ ] Check download count matches expected
- [ ] Check `package_summary.csv` for correct counts
- [ ] Verify PDF count matches manifest count

---

## Scheduled Jobs (launchd)

### CRM -> Database Sync (13:00 GMT+5)

**Schedule:** Daily at 13:00 Almaty time (08:00 UTC)
**Script:** `scripts/sync_crm_to_db.py`
**launchd:** `com.example.crm-db-sync`

**What it does:**
- Reads sales from `excel_ui/SALES_KSP_CRM_V3.xlsx`
- Syncs to `sales_fact_v2` table (deduplicates on order_id + sku_id + store_code)
- DemandEstimator uses this fresh data for PO recommendations

**Manual trigger:**
```bash
python scripts/sync_crm_to_db.py
python scripts/sync_crm_to_db.py --dry-run  # Preview only
```

**Check status:**
```bash
launchctl list | grep crm-db-sync
tail -50 logs/crm_sync_stdout.log
tail -50 logs/crm_sync_stderr.log
```

**Reload scheduler:**
```bash
launchctl unload ~/Library/LaunchAgents/com.example.crm-db-sync.plist
launchctl load ~/Library/LaunchAgents/com.example.crm-db-sync.plist
```

---

## Contact / Escalation
- System issues: Review `.claude/ISSUES.md`
- Architectural questions: Review `.claude/DECISIONS.md`
- Task history: Review `.claude/TASKS.md`
- Kaspi API issues: See `docs/KASPI_API_INTEGRATION.md`

---

*Document version: 7.1 (Phase 12 + Auto-Sync)*
*Last updated: 2025-12-16*
