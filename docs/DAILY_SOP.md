# Daily Standard Operating Procedure (SOP)

## Overview
This document outlines the daily routine for operating the Autonomous Inventory/PO System.  
Scope: Kaspi-only.

### Single-Truth Strict Gate (Workbook Anchored)

Anchor path and symlink contract authority: `config/anchors/README.md` is authoritative.
Write-side apply contract authority: `docs/WRITE_SIDE_GATING_CONTRACT.md` and `docs/WRITE_APPLY_RUNBOOK.md`.
Promotion evidence policy authority: `docs/OPS_ROLLOUT_EVIDENCE_V2_9_PROMOTION_POLICY_2026-02-20.md`.
Daily import + waybill workflow contract authority: `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`.
Google Ops Board phase-1 contract authority: `docs/ops/GOOGLE_OPS_BOARD_PHASE1_CONTRACT.md`.
Business automation pause/resume authority: `docs/ops/BUSINESS_AUTOMATION_CONTROL_RUNBOOK.md`.

Google Ops Board operational contract (employee sizing surface):
- `SalesRaw_Today` is the primary editable daily table.
- `HEIGHT` and `WEIGHT` are employee-entered customer parameters and must be preserved across same-day republishes.
- `MY_SIZE` is employee-entered observed size only.
- `PROBABLE_SIZE` is DB-computed only; Google Sheets does not own business formulas.
- `Status` is operational and limited to `TODAY` / `OVERDUE` using waybill carry-forward truth, not simple row age.
- Same-day publishes refresh system-owned fields in place while preserving employee-entered `HEIGHT`, `WEIGHT`, and `MY_SIZE`.
- Before the explicit `18:57` fallback, automation must not fill `MY_SIZE` defaults while the employee is manually sizing orders.
- The first daily Google Ops Board append/publish must order visible shipment rows by store name A-Z in addition to the normal deterministic row order.
- `SalesRaw_Today` is protected except for `HEIGHT`, `WEIGHT`, and `MY_SIZE`; `Run_Control` is protected except for operator input cells.
- workbook identity sync runs before the first live board publish of the day and re-runs only when the workbook fingerprint changes.
- Google Sheets remains UI only; mapping, probable size, naming, and closeout logic stay in Python/DB.
Promotion minimum merge standard authority: `docs/ops/PROMOTION_MINIMUM_STANDARD.md`.

Current daily scheduler contract (GMT+5):
- import jobs: `11:00`, `15:02`, `16:01`, and `17:02`
- shipped-truth DB sync jobs: `09:30` and `19:15`
  - DB-only path; no Excel CRM import, no Google Sheet publish, no Telegram/WhatsApp send
  - refreshes recent `KASPI_DELIVERY` + `ARCHIVE` order states so `fact_orders_kaspi.actual_shipment_date` / `courier_transmission_date` do not stay stale after evening closeout
- same-day Google Ops Board cutoff is currently store-aware:
  - `AcmeWear` stays same-day through `17:00`
  - all remaining stores stay same-day through `16:00`
- Google Ops Board pre-window health gate: `13:45`
  - runs DB preflight, workbook identity sync, Google board contract check, Kaspi store-context validation, and WhatsApp smoke
  - blocks later automated publish / closeout if red
- Google Ops Board publish jobs: `07:00` daily source-refresh + publish, `11:00` daily quiet publish, immediate after successful import, plus `14:01` to `17:11` every 10 minutes as a backstop
  - `07:00` source refresh order is strict:
    - `export_api_orders`
    - `validate_activeorders_columns`
    - `sync_kaspi_orders`
    - `enrich_kaspi_orders_from_activeorders`
    - Google Ops Board publish
  - publish runs use the quiet `publish` health profile: DB preflight + identity sync + Google board contract only
  - publish backstop must stay browser-silent; it does not open WhatsApp
  - publish fails closed when `excel_ui/ActiveOrders/ActiveOrders.xlsx` is stale for the target date
- Google Ops Board size writeback jobs: `17:15`, `17:30`, `17:45`, `18:00`, `18:15`
- Google Ops Board closeout keep-awake guard: `18:20`
  - runs `/usr/bin/caffeinate -dimsu -t 4200` so the Mac stays awake through the closeout/send window
