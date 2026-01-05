# DEPRECATED — archived in `docs/archive/Future_Phases_Roadmap.md`.

# Future Phases Roadmap — Project 3

**Purpose:** Track phase completion status and roadmap for Phases 6-10.  
**Last Updated:** 2025-12-06

---

## Phase Completion Status

| Phase | Name | Status | Completion Date | Key Deliverable |
|-------|------|--------|-----------------|-----------------|
| 0-5 | Excel Parity | ✅ COMPLETE | 2025-12-06 | Full pipeline matching Inventory_Core_V15 |
| 6 | Predictive Demand & Smart Safety Stock | ✅ COMPLETE | 2025-12-06 | Forecast engine, DOW patterns, Auto-PO |
| 6.5 | Sales Data Rebuild | ✅ COMPLETE | 2025-12-06 | Correct grain (order_id, kaspi_offer_name, sku_id, store_code) |
| 7 | Capital Allocation Optimizer | ✅ COMPLETE | 2025-12-06 | Lifecycle classifier, 20% rule, kill list |
| 8 | Multi-Channel Intelligence | ✅ COMPLETE | 2025-12-06 | Kaspi + WB unified model, expansion scorer |
| 9 | Supplier & Logistics Optimization | 📋 PLANNED | — | Supplier scorecard, container optimizer |
| 10 | Autonomous Operations | 📋 PLANNED | — | <2 hrs/week on routine POs |

---

## Phase Details

### Phase 6: Predictive Demand & Smart Safety Stock ✅

**Completed:** 2025-12-06  
**Tasks:** 41 (TASK-025 through TASK-065)  
**Tests Added:** 98 new tests (103 → 201 total)

**Key Capabilities:**
- Forecast engine with exponential decay weighting
- Day-of-week demand patterns
- Stockout detection and cost estimation
- Forecast accuracy tracking (MAPE, bias)
- Auto-PO generation with confidence scoring
- Data quality monitoring

**New Tables:**
- `dim_seasonality`
- `fact_demand_forecast`
- `dim_sku_lifecycle`
- `fact_stockout_events`
- `fact_forecast_accuracy`
- `fact_po_draft`, `fact_po_draft_lines`
- `fact_po_execution`
- `fact_system_metrics`

---

### Phase 7: Capital Allocation Optimizer ✅

**Completed:** 2025-12-06  
**Tasks:** 15 (TASK-070 through TASK-084)  
**Tests Added:** 25 new tests (218 → 243 total)

**Key Capabilities:**
- Daily capital snapshot per SKU
- Lifecycle classification (GROW/MAINTAIN/HARVEST/KILL)
- Portfolio ROIC optimization
- 20% concentration rule enforcement
- Kill list generator with recovery estimates
- Weekly portfolio review automation

**New Tables:**
- `fact_capital_allocation`
- `fact_portfolio_summary`

**ROI Signal:** +3-5% portfolio ROIC through capital reallocation

---

### Phase 8: Multi-Channel Intelligence ✅

**Completed:** 2025-12-06
**Tasks:** 19 (TASK-085 through TASK-103)
**Tests Added:** 57 new tests (243 → 300 total)

**Key Capabilities:**
- Unified Kaspi + WB data model with channel-agnostic SKU dimension
- WB economics calculator (24.5% commission, 408₽ logistics, 3% tax, RUB/KZT 6.6)
- Channel-specific metrics and 30-day rolling comparisons
- Expansion scorer for WB launch candidates (EXPAND/TEST/HOLD/SKIP)
- Transfer recommender for cross-channel inventory balancing
- Pipeline integration for daily channel metrics

**New Core Modules:**
- `core/calc/wb_economics.py` — WB fee structure and profit calculations
- `core/parsers/wb_parser.py` — Parse WB sales exports
- `core/calc/channel_metrics.py` — Daily and rolling metrics per channel
- `core/calc/channel_comparison.py` — Cross-channel SKU comparison
- `core/calc/expansion_scorer.py` — Score SKUs for WB expansion potential
- `core/calc/transfer_recommender.py` — Inventory transfer recommendations

**New Scripts:**
- `scripts/migrate_010.py` — Multi-channel schema migration
- `scripts/ingest_channel_sales.py` — Unified ingestion (--channel KSP|WB)
- `scripts/build_channel_metrics.py` — Daily build with backfill
- `scripts/run_expansion_analysis.py` — CLI for expansion scoring
- `scripts/run_transfer_analysis.py` — CLI with Telegram alerts

**New Tables:**
- `dim_channel` — Channel configuration and fee structures
- `fact_channel_metrics` — Daily + rolling metrics per SKU per channel
- `fact_channel_inventory` — Stock levels per channel
- `fact_expansion_scores` — Expansion potential scores

