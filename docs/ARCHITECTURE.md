# System Architecture

**Project:** Autonomous Inventory/PO System
**Version:** 2.0 (Phase 6)
**Updated:** 2025-12-06

---

## Overview

This system automates inventory management for a Kaspi.kz retail operation selling clothing (CL), belts (ELS), and furs (FUR). It provides demand forecasting, safety stock calculation, automatic PO generation, and portfolio analytics.

---

## Architecture Diagram

```
                    ┌─────────────────┐
                    │   Kaspi.kz      │
                    │  Excel Exports  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   Ingestion     │
                    │   Pipeline      │
                    └────────┬────────┘
                             │
    ┌────────────────────────┼────────────────────────┐
    │                        │                        │
    ▼                        ▼                        ▼
┌───────────┐         ┌───────────┐         ┌───────────┐
│ Parsers   │         │  Database │         │  Alerts   │
│ (kaspi,   │ ──────► │ (SQLite)  │ ◄────── │ (Telegram)│
│ inventory)│         │           │         │           │
└───────────┘         └─────┬─────┘         └───────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
    ┌─────────┐       ┌─────────┐       ┌─────────┐
    │Forecast │       │Inventory│       │Portfolio│
    │ Engine  │       │  Calc   │       │Analytics│
    └────┬────┘       └────┬────┘       └────┬────┘
         │                 │                 │
         └────────────┬────┴────┬────────────┘
                      │         │
                      ▼         ▼
               ┌───────────────────┐
               │    Auto-PO        │
               │   Generator       │
               └─────────┬─────────┘
                         │
                         ▼
               ┌───────────────────┐
               │  Reports/Exports  │
               └───────────────────┘
```

---

## Directory Structure

```
Autonomous_business/
├── core/                      # Core business logic
│   ├── calc/                  # Calculation modules
│   │   ├── __init__.py        # Module exports
│   │   ├── economics.py       # Revenue, COGS, profit
│   │   ├── inventory.py       # SS, ROP, ROIC, order qty
│   │   ├── forecast.py        # Demand forecasting
│   │   ├── forecast_accuracy.py # MAPE, bias, backtest
│   │   ├── dow_patterns.py    # Day-of-week patterns
│   │   ├── portfolio.py       # Portfolio analytics
│   │   └── status.py          # Inventory status logic
│   ├── parsers/
│   │   └── kaspi_parser.py    # Kaspi Excel parser
│   ├── alerts/
│   │   └── telegram.py        # Telegram notifications
│   ├── automation/
│   │   └── po_generator.py    # Auto-PO generation
│   ├── validation/
│   │   └── data_quality.py    # Anomaly detection
│   ├── db.py                  # Database helpers
│   └── logging_config.py      # Logging configuration
├── scripts/                   # CLI tools
│   ├── Ingestion
│   │   ├── ingest_active_orders.py
│   │   ├── ingest_inventory_snapshot.py
│   │   └── import_historical_sales.py
│   ├── Transformation
│   │   ├── import_legacy_sales.py
│   │   └── build_daily_aggregates.py
│   ├── Calculation
│   │   ├── run_sku_metrics.py
│   │   ├── run_forecast_engine.py
│   │   └── run_forecast_backtest.py
│   ├── Automation
│   │   ├── run_auto_po.py
│   │   ├── po_approval_cli.py
│   │   └── expire_po_drafts.py
│   ├── Reporting
│   │   ├── export_po_suggestions.py
│   │   ├── export_executive_summary.py
│   │   ├── report_dow_analysis.py
│   │   ├── report_stockout_costs.py
│   │   ├── report_data_quality.py
│   │   └── report_po_analytics.py
│   ├── Orchestration
│   │   ├── run_daily_pipeline.py
│   │   └── send_daily_digest.py
│   └── Infrastructure
│       ├── health_check.py
│       ├── backup_db.py
│       └── bootstrap_db.py
├── db/
│   ├── schema.sql             # Database schema (34 tables)
│   └── app.db                 # SQLite database
├── tests/                     # Test suite (201 tests)
│   ├── test_economics.py
│   ├── test_inventory.py
│   ├── test_status.py
│   ├── test_forecast.py
│   ├── test_portfolio.py
│   ├── test_data_quality.py
│   ├── test_integration.py
│   └── ...
├── docs/
│   ├── ARCHITECTURE.md        # This file
│   ├── DAILY_SOP.md           # Daily operations guide
│   └── protocol/              # Business rules
├── exports/                   # Generated reports
├── reports/                   # Analysis outputs
├── logs/                      # Application logs
└── .claude/                   # Agent instructions
    ├── TASKS.md               # Task queue
    ├── DECISIONS.md           # Architecture decisions
    └── ISSUES.md              # Known issues
```

---

## Database Schema

### Dimension Tables (dim_*)

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `dim_sku` | Product master | sku_key, product_type, base_cost_cny |
| `dim_sku_size` | Size variants | sku_id, sku_key, my_size |
| `dim_store` | Store locations | store_code, store_name |
| `dim_seasonality` | Seasonal multipliers | month, product_type, multiplier |
| `dim_sku_lifecycle` | SKU lifecycle status | sku_key, lifecycle_status |