- Google Ops Board early-closeout watch: every 15 seconds between `11:00` and `19:04` (script-gated, no-op unless green)
- early-ready safety gate: first `READY` detection arms a 60-second debounce; closeout starts only if the board is still green after that wait
- `18:57` edge-case fallback:
  - if any `SalesRaw_Today.MY_SIZE` cells are still blank, fill only those blanks from visible, valid `PROBABLE_SIZE`
  - if `PROBABLE_SIZE` is blank or invalid, do not infer a hidden size; leave the row unresolved and block closeout
  - preserve all manual sizes already entered
  - auto-set `Run_Control.ready_for_closeout = READY`
  - trigger closeout immediately if the board is then green
- once READY survives debounce, the watcher launches the closeout scheduler; the closeout script itself runs the full closeout health profile, including Kaspi store-context, Telegram delivery config, and WhatsApp smoke as warning-only fallback readiness
- manual closeout/send recovery reuses the same automation lock as scheduled closeout so we do not fork duplicate live runs
- WhatsApp chat safety now relies on the group title plus strong selected-row identifiers; subtitle drift is treated as diagnostic only
- Google Ops Board closeout backstop job: `18:30`
- closeout is checkpointed and resume-capable; later retries resume from the last safe green stage
- after successful delivery send, closeout runs the DB-only shipped-truth sync immediately; the `19:15` and next-day `09:30` jobs are fallback repairs if the Mac/API is unavailable
- physical courier handover is checked separately from Telegram PDF delivery:
  - after successful Telegram bundle delivery, a passive handover watcher is armed for one compact final check at `20:00`; it must not spam interval messages into the group
  - employee can press `Передал курьеру` or send `/handover_done`; bot waits `60s` and checks Kaspi `Передача` with a compact status
  - employee/owner can send `Передача` or `/handover_status` for an immediate compact read-only handover check
  - employee/owner can send `/hfull` for the full audit table when the compact status is not enough
  - the check is green only when no assembled `KASPI_DELIVERY / ACCEPTED_BY_MERCHANT` orders remain without `courierTransmissionDate` in the target/overdue window
  - if an order's PDF was sent in Telegram but Kaspi still shows no `courierTransmissionDate`, it remains operationally unshipped and must carry forward into the next `MERGED/SEND` batch until physically handed over
  - overdue carry-forward is based on merged per-order DB evidence, not one physical DB row: size and waybill evidence may be split across duplicate rows, while any `courierTransmissionDate` excludes the order from re-bundling
- owner Telegram alerts are low-noise:
  - prewindow green / red
  - closeout started / resumed
  - closeout failed / complete
- daily ops report job: `19:10`
  - read-only reporting; it must not be treated as the shipped-truth population job

Canonical business automation pause/resume:
- inspect current daily-ops automation state with `python3 scripts/manage_business_automation.py status --scope daily-ops`
- dry-run planned pauses/resumes before applying them
- real launchd mutation requires both `ENABLE_BUSINESS_AUTOMATION_CONTROL=1` and `--apply`
- frozen proof windows must pass `python3 scripts/manage_business_automation.py verify --scope daily-ops --expect paused`
- restored daily order processing must pass `python3 scripts/manage_business_automation.py verify --scope daily-ops --expect running`
- evidence is written under `exports/automation_control/`

Daily ops orchestrator profile contract:
- `today-fast` for strict current-day checks
- `catch-up` for overdue-inclusive recovery checks
Authority: `docs/ops/KASPI_DAILY_OPS_ORCHESTRATOR_RUNBOOK.md`

Daily report contract:
- `scripts/generate_daily_ops_report.py`
- `scripts/validate_daily_ops_report.py --strict`

Board V10 autopilot contract:
- `scripts/run_daily_autopilot.py --as-of <YYYY-MM-DD> --strict`
- exception queue output: `exports/exceptions/<YYYY-MM-DD>/exceptions.{json,md}`

Run strict validation with workbook anchor enabled before operator decisions:

```bash
AB_CRM_WORKBOOK_PATH="config/anchors/SALES_KSP_CRM_LATEST.xlsx" \
AB_INBOUND_WORKBOOK_PATH="config/anchors/INBOUND_CALENDAR_LATEST.xlsx" \
./.venv/bin/python scripts/validate_params.py --strict
```

Notes:
- `AB_CRM_WORKBOOK_PATH` gate is optional by design; if unset, workbook anchor check is skipped.
- In production operations, set it explicitly so daily published sales truth cannot exceed workbook anchor tolerance.
- Content freshness guard also enforces workbook max-date lag/future windows:
  - `AB_CRM_WORKBOOK_MAX_LAG_DAYS` (default `1`)
  - `AB_CRM_WORKBOOK_MAX_FUTURE_CONTENT_DAYS` (default `0`)
