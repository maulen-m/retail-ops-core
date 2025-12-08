# System Architecture

**Project:** Autonomous Inventory/PO System
**Version:** 4.0 (Phase 9.6)
**Updated:** 2025-12-09

---

## Overview

This system automates inventory management for a multi-channel retail operation on Kaspi.kz and Wildberries (WB), selling clothing (CL), belts (ELS), and furs (FUR). It provides demand forecasting, safety stock calculation, automatic PO generation, portfolio analytics, and cross-channel optimization.

---

## Architecture Diagram

```
     ┌─────────────────┐                  ┌─────────────────┐
     │   Kaspi.kz      │                  │   Wildberries   │
     │  Excel Exports  │                  │  Excel Exports  │
     └────────┬────────┘                  └────────┬────────┘
              │                                    │
              └──────────────┬─────────────────────┘
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
│ wb, inv)  │         │           │         │           │
└───────────┘         └─────┬─────┘         └───────────┘
                            │
    ┌───────────────────────┼───────────────────────────┐
    │             │         │         │                 │
    ▼             ▼         ▼         ▼                 ▼
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────────┐
│Forecast │ │Inventory│ │Portfolio│ │ Channel │ │ Expansion │
│ Engine  │ │  Calc   │ │Analytics│ │ Metrics │ │  Scorer   │
└────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └─────┬─────┘
     │           │           │           │            │
     └───────────┴───────┬───┴───────────┴────────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
     ┌───────────────────┐  ┌───────────────────┐
     │    Auto-PO        │  │    Transfer       │
     │   Generator       │  │   Recommender     │
     └─────────┬─────────┘  └─────────┬─────────┘
               │                      │
               └──────────┬───────────┘
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
│   ├── config/                # Centralized configuration (Phase 9.6)
│   │   └── inventory_params.py # Inventory parameters dataclass
│   ├── calc/                  # Calculation modules
│   │   ├── __init__.py        # Module exports
│   │   ├── economics.py       # Kaspi revenue, COGS, profit
│   │   ├── wb_economics.py    # WB revenue, fees, profit (Phase 8)
│   │   ├── inventory.py       # SS, ROP, ROIC, order qty
│   │   ├── size_allocation.py # Size-aware PO allocation (Phase 9.6)
│   │   ├── forecast.py        # Demand forecasting
│   │   ├── forecast_accuracy.py # MAPE, bias, backtest
│   │   ├── dow_patterns.py    # Day-of-week patterns
│   │   ├── portfolio.py       # Portfolio analytics
│   │   ├── status.py          # Inventory status logic
│   │   ├── channel_metrics.py # Per-channel metrics (Phase 8)
│   │   ├── channel_comparison.py # Cross-channel comparison (Phase 8)
│   │   ├── expansion_scorer.py # WB expansion scoring (Phase 8)
│   │   └── transfer_recommender.py # Inventory transfer (Phase 8)
│   ├── parsers/
│   │   ├── kaspi_parser.py    # Kaspi Excel parser
│   │   └── wb_parser.py       # WB Excel parser (Phase 8)
│   ├── alerts/
│   │   └── telegram.py        # Telegram notifications
│   ├── automation/
│   │   └── po_generator.py    # Auto-PO generation
│   ├── validation/
│   │   └── data_quality.py    # Anomaly detection
│   ├── db/                    # Database module (refactored)
│   │   ├── __init__.py        # Connection helpers
│   │   └── queries.py         # Size-level data queries (Phase 9.6)
│   └── logging_config.py      # Logging configuration
├── scripts/                   # CLI tools
│   ├── Ingestion
│   │   ├── ingest_active_orders.py
│   │   ├── ingest_inventory_snapshot.py
│   │   ├── ingest_channel_sales.py  # Unified Kaspi/WB ingestion (Phase 8)
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
│   ├── Validation (Phase 9.6)
│   │   ├── validate_size_allocation.py  # 7 validation checks
│   │   └── compare_old_vs_new_allocation.py  # Allocation comparison
│   ├── Multi-Channel (Phase 8)
│   │   ├── build_channel_metrics.py  # Daily channel metrics
│   │   ├── run_expansion_analysis.py # WB expansion scoring
│   │   └── run_transfer_analysis.py  # Cross-channel transfers
│   ├── Orchestration
│   │   ├── run_daily_pipeline.py
│   │   └── send_daily_digest.py
│   └── Infrastructure
│       ├── health_check.py
│       ├── backup_db.py
│       └── bootstrap_db.py
├── db/
│   ├── schema.sql             # Database schema (38 tables)
│   └── app.db                 # SQLite database
├── tests/                     # Test suite (556+ tests)
│   ├── test_economics.py
│   ├── test_inventory.py
│   ├── test_status.py
│   ├── test_forecast.py
│   ├── test_portfolio.py
│   ├── test_data_quality.py
│   ├── test_integration.py
│   ├── test_wb_economics.py   # WB economics (Phase 8)
│   ├── test_channel_metrics.py # Channel metrics (Phase 8)
│   ├── test_expansion_scorer.py # Expansion scoring (Phase 8)
│   ├── test_size_allocation.py # Size allocation (Phase 9.6) - 86 tests
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
| `dim_store` | Store locations | store_code, channel |
| `dim_channel` | Channel config (Phase 8) | channel_code, commission_pct, logistics_fee |
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
| `fact_channel_metrics` | Per-channel metrics (Phase 8) | sku_key, channel_code, units_30d, roic |
| `fact_channel_inventory` | Channel stock levels (Phase 8) | sku_key, channel_code, on_hand, days_cover |
| `fact_expansion_scores` | WB expansion scores (Phase 8) | sku_key, expansion_score, recommendation |

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
apply_size_splits(sku_key, total_qty, db_path) -> dict  # Legacy
generate_po_draft(db_path, trigger, sku_filter) -> int
generate_po_draft_size_aware(sku_key, store_code, db_path) -> PODraft  # Phase 9.6
calc_confidence_score(sku_key, order_qty, ...) -> float
```