### Fact Tables (fact_*)

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `fact_sales` | Processed transactions | order_id, sku_id, quantity, cogs, profit |
| `fact_sales_daily` | Daily aggregates by SKU | sale_date, sku_key, units, revenue |
| `fact_sales_daily_size` | Daily aggregates by size | sale_date, sku_id, units |
| `fact_inventory_snapshot_size` | Current stock levels | sku_id, current_stock |
| `fact_sku_metrics` | Calculated metrics | sku_key, d30, ss_total, rop, roic_monthly |
| `fact_demand_forecast` | Demand predictions | forecast_date, sku_key, predicted_units |
| `fact_forecast_accuracy` | Forecast accuracy | sku_key, mape, bias |
| `fact_stockout_events` | Stockout tracking | sku_key, stockout_date, lost_sales |
| `fact_po_draft` | PO drafts | draft_id, total_qty, confidence_score |
| `fact_po_draft_lines` | PO line items | draft_id, sku_key, quantity, size_qty |
| `fact_po_execution` | PO execution tracking | po_id, ordered_qty, received_qty |
| `fact_alert_log` | Alert history | sku_key, alert_type, sent_at |

---

## Core Modules

### economics.py

Calculates financial metrics per transaction.

```python
calc_delivery_fee(sell_price_kzt) -> float
calc_cogs(base_cost_cny, weight_kg, ...) -> float
calc_net_rev(sell_price_kzt, quantity, ...) -> float
calc_profit(sell_price_kzt, quantity, efficiency) -> float
```

### inventory.py

Safety stock and reorder point calculations.

```python
calc_d30(total_units, period_days) -> float
calc_sigma(d30, volatility_factor) -> float
calc_ss_total(d30, L, R, z, B, TV) -> float
calc_rop(d30, L, ss_total) -> float
calc_roic(d30, profit_unit, cogs_unit, ...) -> float
calc_rop_v2(d_forecast, trend_slope, sigma, ...) -> float
```

### forecast.py

Demand forecasting with trend adjustment.

```python
calc_weighted_demand(daily_sales, decay_factor) -> float
calc_trend_slope(daily_sales) -> float
calc_d_forecast(daily_sales, horizon_days) -> float
calc_confidence_interval(daily_sales, forecast) -> tuple
apply_seasonality(forecast, month, product_type) -> float
```

### portfolio.py

Portfolio-level analytics.

```python
calc_portfolio_roic(db_path) -> dict
identify_kill_candidates(db_path, roic_threshold) -> list
check_concentration_rule(proposed_po, ..., max=0.20) -> dict
recommend_lifecycle_status(roic, trend, d30) -> str
```

### po_generator.py

Automatic PO generation.

```python
calc_order_quantity(sku_key, current_stock, rop, ...) -> int
apply_size_splits(sku_key, total_qty, db_path) -> dict
generate_po_draft(db_path, trigger, sku_filter) -> int
calc_confidence_score(sku_key, order_qty, ...) -> float
```

---

## Data Flow

### Daily Pipeline

1. **Ingest** - Parse Kaspi Excel exports
2. **Transform** - Calculate economics (COGS, NetRev, Profit)
3. **Aggregate** - Build daily summaries
4. **Calculate** - Compute D30, SS, ROP, ROIC
5. **Forecast** - Generate demand predictions
6. **Alert** - Send Telegram notifications
7. **Export** - Generate reports and PO suggestions

### Auto-PO Flow

1. Check SKUs where `current_stock < ROP`
2. Calculate order quantity: `target_stock - current_stock`
3. Apply size splits based on historical sales mix
4. Calculate confidence score
5. Create draft PO if confidence > threshold
6. Wait for human approval
7. Track execution (ordered vs received)

---

## Configuration

### Environment Variables (.env)

```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Default Parameters (inventory.py)

```python
DEFAULT_PARAMS = {
    "L": 21,      # Lead time (days)
    "R": 10,      # Review period (days)
    "z": 1.65,    # Service level (95%)
    "B": 14,      # Buffer days
    "TV": 0.23,   # Size mix variability
}
```

---

## Key Business Rules

1. **3-State Inventory Status**
   - REORDER: total_stock < ROP
   - WAIT: current_stock < ROP but inbound covers
   - OK: current_stock >= ROP

2. **20% Concentration Rule**
   - No single SKU can exceed 20% of total capital

3. **Lifecycle States**
   - GROW: High ROIC + positive trend
   - MAINTAIN: Medium ROIC or high ROIC declining
   - HARVEST: Low ROIC with demand
   - KILL: Negative ROIC or no demand

4. **24-Hour Alert Cooldown**
   - Same SKU alert only once per 24 hours

---

## Performance

- Database: SQLite (single file, ~10MB)
- Tests: 201 tests in ~0.6 seconds
- Forecast: Covers 2+ SKUs with 7-day history
- Backup: 85%+ compression with gzip

---

## Dependencies

```
Python 3.11+
├── pandas          # Data processing
├── openpyxl        # Excel parsing
├── requests        # Telegram API
├── pyyaml          # Configuration
└── pytest          # Testing
```

---

## Future Enhancements

- Machine learning forecast models
- Multi-supplier integration
- Real-time Kaspi API connection
- Mobile app for PO approval
- Automated supplier ordering