- Canonical workbook location is `excel_ui/SALES_KSP_CRM_V3.xlsx`;
  `config/anchors/SALES_KSP_CRM_LATEST.xlsx` must symlink to that file.
- Canonical inbound/payment truth pointer is `config/anchors/INBOUND_CALENDAR_LATEST.xlsx`
  (or set `AB_INBOUND_WORKBOOK_PATH` directly).

---

## Morning Routine (9:00 AM)

### 1. Check System Health
```bash
# Verify database integrity
python scripts/test_schema.py

# Check current fact_sales state
sqlite3 db/app.db "SELECT COUNT(*), MIN(order_date), MAX(order_date) FROM fact_sales;"
```

### 1.1 Run strict daily preflight (fail closed)
Use the wrapper so workbook-anchor validation is mandatory for operator runs.

```bash
./.venv/bin/python scripts/run_strict_daily_preflight.py \
  --workbook "config/anchors/SALES_KSP_CRM_LATEST.xlsx" \
  --emit-lineage \
  --send-alert-on-fail \
  --ensure-business-insides
```

Behavior:
- Fails closed when workbook path is missing.
- Fails closed when workbook is stale (default max age: 36h, configurable).
- Fails closed when workbook mtime is in the future beyond allowed skew (default 120s).
- Fails closed when workbook **content** is stale beyond allowed lag (`AB_CRM_WORKBOOK_MAX_LAG_DAYS`, default `1` day).
- Auto-generates missing daily `BUSINESS_INSIDES_<as_of>.md` before strict validation.
- Business-insides auto-generation runs with `--strict-cogs` (unresolved COGS blocks publication).
- Runs `validate_params.py --strict`.
- Optionally emits lineage JSON under `exports/lineage/`.
- Emits drift pack artifact under `exports/validation/<YYYY-MM-DD>/single_truth_drift_pack.{md,json}` after strict PASS.
- If repo `.venv/bin/python` exists, preflight re-execs under it for deterministic dependencies.

### 1.1.1 Run deterministic ops status check
Run this before launchd smoke/manual starts to verify anchor health + scheduler validate-only together:

```bash
./.venv/bin/python scripts/ops_status.py --project-root .
```

Expected outcome:
- `OPS_STATUS PASS` with zero exit code.

### 1.2 Run on-delivery residual dry-run check
Run this daily before any write-side cashflow reconciliation:

```bash
./.venv/bin/python scripts/check_on_delivery_residuals.py \
  --since 2026-01-01 \
  --until "$(date +%F)"
```

Optional alert mode:

```bash
./.venv/bin/python scripts/check_on_delivery_residuals.py \
  --since 2026-01-01 \
  --until "$(date +%F)" \
  --send-alert
```
### 2. Download Today's Inventory
1. Use the canonical stock snapshot workbook:
   - `config/anchors/STOCK_SNAPSHOT_LATEST.xlsx`
   - Current single-truth source: `excel/stock_snapshot_19.2.2026.xlsx`
2. Previous `excel/Current_stock_*.xlsx` snapshots are deprecated (contaminated).
3. Sync stock snapshot column + inbound transit truth:

```bash
# Dry-run (default)
python3 scripts/sync_current_stock.py

# Apply to DB (guarded)
ENABLE_STOCK_SNAPSHOT_WRITE=1 python3 scripts/sync_current_stock.py --apply
```

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
1. Parameters match Master_Inventory_Rules_v9.md
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
excel_ui/run_merged_build_waybills.command  -- Build waybill bundles
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
Double-click: excel_ui/run_merged_build_waybills.command

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
- [ ] Run builder: `run_merged_build_waybills.command`
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
2. Fill `SalesRaw_Today.MY_SIZE` in the Google Ops Board
3. Set `Run_Control.ready_for_closeout=READY` when the sizing batch is complete
4. If the board is fully green earlier, the minute-level watch arms a 60-second safety debounce and then starts closeout automatically if the board is still green; `18:30` remains only a backstop, and the watch still stays active through `19:04` for late READY or `18:57` visible `PROBABLE_SIZE` copy-only recovery

### Step 1: Ship Orders via API

Sets "Количество мест" (package count) and moves orders from "Упаковка" to "Передача".