### size_allocation.py (Phase 9.6)

True size-level allocation with guardrails and ROIC gate.

```python
# Enums
OrderStatus: REORDER, WAIT, OK
ROICAction: ORDER_FULL, ORDER_WITH_FLAG, REVIEW_REQUIRED
DemandConfidence: ACTUAL, MARGINAL, FALLBACK, NO_DATA

# Demand
calc_d_sku_with_oos_filter(sales_history, stock_history) -> tuple[float, int, DemandConfidence]
calc_size_mix_with_guardrails(size_sales, min_mix=0.03, max_mix=0.40) -> dict[str, float]

# Safety Stock
calc_safety_stock_for_size(d_size, sigma_sku, size_mix, ...) -> tuple[5 floats]
calc_rop_for_size(d_size, ss_total, L) -> float
calc_t_post_for_size(d_size, ss_total, R) -> float

# Status
calc_pre_arrival_stock(current_stock, inbound_stock, d_size, days) -> float
calc_status_for_size(current_stock, total_stock, rop) -> OrderStatus
should_generate_po(size_statuses) -> tuple[bool, list[str]]

# Allocation
calc_order_qty_for_size(d_size, t_post, pre_arrival_stock) -> int
adjust_for_new_sku(order_qty, sku_age_days) -> tuple[int, float]
apply_low_demand_insurance(allocations, demands, mixes, total_qty) -> dict

# ROIC
calc_roic(d_sku, ss_total, unit_cogs, unit_profit, L, R) -> float
apply_roic_gate(roic, order_qty) -> tuple[ROICAction, int]

# Main Generator
generate_po_draft(...) -> PODraft
```

### inventory_params.py (Phase 9.6)

Centralized inventory parameters as frozen dataclass.

```python
@dataclass(frozen=True)
class InventoryParams:
    L: int = 21        # Lead time (days)
    R: int = 10        # Review period (days)
    B: int = 14        # Buffer days
    z: float = 1.65    # Service level (95%)
    TV: float = 0.23   # Size mix variability
    sigma_factor: float = 0.4
    min_size_mix: float = 0.03   # 3% floor
    max_size_mix: float = 0.40   # 40% cap
    roic_full_approval: float = 0.20    # 20% threshold
    roic_flag_threshold: float = 0.10   # 10% threshold
    new_sku_30d_factor: float = 0.75
    new_sku_60d_factor: float = 0.85
    new_sku_90d_factor: float = 0.95

get_params() -> InventoryParams  # Singleton pattern
```

