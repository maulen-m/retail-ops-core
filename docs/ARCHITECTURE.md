# System Architecture

**Project:** Autonomous Inventory/PO System
**Version:** 5.0 (Phase 10)
**Updated:** 2025-12-10

---

## Overview

This system automates inventory management for a **Kaspi-only** retail operation (CL/ELS/FUR). It provides demand forecasting, safety stock calculation, automatic PO generation, portfolio analytics, and PO lifecycle management.

## Single-Truth Path (PO, Inventory, Cashflow)

The operational truth chain is enforced as:

1. `fact_inventory_snapshot_size` message-date baseline (latest snapshot on or before row message date).
2. PO dashboard generation (`scripts/generate_po_dashboard_data.py`) computes PLAN and REAL_ARCHIVE rows from canonical math and DB facts.
3. REAL PO archive/lifecycle is part-grain when `po_part` exists (`po_part_id` keys in `archived_pos` and `real_pos`).
4. Inbound payment truth is sourced from `po_part` (`is_paid_base`, `is_paid_dlv`, `to_pay_*`) loaded from `PO_part_id_Totals`.
5. Cashflow paid-capital view is anchored to bank cash + paid inventory components only.
3. Dashboard validators (`scripts/validate_po_dashboard_invariants.py`, `scripts/validate_single_truth_alignment.py`) assert PLAN/REAL separation, qty identity vs `po_line`, and formula consistency.
6. Cashflow and inventory gates (`scripts/validate_cashflow_invariants.py`, `scripts/validate_inventory_cost_drift.py`) must remain aligned with the same underlying facts.

Rules:
- `PLAN-*` rows are recommendations only.
- Non-PLAN rows in dashboard `pos` are `po_kind="REAL_ARCHIVE"` and are recomputed from real PO timeline state.
- DOC presentation uses half-up rounding to 1 decimal across PLAN and REAL_ARCHIVE output.

---

## Architecture Diagram