```bash
# Full run with output
python scripts/ship_orders_api.py --verbose

# Automated closeout path (DB-first, no workbook dependency)
python scripts/ship_orders_api.py --selection-source db --verbose

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

Downloads waybill PDFs for TODAY's batch only (exact date match) unless overdue is included.

```bash
# Download today's waybills
python scripts/download_waybills_api.py --verbose

# Dry run (preview only)
python scripts/download_waybills_api.py --dry-run

# Specific date
python scripts/download_waybills_api.py --date 2025-12-10

# All historical orders (not just today)
python scripts/download_waybills_api.py --all-dates

# Include overdue orders (planned_date <= today, bounded by lookback)
python scripts/download_waybills_api.py --include-overdue
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
- Use `--include-overdue` for `planned_date <= today` (bounded by lookback)
- Use `--all-dates` for `planned_date <= today` with no lower bound

### Step 3: Build Waybill Bundles

Groups PDFs by store and type. Same as Phase 11, but uses API-downloaded waybills.
When overdue is included, output is split into:
`excel_ui/Kaspi_orders/Today/TODAY/` and `excel_ui/Kaspi_orders/Today/OVERDUE/`.

```bash
python scripts/build_daily_waybills.py --verbose
```

**Waybill Sources (priority order):**
1. API downloads: `excel_ui/ActiveOrders/waybills/*.pdf`
2. ZIP files: `excel_ui/ActiveOrders/waybill*.zip`

### Step 4: Archive and Retention Rules (Current Policy)

`excel_ui/run_merged_build_waybills.command` now calls `scripts/archive_waybill_inputs.py` after build.

**Archive scope:**
- Local run archive (`excel_ui/Archive/input_*`) includes:
- CRM workbook snapshot
- only selected-order waybill PDFs from the current selection cache
- optional `waybill*.zip` inputs
- It does **not** copy the full historical `ActiveOrders/waybills` cache each run.

**Retention:**
- Local waybill cache retention: 30 days
- Local run archive retention: 14 days

**Cold storage (External_database):**
- Old local cache PDFs are migrated to:
- `<EXTERNAL_DB_ROOT>/Autonomous_business/kaspi_waybills/by_order/{order_id}.pdf`
- Deduplication is by order ID filename, so shipped waybill PDFs are never duplicated.

**Workbook backups:**
- Google Drive backup remains workbook-only per run.
- External_database also receives workbook snapshots under:
- `.../Autonomous_business/kaspi_waybills/workbooks/`

**Google Drive snapshot rule:**
- `repo_backups_G/External_database/snapshots/*` must not include
  `Autonomous_business/kaspi_waybills/by_order/` PDFs.
- Source of truth for by-order waybill PDFs is local External_database:
  `<EXTERNAL_DB_ROOT>/Autonomous_business/kaspi_waybills/by_order/`

**Config env vars:**
- `KASPI_WAYBILL_CACHE_RETENTION_DAYS` (default `30`)
- `KASPI_ARCHIVE_RETENTION_DAYS` (default `14`)
- `KASPI_EXTERNAL_DB_ROOT`
- `KASPI_EXTERNAL_DB_REPO_LABEL` (default `Autonomous_business`)

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

### Single-Truth Hardening Jobs (21:00/21:05 local)

Install/update schedulers:

```bash
chmod +x scripts/install_single_truth_ops_scheduler.sh
./scripts/install_single_truth_ops_scheduler.sh
```

Anchor workbook paths (symlinks):

```bash
REPO_PATH="$(pwd)"
CRM_SOURCE_PATH="$REPO_PATH/excel_ui/SALES_KSP_CRM_V3.xlsx"
INBOUND_SOURCE_PATH="<set from config/anchors/README.md>"
ln -sfn "$CRM_SOURCE_PATH" "$REPO_PATH/config/anchors/SALES_KSP_CRM_LATEST.xlsx"
ln -sfn "$INBOUND_SOURCE_PATH" "$REPO_PATH/config/anchors/INBOUND_CALENDAR_LATEST.xlsx"
```

Jobs:
- `com.example.single-truth-preflight` (21:00): runs strict preflight with lineage output and auto-generates missing daily `BUSINESS_INSIDES`.
- `com.example.on-delivery-residuals` (21:05): runs residual dry-run and sends alert when residuals exist.

Manual trigger:

```bash
launchctl start com.example.single-truth-preflight
launchctl start com.example.on-delivery-residuals
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