**ROI Signal:** +2-4% margin through channel optimization

---

### Phase 9: Supplier & Logistics Optimization 📋

**Status:** Planned  
**Timeline:** ~4-6 weeks post Phase-8  
**Depends On:** Phase 8 complete, WB data flowing

**Planned Capabilities:**

| Feature | What It Does | ROI Signal |
|---------|--------------|------------|
| Supplier scorecard | Track lead time, quality, price variance | Best supplier selection |
| Container fill optimizer | Maximize CBM efficiency per shipment | -5-10% freight cost |
| FX hedge alerts | Warn on CNY/KZT, RUB/KZT moves >5% | Avoid FX surprises |
| Optimal order timing | Best day/week to place POs | Cash flow optimization |
| Full WB tariff integration | Per-SKU, per-warehouse logistics fees | Replace 408₽ proxy |

**New Tables (Planned):**
- `dim_supplier`
- `fact_supplier_performance`
- `fact_fx_rates`
- `fact_logistics_events`
- `dim_wb_warehouse` (WB warehouse-specific tariffs)

**ROI Signal:** -5-10% landed cost

---

### Phase 10: Autonomous Operations 📋

**Status:** Planned  
**Timeline:** ~8-12 weeks post Phase-8  
**Depends On:** Phases 8-9 complete, 3 months of validated decisions

**Planned Capabilities:**

| Feature | Automation Level | Human Role |
|---------|-----------------|------------|
| Auto-PO generation | Full | Approve/reject via Telegram |
| Auto-price adjustment | Within bounds (±10%) | Set bounds, review weekly |
| Anomaly detection | Continuous monitoring | Investigate flags |
| Self-tuning parameters | Quarterly recommendations | Review and approve |
| Multi-channel rebalancing | Suggested transfers | Approve execution |

**Approval Gates (never fully autonomous):**
- POs > $5,000 → require manual approval
- Price changes > 10% → require manual approval
- New SKU launches → always manual
- Supplier changes → always manual
- Channel expansion → always manual

**Target:** <2 hours/week on routine operations

---

## Dependency Map

```
Phases 0-5 (Foundation — Excel Parity) ✅
    ↓
Phase 6 (Predict) ✅ ←── requires 60+ days of clean fact_sales_daily
    ↓
Phase 7 (Allocate) ✅ ←── requires Phase 6 forecasts + capital tracking
    ↓
Phase 8 (Multi-channel) ✅ ←── unified Kaspi + WB model complete
    ↓
Phase 9 (Suppliers) ←── requires fact_po_lines with supplier tracking
    ↓
Phase 10 (Autonomous) ←── requires all above + 3 months of validated decisions
```

---

## Success Metrics by Phase

| Phase | Primary Metric | Target | Actual |
|-------|----------------|--------|--------|
| 0-5 | Excel parity | D₃₀ ±1%, ROIC ±2%, Status identical | ✅ Achieved |
| 6 | Forecast accuracy | MAPE <20% on 7-day forecast | ✅ Achieved |
| 7 | Capital efficiency | Portfolio ROIC +3% vs Phase-5 baseline | ✅ 241% portfolio ROIC |
| 8 | Channel optimization | Margin +2% through channel/price tuning | ✅ Infrastructure ready |
| 9 | Landed cost | -5% through supplier/logistics optimization | 📋 Planned |
| 10 | Operational leverage | <2 hrs/week on routine PO decisions | 📋 Planned |

---

## Current Data State

| Metric | Value | As Of |
|--------|-------|-------|
| fact_sales records | 13,050 | 2025-12-06 |
| Unique SKUs | 67 | 2025-12-06 |
| SKUs with COGS | 54 | 2025-12-06 |
| Historical days | 406+ | 2025-12-06 |
| Total tests | 334 | 2025-12-06 |
| Portfolio ROIC | 241.3% | 2025-12-06 |

---

## What This System Will NOT Do

Keeping scope clear prevents feature creep:

- ❌ Accounting/bookkeeping (use 1C or separate system)
- ❌ Customer service/returns management
- ❌ Marketing/advertising optimization (beyond basic WB ad cost tracking)
- ❌ New product sourcing/design
- ❌ Warehouse management (physical operations)
- ❌ Legal/compliance/tax filing

The system is purely: **demand sensing → capital allocation → purchase optimization → performance tracking**

---

## Changelog

| Date | Change |
|------|--------|
| 2025-12-06 | Created roadmap; marked Phases 0-7 complete |
| 2025-12-06 | Added Phase 8 spec reference |
| 2025-12-06 | Phase 8 complete; 19 tasks, 57 new tests, 6 core modules |

---

*Owner: Adil / Code Captain*