```
     ┌─────────────────┐
     │   Kaspi.kz      │
     │  Excel Exports  │
     └────────┬────────┘
              │
              ▼
     ┌───────────────────┐
     │   Ingestion       │
     │   Pipeline        │
     └────────┬──────────┘
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
    ┌───────────────────────┼───────────────────────────────┐
    │         │             │         │           │         │
    ▼         ▼             ▼         ▼           ▼         ▼
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│Forecast │ │Inventory│ │Portfolio│ │ Channel │ │ Stock   │ │   PO    │
│ Engine  │ │  Calc   │ │Analytics│ │ Metrics │ │ Ledger  │ │Lifecycle│
└────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
     │           │           │           │           │           │
     └───────────┴───────────┴─────┬─────┴───────────┴───────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
     ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
     │    Auto-PO        │  │    Transfer       │  │   Landed Cost     │
     │   Generator       │  │   Recommender     │  │   Calculator      │
     └─────────┬─────────┘  └─────────┬─────────┘  └─────────┬─────────┘
               │                      │                      │
               └──────────────────────┼──────────────────────┘
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
│   │   ├── economics.py       # Kaspi revenue, fees, profit
│   │   ├── inventory.py       # SS, ROP, ROIC, order qty
│   │   ├── size_allocation.py # Size-aware PO allocation (Phase 9.6)
│   │   ├── forecast.py        # Demand forecasting
│   │   ├── forecast_accuracy.py # MAPE, bias, backtest
│   │   ├── dow_patterns.py    # Day-of-week patterns
│   │   ├── portfolio.py       # Portfolio analytics
│   │   ├── status.py          # Inventory status logic
│   │   ├── landed_cost.py     # Landed cost calculator (Phase 10)
│   │   └── demand_estimator.py # Anchor blending, OOS detection (Phase 13)
│   ├── parsers/
│   │   ├── kaspi_parser.py    # Kaspi Excel parser
│   ├── ingest/                # Data ingestion modules (Phase 10)
│   │   └── sales_ingest.py    # Sales ingest with dedup
│   ├── po/                    # PO lifecycle management (Phase 10)
│   │   ├── lifecycle.py       # PO state machine
│   │   └── eta.py             # ETA calculation
│   ├── alerts/
│   │   └── telegram.py        # Telegram notifications
│   ├── automation/
│   │   └── po_generator.py    # Auto-PO generation
│   ├── validation/
│   │   └── data_quality.py    # Anomaly detection
│   ├── db/                    # Database module (refactored)
│   │   ├── __init__.py        # Connection helpers
│   │   ├── ledger.py          # Stock ledger operations (Phase 10)
│   │   └── queries.py         # Size-level data queries (Phase 9.6/10)
│   └── logging_config.py      # Logging configuration
├── scripts/                   # CLI tools
│   ├── Ingestion
│   │   ├── ingest_active_orders.py
│   │   ├── ingest_inventory_snapshot.py
│   │   ├── ingest_sales_v2.py       # Sales ingest with dedup (Phase 10)
│   │   └── import_historical_sales.py
│   ├── Transformation
│   │   ├── import_legacy_sales.py
│   │   ├── build_daily_aggregates.py
│   │   └── import_po_from_excel.py  # PO import from Inbound template (Phase 10)
│   ├── Calculation
│   │   ├── run_sku_metrics.py
│   │   ├── run_forecast_engine.py
│   │   └── run_forecast_backtest.py
│   ├── Automation
│   │   ├── run_auto_po.py
│   │   ├── po_approval_cli.py
│   │   ├── po_cli.py               # Full PO lifecycle CLI (Phase 10)
│   │   └── expire_po_drafts.py
│   ├── Reporting
│   │   ├── export_po_suggestions.py
│   │   ├── export_executive_summary.py
│   │   ├── report_dow_analysis.py
│   │   ├── report_stockout_costs.py
│   │   ├── report_data_quality.py
│   │   └── report_po_analytics.py
│   ├── Validation (Phase 9.6/10)
│   │   ├── validate_size_allocation.py  # 7 validation checks
│   │   ├── validate_ledger.py          # Stock ledger validation (Phase 10)
│   │   └── compare_old_vs_new_allocation.py  # Allocation comparison
│   ├── Stock Ledger (Phase 10)
│   │   ├── bootstrap_ledger.py      # Initialize stock from Excel
│   │   └── rebuild_snapshot.py      # Rebuild snapshot from ledger
│   ├── Orchestration
│   │   ├── run_daily_pipeline.py
│   │   ├── daily_pipeline_v2.py     # Ledger-integrated pipeline (Phase 10)
│   │   ├── sync_crm_to_db.py        # Daily CRM → sales_fact_v2 sync (scheduled 13:00 GMT+5)
│   │   └── send_daily_digest.py
│   └── Infrastructure
│       ├── health_check.py
│       ├── backup_db.py
│       └── bootstrap_db.py
├── db/
│   ├── schema.sql             # Database schema (38 tables)
│   └── app.db                 # SQLite database
├── tests/                     # Test suite (640+ tests)
│   ├── test_economics.py
│   ├── test_inventory.py
│   ├── test_status.py
│   ├── test_forecast.py
│   ├── test_portfolio.py
│   ├── test_data_quality.py
│   ├── test_integration.py
│   ├── test_size_allocation.py # Size allocation (Phase 9.6) - 86 tests
│   ├── test_stock_ledger.py   # Stock ledger operations (Phase 10) - 23 tests
│   ├── test_po_lifecycle.py   # PO lifecycle (Phase 10) - 19 tests
│   ├── test_eta_calc.py       # ETA calculation (Phase 10) - 17 tests
│   ├── test_landed_cost.py    # Landed cost (Phase 10) - 14 tests
│   ├── test_sales_ingest.py   # Sales ingest (Phase 10) - 18 tests
│   ├── test_queries_v2.py     # v2 queries (Phase 10) - 14 tests
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
| `fact_input_audit` | Audit trail (Phase 10) | table_name, record_id, change_type, old/new_value |

### Phase 10 Tables (Event-Sourced)

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `stock_ledger` | Event-sourced stock changes | event_date, event_type, sku_id, qty_change, running_balance |
| `sales_fact_v2` | Deduplicated sales records | order_id, sku_id, store_code, kaspi_offer_name, quantity |
| `po_header` | PO header records | po_id, supplier_code, status, arrival dates, fx rates, costs |
| `po_part` | Split-shipment PO parts | po_part_id, po_id, supplier_id, cargo_send_date, status, totals |
| `po_line` | PO line items | po_id, po_part_id, sku_id, order_qty, received_qty, unit_cost_cny |

**stock_ledger Event Types:**
- `INITIAL` - Bootstrap/opening balance
- `SALE` - Stock decrease from customer order
- `INBOUND` - Stock increase from PO arrival
- `RETURN` - Stock increase from customer return
- `ADJUSTMENT` - Manual stock correction (+/-)
- `WRITE_OFF` - Stock decrease from damage/loss

**po_header Status Flow:**
`DRAFT` → `SENT` → `PREPARING` → `SHIPPED_SELLER` → `SHIPPED_CARGO` → `IN_TRANSIT` → `ARRIVED_ALM` → `ARRIVED_AST` → `RECEIVED` → `CLOSED`

---

## Core Modules

### economics.py

Calculates financial metrics per transaction.

```python
calc_delivery_fee(sell_price_kzt, weight_kg=None, delivery_type="city") -> float
calc_cogs(base_cost_cny, weight_kg, ...) -> float
calc_net_rev(sell_price_kzt, delivery_fee=None, ...) -> float
calc_profit(sell_price_kzt, base_cost_cny, weight_kg, ...) -> float
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

