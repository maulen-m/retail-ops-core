# CRM Operating Model V1
## Project 3 — Autonomous Inventory/PO System

**Created:** December 6, 2025  
**Phase:** 0-1 Bootstrap

---

## 1. System Purpose

Replace Excel V15's calculation logic with a Python/SQLite engine that:
- Ingests daily Kaspi/WB exports for 5 stores
- Computes identical D₃₀, σ, SS, ROP, ROIC, Status to Excel V15
- Produces size-split PO recommendations
- Sends Telegram alerts on REORDER status

**Excel remains as UI**. Python is the brain.

---

## 2. End-to-End Data Flow
```
┌─────────────────────┐
│  Kaspi Portal       │  Manual daily export
│  (5 stores)         │  ActiveOrders_[date].xlsx
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│  data_raw/          │  Raw files (read-only)
│  ActiveOrders/      │
└─────────┬───────────┘
          ▼ [run_daily_ingest.py]
┌─────────────────────┐
│  fact_sales_raw     │  Order-level grain
│  (order_id × sku_id │  Full Kaspi identifiers
│   × store_code)     │
└─────────┬───────────┘
          ▼ [clean + enrich]
┌─────────────────────┐
│  fact_sales         │  Cleaned transactions
│  (Net_rev, COGS,    │  Per V15 formulas
│   Profit calculated)│
└─────────┬───────────┘
          ▼ [aggregate]
┌─────────────────────────────────────────────┐
│  fact_sales_daily        │  fact_sales_daily_size  │
│  (date × sku_key ×       │  (date × sku_id ×       │
│   store_code)            │   store_code)           │
│  → For D₃₀, σ, SS, ROP   │  → For size mix %       │
└─────────┬────────────────┴─────────┬───────────────┘
          ▼                          ▼
┌─────────────────────────────────────────────┐
│  view_sku_metrics                           │
│  (sku_key × store_code)                     │
│  D₃₀, σ, SS_total, ROP, ROIC, Status,       │
│  Suggested_Order_Qty                        │
└─────────┬───────────────────────────────────┘
          ▼
┌─────────────────────────────────────────────┐
│  view_size_allocations                      │
│  (sku_id × store_code)                      │
│  Alloc_i = max(0, T_post × D_i − Pre_i)     │
└─────────┬───────────────────────────────────┘
          ▼
┌─────────────────────┐      ┌─────────────────────┐
│  exports/           │      │  Telegram Bot       │
│  po_suggestions.csv │      │  REORDER alerts     │
│  inventory_snap.csv │      │                     │
└─────────────────────┘      └─────────────────────┘
          ▼
┌─────────────────────┐
│  Excel UI           │
│  Inventory_Core_V15 │  (frozen, for validation + human review)
└─────────────────────┘
```

---

## 3. Table ↔ Excel Mapping

### 3.1 Dimension Tables

| DB Table      | Excel Source               | Notes                                      |
|---------------|----------------------------|--------------------------------------------|
| dim_store     | New (hardcoded or YAML)    | UNIVERSAL, ACMEWEAR, 11KZ, MELVIS, STOREB   |
| dim_sku       | Dim_SKU sheet              | sku_key, base_cost_cny, weight_kg, product_type |
| dim_sku_size  | Sku_Map_CRM_3 (size rows)  | sku_id = sku_key + my_size, barcode        |
| dim_params    | Dim_Params + Dim_Params_PT | Global + Product_Type overrides            |

### 3.2 Fact Tables

| DB Table             | Excel Equivalent        | Grain                          |
|----------------------|-------------------------|--------------------------------|
| fact_sales_raw       | (new, not in Excel)     | order_id × sku_id × store_code |
| fact_sales           | Fact_Sales sheet        | order_id × sku_id × store_code |
| fact_sales_daily     | Fact_Sales_Daily sheet  | date × sku_key × store_code    |
| fact_sales_daily_size| (new for size mix)      | date × sku_id × store_code     |
| fact_po_lines        | Fact_PO_Lines sheet     | po_id × sku_id × store_code    |
| fact_inventory_snap  | (derived daily)         | date × sku_key × store_code    |
| fact_cash_ledger     | (Phase 3+)              | Event-level for K_avg          |

### 3.3 Views

| DB View              | Excel Equivalent | Key Columns                                |
|----------------------|------------------|--------------------------------------------|
| view_sku_metrics     | ABC_View         | D₃₀, σ, SS_total, ROP, ROIC, Status, Suggested_Order |
| view_size_allocations| (implicit)       | Per-size allocation using T_post formula   |

---

## 4. Size-Level Logic

**Problem:** Excel ABC_View operates at sku_key level. POs need size splits.

**Solution:**

1. **Style-level (sku_key):** Compute D₃₀, SS_total, ROP, T_post, Suggested_Order_Qty
2. **Size-level (sku_id):** 
   - Compute D_i (demand per size from fact_sales_daily_size)
   - Compute Pre_i (on-hand + inbound per size)
   - Alloc_i = max(0, T_post × D_i − Pre_i)
3. **Validation:** Sum of Alloc_i ≈ Suggested_Order_Qty (may differ slightly due to rounding)

**store_code dimension:** All calculations are per-store. A SKU in UNIVERSAL has different D₃₀ than in ACMEWEAR.

---

## 5. Decision-Making Framework (Embedded)

Before any PO suggestion, the system computes:

| Question           | Implementation                                      |
|--------------------|-----------------------------------------------------|
| Expected ROIC?     | `(unit_profit × D₃₀ × 30) / K_avg`                 |
| Capital required?  | `K_avg = D₃₀ × (L + R/2) × COGS + SS_total × COGS` |
| Maximum downside?  | Suggested_Order × COGS_unit                         |
| Exit path?         | Product_Type → typical liquidation days             |
| 20% rule?          | Flag if order exceeds 20% of portfolio capital      |

These checks surface in view_sku_metrics as warning flags.

---

## 6. Phase 6-10 Extensibility Hooks

Schema includes placeholder columns/tables for future:

| Future Table           | Phase | Purpose                                      |
|------------------------|-------|----------------------------------------------|
| fact_demand_forecast   | 6     | Predicted demand with confidence intervals   |
| dim_seasonality        | 6     | Month × product_type → multiplier            |
| fact_capital_allocation| 7     | ROIC ranking + allocation decisions          |
| dim_sku_lifecycle      | 7     | GROW/MAINTAIN/HARVEST/KILL status            |
| fact_channel_metrics   | 8     | Cross-channel margin comparison              |
| dim_supplier           | 9     | Supplier scorecards                          |
| fact_fx_rates          | 9     | CNY/KZT, USD/KZT daily rates                 |

**Design rule:** No hard-coded "Kaspi-only" or "single-store" assumptions in table/column names.

---

## 7. Validation Contract

Before Phase 5 go-live, Python must match Excel V15:

| Metric           | Tolerance | Test SKUs                        |
|------------------|-----------|----------------------------------|
| D₃₀              | ±1%       | LINE52, LINE51, 1 slow-mover    |
| SS_total         | ±1%       |                                  |
| ROIC             | ±2%       |                                  |
| Status           | 100%      |                                  |
| Suggested_Order  | ±1 unit   |                                  |