### wb_economics.py (Phase 8)

WB-specific economics calculations.

```python
calc_wb_net_revenue(seller_price_rub, fx_rub_kzt, logistics_fee_rub, commission_pct, tax_pct) -> tuple
calc_wb_profit(seller_price_rub, cogs_kzt, ...) -> float
calc_wb_breakeven_price(cogs_kzt, target_margin_pct, ...) -> float
compare_kaspi_vs_wb(kaspi_price_kzt, wb_price_rub, cogs_kzt, ...) -> dict
```

### channel_metrics.py (Phase 8)

Per-channel metrics calculations.

```python
calc_channel_metrics_for_date(db_path, metric_date) -> list[ChannelMetrics]
save_channel_metrics(db_path, metrics) -> int
get_latest_channel_metrics(db_path, sku_key, channel_code) -> ChannelMetrics
```

### expansion_scorer.py (Phase 8)

Score SKUs for WB expansion potential.

```python
score_sku_for_expansion(db_path, sku_key, target_channel) -> ExpansionScore
score_all_skus_for_expansion(db_path, source_channel, target_channel) -> list
# Returns recommendation: EXPAND, TEST, HOLD, SKIP
```

### transfer_recommender.py (Phase 8)

Recommend inventory transfers between channels.

```python
recommend_transfers(db_path, min_days_cover, max_days_cover) -> list[TransferRecommendation]
get_critical_imbalances(db_path) -> list[TransferRecommendation]
get_transfer_summary(recommendations) -> dict
```

---

## Data Flow

### Daily Pipeline

1. **Ingest** - Parse Kaspi/WB Excel exports
2. **Transform** - Calculate economics (COGS, NetRev, Profit)
3. **Aggregate** - Build daily summaries
4. **Calculate** - Compute D30, SS, ROP, ROIC
5. **Forecast** - Generate demand predictions
6. **Capital Snapshot** - Build capital allocation
7. **Channel Metrics** - Build per-channel metrics (Phase 8)
8. **Alert** - Send Telegram notifications
9. **Export** - Generate reports and PO suggestions

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

5. **WB Economics (Phase 8)**
   - Commission: 24.5% (clothing category)
   - Logistics: 408₽ per unit (proxy)
   - Tax: 3% (Kazakhstan)
   - FX: 6.6 RUB/KZT

6. **Expansion Scoring (Phase 8)**
   - Demand score: 40% weight (based on units_30d)
   - Margin score: 40% weight (WB margin vs Kaspi)
   - Competition score: 20% weight (competitor count)
   - Recommendations: EXPAND (75+), TEST (50-74), HOLD (30-49), SKIP (<30)

7. **Size-Aware Allocation (Phase 9.6)**
   - OOS-filtered demand: Excludes stockout days from calculation
   - Size mix guardrails: 3% floor, 40% cap
   - Demand confidence uplifts: MARGINAL (1.2×), FALLBACK (1.5×)
   - ANY-size REORDER: Single size triggers whole SKU PO
   - New SKU factors: 0.75 (<30d), 0.85 (30-60d), 0.95 (60-90d)
   - Low demand insurance: D < 0.1 AND mix ≥ 5% → add 1% of PO

8. **ROIC Gate (Phase 9.6)**
   - ORDER_FULL: ROIC ≥ 20% (auto-approve)
   - ORDER_WITH_FLAG: 10-20% ROIC (approve with review)
   - REVIEW_REQUIRED: < 10% ROIC (manual approval needed)

---

## Performance

- Database: SQLite (single file, ~10MB)
- Tests: 556+ tests in ~1.2 seconds (86 new Phase 9.6 tests)
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
- Full WB tariff integration (per-SKU, per-warehouse fees)
- Container fill optimizer for multi-channel shipments