### ledger.py (Phase 10)

Event-sourced stock tracking and audit logging.

```python
# Stock Ledger
add_ledger_event(event_type, sku_id, qty_change, event_date, ...) -> int  # ledger_id
get_stock_balance(sku_id, store_code, as_of_date) -> int
get_stock_balances_all(store_code, as_of_date) -> dict[str, int]
get_ledger_events(sku_id, event_type, start_date, end_date, limit) -> list[dict]
rebuild_snapshot_from_ledger(snapshot_date, store_code) -> int
count_ledger_events(event_type, sku_id, store_code) -> int
get_event_summary(as_of_date, store_code) -> dict

# Audit Logging
log_audit(table_name, record_id, field_name, old_value, new_value, change_type, source) -> int
get_audit_history(table_name, record_id, since, limit) -> list[dict]
count_audit_entries(table_name, record_id, change_type) -> int
get_audit_summary(table_name) -> dict
```

### lifecycle.py (Phase 10)

PO lifecycle state machine.

```python
generate_po_id() -> str  # Format: PO-YYYYMMDD-XXXX
create_po(supplier_code, status, notes, created_by, db_path) -> str  # po_id
add_po_line(po_id, sku_id, order_qty, unit_cost_cny, db_path) -> int  # po_line_id
update_po_field(po_id, field_name, value, db_path) -> bool
update_po_status(po_id, new_status, db_path) -> bool
confirm_po_arrival(po_id, arrival_type, arrival_date, db_path) -> dict  # Creates INBOUND events
close_po(po_id, db_path) -> bool
receive_po_line(po_line_id, received_qty, db_path) -> dict
get_po(po_id, db_path) -> dict
get_po_lines(po_id, db_path) -> list[dict]
list_pos(status, supplier_code, limit, db_path) -> list[dict]
```

### eta.py (Phase 10)

PO ETA calculation (L=21 days from ship_date_cargo).

```python
estimate_prep_days(supplier_code, db_path) -> int  # Default: 7
calc_eta(po_id, db_path) -> dict  # {eta, confidence, from_date, lead_time}
update_po_eta(po_id, db_path) -> bool
recalc_all_etas(db_path) -> int  # Number of POs updated
get_etas_by_status(status, db_path) -> list[dict]
```

### landed_cost.py (Phase 10)

Landed cost calculation (cargo rate: 2.66 USD/kg).

```python
calc_supplier_costs(po_id, fx_rate_cny_kzt, db_path) -> dict
calc_cargo_costs(po_id, weight_kg, cargo_rate_usd_kg, fx_rate_usd_kzt, db_path) -> dict
calc_landed_costs(po_id, db_path) -> dict
get_sku_landed_cost(sku_id, fx_rate_cny_kzt, weight_kg, cargo_rate_usd_kg, fx_rate_usd_kzt, db_path) -> dict
recalc_po_costs(po_id, db_path) -> dict
```

### sales_ingest.py (Phase 10)

Sales ingestion with deduplication.

```python
parse_sales_excel(xlsx_path) -> list[dict]
ingest_sales(records, store_code, create_ledger_events, db_path) -> dict
get_unmapped_offers(db_path) -> list[dict]
update_returns_from_api(updates, db_path) -> dict  # Creates RETURN events
normalize_store_code(raw_store) -> str
```

### queries.py v2 functions (Phase 10)

Query functions using Phase 10 tables.

```python
get_size_current_stock_v2(sku_key, store_code, db_path) -> dict[str, int]
get_size_inbound_v2(sku_key, store_code, db_path) -> dict[str, int]
get_size_sales_90d_v2(sku_key, store_code, db_path) -> dict[str, int]
get_size_sales_history_v2(sku_key, store_code, days, db_path) -> dict[str, list[int]]
get_size_stock_history_v2(sku_key, store_code, days, db_path) -> dict[str, list[int]]
get_sku_age_days_v2(sku_key, store_code, db_path) -> int
get_po_lines_for_sku(sku_key, status, db_path) -> list[dict]
get_stock_movement_summary(sku_key, store_code, days, db_path) -> dict
```

---

## Data Flow

### Daily Pipeline

1. **Ingest** - Parse Kaspi Excel exports
2. **Transform** - Calculate economics (COGS, NetRev, Profit)
3. **Aggregate** - Build daily summaries
4. **Calculate** - Compute D30, SS, ROP, ROIC
5. **Forecast** - Generate demand predictions
6. **Capital Snapshot** - Build capital allocation
7. **Alert** - Send Telegram notifications
8. **Export** - Generate reports and PO suggestions

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

5. **Size-Aware Allocation (Phase 9.6)**
   - OOS-filtered demand: Excludes stockout days from calculation
   - Size mix guardrails: 3% floor, 40% cap
   - Demand confidence uplifts: MARGINAL (1.2×), FALLBACK (1.5×)
   - ANY-size REORDER: Single size triggers whole SKU PO
   - New SKU factors: 0.75 (<30d), 0.85 (30-60d), 0.95 (60-90d)
   - Low demand insurance: D < 0.1 AND mix ≥ 5% → add 1% of PO

6. **ROIC Gate (Phase 9.6)**
   - ORDER_FULL: ROIC ≥ 20% (auto-approve)
   - ORDER_WITH_FLAG: 10-20% ROIC (approve with review)
   - REVIEW_REQUIRED: < 10% ROIC (manual approval needed)

7. **Event-Sourced Stock Tracking (Phase 10)**
   - All stock changes recorded as immutable events in `stock_ledger`
   - Balance = SUM(qty_change) for all events
   - Snapshot rebuilt from ledger on demand
   - Audit trail for all modifications in `fact_input_audit`

8. **PO Lifecycle State Machine (Phase 10)**
    - Status flow: DRAFT → SENT → PREPARING → SHIPPED_SELLER → SHIPPED_CARGO → IN_TRANSIT → ARRIVED_ALM → ARRIVED_AST → RECEIVED → CLOSED
    - INBOUND events created on arrival confirmation
    - Immutable fields: archive_alm_arrival, archive_ast_arrival (once set)
    - ETA calculation: L=21 days from ship_date_cargo

9. **Sales Deduplication (Phase 10)**
    - Dedup key: (order_id, sku_id, store_code, kaspi_offer_name)
    - Same order with different offers → separate records
    - SALE events created for each new sale
    - RETURN events created for returned items

10. **Landed Cost Calculation (Phase 10)**
    - Supplier cost: qty × unit_cost_cny × fx_rate_cny_kzt
    - Cargo cost: weight_kg × cargo_rate_usd_kg × fx_rate_usd_kzt
    - Default cargo rate: 2.66 USD/kg
    - Landed cost = Supplier cost + Cargo cost allocation

---

## Performance

- Database: SQLite (single file, ~10MB)
- Tests: 640+ tests in ~1.5 seconds (105 new Phase 10 tests)
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
- Container fill optimizer for shipments
