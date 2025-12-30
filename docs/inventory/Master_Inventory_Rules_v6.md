# Master Inventory Rules v6.0
## Authoritative Reference for Adil's Kazakhstan/Russia E-commerce Business
**Last Updated:** December 12, 2025  
**Scope:** Kaspi (Kazakhstan) + Wildberries (Russia) — shared SKU inventory management  
**Implementation:** `Inventory_Core_V15_FINAL.xlsx` + Project 3 (Python/DB)

---

## 1. KEY IDENTIFIERS

| Key | Definition | Example |
|-----|------------|---------|
| `SKU_key` | Full product path (Category_Line_Gender_Model_Color) | `CL_OC_MEN_LINE51_WHITE` |
| `SKU_ID` | Size-level identifier | `CL_OC_MEN_LINE52_BLACK_XL` |
| `OrderID` | Kaspi order number | `407785789` |
| `Kaspi_Offer_name` | Kaspi listing title | `Комплект Antec RASH-921...` |
| `MY_SIZE` | Normalized size label | Adults: `S, M, L, XL, 2XL, 3XL` / Kids: `22, 24...34` |
| `Product_Type` | Business category for parameter overrides | `CL`, `ELS`, `FUR` |

### 1.1 Product_Type Definitions

| Code | Meaning | Status | Channel | Notes |
|------|---------|--------|---------|-------|
| `CL` | Clothes | **Active** | Kaspi, WB | Main business — New-clo line, Line51, Line52 |
| `ELS` | Electronics | Active (risky) | Kaspi only | Epson printers; higher risk factor applies |
| `FUR` | Furniture | Not selling yet | — | Future category |

---

## 2. CURRENT FX RATES & COSTS (Dec 2025)

| Parameter | Value | Notes |
|-----------|-------|-------|
| `FX_USD_KZT` | 530 | Cargo payments |
| `FX_CNY_KZT` | 78 | Supplier payments |
| `FX_RUB_KZT` | 6.6 | WB revenue conversion |

### 2.1 Cargo Rates (China → Astana)

| Product_Type | Rate (USD/kg) | Notes |
|--------------|---------------|-------|
| `CL` (Clothes) | **2.66** | Improved from 3.4 |
| `ELS` (Electronics) | **2.26** | Lower rate |
| `FUR` (Furniture) | **1.76** | Lowest rate |

---

## 3. CHANNEL PARAMETER INHERITANCE

### 3.0 Structure

Parameters follow a **Master → Channel** inheritance model:

```
┌─────────────────────────────────────────────────────────────┐
│                      MASTER PARAMS                           │
│  Supply chain: L1, R, B, FX rates, cargo rates              │
│  Business rules: z, TV, σ, VAT, ROIC gates, size mix        │
│  Risk factors: New SKU factors, ELS_risk                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
            ┌──────────────┴──────────────┐
            ▼                             ▼
   ┌─────────────────┐           ┌─────────────────┐
   │     KASPI       │           │       WB        │
   │  Commission     │           │  Commission     │
   │  Delivery tiers │           │  Logistics fee  │
   │  Payout lag     │           │  Payout cycle   │
   │  Return rate    │           │  Return rate    │
   │  L_total = L1   │           │  L_total = L1+  │
   │  Product: CL,ELS│           │  Product: CL    │
   └─────────────────┘           └─────────────────┘
```

**Inheritance Rules:**
1. If param not listed in channel section → **inherit Master value**
2. Channel sections only list **overrides and platform-specific params**
3. Derived params must show formula referencing Master (e.g., `L_total = L1 + L2 + L3`)
4. WB-only params use `WB_` prefix
5. `VAT_rate` is Master-owned — channels inherit, never override

**Active Channels:**
- **Kaspi** (§3.1) — Primary, supports CL and ELS
- **Wildberries** (§3.2) — Expansion, CL only (no ELS on WB)

---

### 3.1 Channel: Kaspi (Kazakhstan)

**Inherits from Master:** L1, R, B, z, TV, σ_factor, FX rates, cargo rates, VAT_rate, ROIC gates, size mix guardrails, new SKU factors

**Kaspi-Specific:**

| Parameter | Value | Notes |
|-----------|-------|-------|
| `Commission` | 12.5% | Platform fee |
| `Payout_lag` | 2 days | Fast payout |
| `Return_rate` | ~5% | Low return rate |
| `L_total` | 21 days | `= L1` (no additional legs) |

#### 3.1.1 Kaspi Delivery Fee Tiers

| Price Range (KZT) | Fee (KZT) |
|-------------------|-----------|
| 0 – 4,999 | **0** |
| 5,000 – 14,999 | **856** |
| 15,000+ | **1,259** |

```excel
Delivery_fee = IF(Price<=4999, 0, IF(Price<=14999, 856, 1259))
```

---

### 3.2 Channel: Wildberries (Russia)

**Inherits from Master:** R, B, z, TV, σ_factor, FX rates, cargo rates, VAT_rate, ROIC gates, size mix guardrails, new SKU factors

**Product Scope:** CL only (no ELS on WB)

**WB-Specific Lead Time:**

| Param | Value | Source |
|-------|-------|--------|
| `L1` | 21 days | Master §4.1 (inherited) |
| `L2` | 1 day/200 units | WB-specific (fulfillment prep) |
| `L3` | 10 days | WB-specific (Astana → WB warehouses) |
| `L_total` | **~32 days** | `= L1 + L2 + L3` |

**WB-Specific Economics:**

| Parameter | Value | Notes |
|-----------|-------|-------|
| `WB_commission` | 24.5% | vs Kaspi 12.5% |
| `WB_logistics_storage` | 408₽/unit avg | Combined logistics + storage |
| `WB_return_rate` | 25% | vs Kaspi ~5% — **major risk factor** |
| `WB_payment_cycle` | 7-day sales + 11-day delay | vs Kaspi 2-day payout |
| `WB_warehouse_split` | Multi-region distribution | No Kaspi equivalent |

> **Reference:** Full WB strategy and scenario analysis in `WB_policy_v4.md`

---

## 4. SAFETY STOCK POLICY PARAMETERS

### 4.1 Global Defaults (Master-Owned)

| Param | Value | Notes |
|-------|-------|-------|
| `L1` (L_days) | 21 | Lead days: China → Astana |
| `R_days` | 10 | Review period |
| `B_days` | 14 | Safety floor buffer |
| `z_factor` | 1.65 | ≈95% service level |
| `TV_mix_floor` | 0.23 | Size-mix volatility floor |
| `σ_factor` | 0.4 | `σ = D_30 × 0.4` |
| `VAT_rate` | 0.03 | 3% (4% from 2026-01-01) — **Master-owned** |

### 4.2 ROIC Gates & Capital Allocation

#### 4.2.1 Approval Thresholds

| ROIC Range | Decision | Action |
|------------|----------|--------|
| **≥ 20%** | `ORDER_FULL` | Auto-approve PO |
| **10–20%** | `ORDER_WITH_FLAG` | Approve with monitoring flag |
| **< 10%** | `REVIEW_REQUIRED` | Human decision required |

#### 4.2.2 Capital Allocation When Constrained

When total available capital < sum of K_avg for all ROIC ≥ 20% items:

1. **Rank all eligible SKUs by ROIC** (highest to lowest)
2. **Allocate capital in rank order** until exhausted
3. **Apply smoothing to tail** — Gaussian-weighted redistribution capped at 15% of total capital
   - Prevents sharp cutoff where item #N gets full allocation and #N+1 gets zero
   - Smoothing formula: `Alloc_i = Base_alloc_i × (1 - 0.15 × gaussian_tail_weight_i)`

```
Example: 5M KZT capital, 8 SKUs qualify
  SKU_A (ROIC 45%): K_avg 1.2M → Alloc 1.2M
  SKU_B (ROIC 38%): K_avg 0.9M → Alloc 0.9M
  SKU_C (ROIC 32%): K_avg 1.1M → Alloc 1.1M
  SKU_D (ROIC 28%): K_avg 0.8M → Alloc 0.8M
  SKU_E (ROIC 24%): K_avg 1.0M → Alloc 0.85M (smoothed, tail starts)
  SKU_F (ROIC 21%): K_avg 0.7M → Alloc 0.15M (smoothed remainder)
  SKU_G, SKU_H: No allocation this cycle
```

### 4.3 New Item Capital Limit

| Param | Value | Rule |
|-------|-------|------|
| `Max_new_SKU_capital_pct` | 20% | No **new** SKU_key (not currently in catalog) may consume >20% of deployed capital |

**Scope:** Applies only to SKU_keys being added to catalog for the first time. Existing SKUs have no individual capital cap (governed by ROIC ranking instead).

### 4.4 Size Mix Guardrails (Product_Type: CL only)

**Applies to:** Clothes (`CL`) only — not ELS, not FUR

| Param | Value | Purpose |
|-------|-------|---------|
| `Size_mix_floor` | 3% | Minimum allocation per size (prevent zero-stock) |
| `Size_mix_cap` | 40% | Maximum allocation per size (prevent over-concentration) |

**Note:** ELS and FUR do not have size variants; these guardrails are irrelevant for those Product_Types.

### 4.5 Prep Days by Product Type

Prep days represent supplier preparation time before shipping. **Critical:** Prep is calculated per supplier batch, not per individual SKU.

#### 4.5.1 Prep Days Formulas

| Product_Type | Prep Days | Formula |
|--------------|-----------|---------|
| `CL` (Clothes) | **Shared** | `ceil(1.3 × Total_CL_Weight_kg / 100)` |
| `ELS` (Electronics) | **1 day (constant)** | Always 1 |
| `FUR` (Furniture) | TBD | Not active |

**Why shared for CL:** A single supplier prepares all clothing items together. The supplier cannot ship until ALL items are ready, so prep time depends on total batch weight.

#### 4.5.2 Prep Models

| Model | Name | Formula | Default |
|-------|------|---------|---------|
| **Model B** | Worst-Case | `prep = ceil(1.3 × weight / 100)` | No |
| **Model C** | Capacity-Capped | `prep = min(Model_B, R)` | **Yes** |

Model C caps prep at R (10 days) assuming supplier can parallel-process within a review cycle.

#### 4.5.3 Effective Lead Time

```
Effective_L = L + prep_days

CL items:  Effective_L = 21 + Total_Prep_Clothes
ELS items: Effective_L = 21 + 1 = 22
```

**Usage:** All consumption and stock projection calculations must use `Effective_L`, not raw `L`.

---

### 4.6 New SKU Risk Factors

Reduce order quantities for SKUs with limited or no sales history to manage demand uncertainty.

#### 4.6.1 Base Factors (by sales history)

| History | Factor | Effective Order |
|---------|--------|-----------------|
| **0 days** (never sold) | **0.50** | 50% of calculated qty |
| < 30 days | 0.75 | 75% of calculated qty |
| 30–60 days | 0.85 | 85% of calculated qty |
| 60–90 days | 0.95 | 95% of calculated qty |
| ≥ 90 days | 1.00 | Full calculated qty |

#### 4.6.2 Product_Type Risk Multiplier

| Product_Type | Risk Multiplier | Combined with New_SKU_0d |
|--------------|-----------------|--------------------------|
| `CL` (Clothes) | 1.0 | 0.50 × 1.0 = **0.50** |
| `ELS` (Electronics) | **0.5** | 0.50 × 0.5 = **0.25** |
| `FUR` (Furniture) | TBD | Not active |

**ELS_risk rationale:** Electronics carry higher obsolescence and demand uncertainty risk. A brand-new ELS SKU gets only 25% of calculated order quantity.

#### 4.6.3 Formula

```
Effective_order_qty = Calculated_qty × New_SKU_factor × Product_Type_risk

Example (new ELS item, never sold):
  Calculated_qty = 100 units
  New_SKU_0d_factor = 0.50
  ELS_risk = 0.50
  Effective_order_qty = 100 × 0.50 × 0.50 = 25 units
```

---

## 5. CORE FORMULAS

### 5.1 Demand & Volatility (per SKU)

```
D_30 = SUM(sales_30d) / 30
σ    = D_30 × 0.4    # APPROXIMATION (pragmatic, not MAD-based)
```

### 5.1.1 Status Flag Logic (ABC_View) — v5.2+ CORRECTED

**Correct Formula (check Total FIRST, then Current):**
```excel
=IF(Total_stock < ROP, "⚠️ REORDER",
    IF(Current_stock < ROP, "📦 WAIT (inbound)", "✅ OK"))
```

**Logic:**
1. If `Total_stock < ROP` → **⚠️ REORDER** (nothing covers the gap)
2. Else if `Current_stock < ROP` (but Total ≥ ROP) → **📦 WAIT** (inbound covers it)
3. Else → **✅ OK**

| Status | Meaning | Action |
|--------|---------|--------|
| ⚠️ REORDER | Total stock below ROP | Place PO this week |
| 📦 WAIT | Current below ROP but inbound covers | Monitor; PO in transit |
| ✅ OK | Total stock above ROP | No action needed |

**Column references in ABC_View:**
- C = Current_stock
- E = Total_stock (Current + Inbound)
- U = ROP

### 5.1.2 Partial OOS Detection (Size-Level Suppression)

Detect size-level stockout suppression by measuring share drift from anchor.

**Threshold:** ≥30% relative share drift

**Formula:**
```
relative_drift = (anchor_share - observed_share) / anchor_share
IF relative_drift ≥ 0.30 → SIZE IS SUPPRESSED
```

**Example:**
```
3XL: anchor_share = 13%, observed_share = 9%
relative_drift = (13 - 9) / 13 = 30.7% → SUPPRESSED ✓

If demand genuinely fell (all sizes proportional):
3XL: anchor_share = 13%, observed_share = 13% (of smaller total)
relative_drift = 0% → NOT suppressed ✓
```

**Config param:**

| Param | Value | Notes |
|-------|-------|-------|
| `suppression_relative_threshold` | 0.30 | ≥30% drop from anchor = suppressed |

**Effect on anchor_weight:**

| Suppressed Sizes | Anchor Weight Boost |
|------------------|---------------------|
| 1 size | w = max(w, 0.5) |
| 2 sizes | w = max(w, 0.7) |
| 3+ sizes | w = max(w, 0.8) |

### 5.2 Safety Stock Components

```
SS_demand = z × σ × √L          # Demand variability during lead time
SS_floor  = D × B               # Minimum buffer (14 days of demand)
SS_mix    = TV × D × L          # Size mix uncertainty buffer (CL only)
SS_total  = SS_demand + SS_floor + SS_mix
```

**Note:** For ELS/FUR (no size variants), `SS_mix = 0`.

### 5.3 Reorder Point & Target Coverage

```
ROP    = D × L + SS_total    # Trigger point for new order
T_post = R + (SS_total / D)  # Target days of cover after arrival
```

### 5.4 Capital & ROIC

```
K_avg          = D × (L + R/2) × COGS + SS_total × COGS
Monthly_Profit = UnitProfit × D × 30
Monthly_ROIC   = Monthly_Profit / K_avg
```

---

## 6. UNIT ECONOMICS FORMULAS

### 6.1 Kaspi (CL items)

```
Net_rev_unit = (Sell_price × (1 - 0.125) - Delivery_fee) × (1 - VAT_rate)
COGS_unit    = BaseCost_CNY × FX_CNY_KZT + Weight_kg × Cargo_rate × FX_USD_KZT
Unit_Profit  = Net_rev_unit - COGS_unit
```

### 6.2 Wildberries (CL items)

```
Net_rev_unit = (SPP_RUB × (1 - 0.245) - WB_logistics_storage) × FX_RUB_KZT × (1 - VAT_rate)
COGS_unit    = BaseCost_CNY × FX_CNY_KZT + Weight_kg × Cargo_rate × FX_USD_KZT
Unit_Profit  = Net_rev_unit - COGS_unit
```

> **Note:** WB has higher commission (24.5% vs 12.5%) and return rate (25% vs 5%), but favorable RUB/KZT rate (6.6) can still yield strong ROIC at right price points.

### 6.3 COGS Reference by SKU

| SKU | Base (CNY) | Weight | COGS (KZT) |
|-----|------------|--------|------------|
| **LINE52** | 47 | 0.95 kg | **5,005** |
| **LINE51** | 60 | 0.95 kg | **6,019** |

---

## 7. INVENTORY_CORE.XLSX TABLE MAP (V15_FINAL)

### Dimension Tables
| Sheet | Purpose | Key |
|-------|---------|-----|
| `Dim_Params` | Global defaults | Param |
| `Dim_Params_PT` | Product_Type overrides | Product_Type |
| `Dim_SKU` | SKU master | SKU_key |

### Fact Tables
| Sheet | Purpose | Grain |
|-------|---------|-------|
| `Fact_PO_Lines` | PO line items | PO_Id × SKU_KEY × MY_SIZE |
| `Fact_Sales` | Sales transactions | Date × SKU_key × OrderID |
| `Fact_Sales_Daily` | Daily aggregates (DERIVED) | Date × SKU_key |

### View Tables
| Sheet | Purpose |
|-------|---------|
| `ABC_View` | Per-SKU operational dashboard |
| `tb_Inbound` | Open PO inbound schedule |
| `Master_Calendar` | Portfolio daily view |
| `SKU_Calendar` | Per-SKU daily projection |

### Retained for Future Use
| Sheet | Purpose |
|-------|---------|
| `tb_Moves` | Inventory movement tracking (future) |
| `tb_Cash` | Cash flow tracking (future) |

### Deleted Sheets (no longer exist)
| Sheet | Reason |
|-------|--------|
| `Dim_PO_Header` | Deprecated; Status now native in Fact_PO_Lines |

**Total sheet count: 13**

---

## 8. FACT_SALES COLUMN STRUCTURE (V15_FINAL)

**Design principle:** Data columns first (A–I), then formula columns (J–P). This enables idempotent data imports.

| Col | Header | Type | Source/Formula |
|-----|--------|------|----------------|
| **A** | **Date** | Data | Direct from export |
| **B** | **OrderID** | Data | Kaspi order number (№ заказа) |
| **C** | **Kaspi_Offer_name** | Data | Kaspi listing title |
| **D** | **SKU_key** | Data | Normalized SKU key |
| **E** | **SKU_ID** | Data | Size-level SKU |
| **F** | **Quantity** | Data | Units sold |
| **G** | **Sell_price_kzt** | Data | Unit sale price |
| **H** | **Product_Type** | Data | CL/ELS/FUR |
| **I** | **Channel** | Data | "Kaspi" or "WB" |
| **J** | **Delivery_fee** | Formula | Tiered lookup: `=IF(G<=4999,0,IF(G<=14999,856,1259))` |
| **K** | **Net_rev_unit** | Formula | `=(G*(1-Commission)-J)*(1-VAT_rate)` |
| **L** | **Line_NetRev** | Formula | `=K*F` |
| **M** | **COGS_unit** | Formula | Lookup from Dim_SKU |
| **N** | **COGS_line** | Formula | `=M*F` |
| **O** | **Profit_unit** | Formula | `=K-M` |
| **P** | **Profit_line** | Formula | `=L-N` |

**Row count:** 13,372 (1 header + 13,371 data rows)

---

## 9. FACT_SALES_DAILY COLUMN STRUCTURE (V15_FINAL)

**Critical rule:** Fact_Sales_Daily is a **pure derived view**. All metric columns must be SUMIFS formulas. No hard-coded values allowed in the data region.

| Col | Header | Formula (references V15 Fact_Sales columns) |
|-----|--------|---------------------------------------------|
| A | Date | Direct |
| B | SKU_key | Direct |
| C | Units | `=SUMIFS(Fact_Sales!$F:$F, Fact_Sales!$A:$A, A2, Fact_Sales!$D:$D, B2)` |
| D | Revenue | `=SUMIFS(Fact_Sales!$L:$L, Fact_Sales!$A:$A, A2, Fact_Sales!$D:$D, B2)` |
| E | Delivery | `=SUMIFS(Fact_Sales!$J:$J, Fact_Sales!$A:$A, A2, Fact_Sales!$D:$D, B2)` |
| F | COGS | `=SUMIFS(Fact_Sales!$N:$N, Fact_Sales!$A:$A, A2, Fact_Sales!$D:$D, B2)` |
| G | Profit | `=SUMIFS(Fact_Sales!$P:$P, Fact_Sales!$A:$A, A2, Fact_Sales!$D:$D, B2)` |

---

## 10. DATA SOURCE HIERARCHY (for CRM automation)

### 10.1 Legacy Sales Data

| File | Role | Use |
|------|------|-----|
| `SALES_KSP_CRM_GPT_15.9.25.xlsx` | **Canonical row source** | All 13,371 legacy transactions |
| `SALES_KSP_CRM_V3.xlsx` | Column semantics reference | Do NOT use for row data |
| `ActiveOrders_Example.xlsx` | Future ingest shape | Defines Kaspi raw export format |

### 10.2 Future Ingest (Project 3 - CRM)

**ActiveOrders column mapping → Fact_Sales_Raw (DB table, not Excel):**

| ActiveOrders Column (Russian) | Fact_Sales_Raw Column |
|-------------------------------|----------------------|
| `№ заказа` | OrderID |
| `Дата поступления заказа` | Order_date |
| `Название товара в Kaspi Магазине` | Kaspi_offer |
| `Артикул` | Kaspi_article |
| `Сумма` | Sell_price_kzt |
| `Количество` | Quantity |
| `Стоимость доставки для продавца` | Delivery_fee_seller |
| `Стоимость доставки для покупателя` | Delivery_fee_buyer |
| `Статус` | Status |

> **Note:** `Fact_Sales_Raw` is a **Project 3 (CRM/DB) responsibility**, not an Excel sheet.

---

## 11. QUICK REFERENCE CARD

```
COGS = Base_CNY × 78 + Weight × 2.66 × 530
  LINE52: 47×78 + 0.95×2.66×530 = 5,005 KZT
  LINE51:  60×78 + 0.95×2.66×530 = 6,019 KZT

DELIVERY FEE (Kaspi):
  Price ≤ 4,999   → 0 KZT
  Price 5,000-14,999 → 856 KZT
  Price ≥ 15,000  → 1,259 KZT

NetRev = (Price × 0.875 - Delivery_fee) × 0.97

σ = D_30 × 0.4

SS_total = z×σ×√L + D×B + TV×D×L  (SS_mix=0 for non-CL)
ROP = D×L + SS_total

Status = Total<ROP ? "⚠️ REORDER" : (Current<ROP ? "📦 WAIT" : "✅ OK")

NEW SKU FACTORS:
  0 days:  0.50 (× ELS_risk 0.5 for electronics = 0.25)
  <30d:    0.75
  30-60d:  0.85
  60-90d:  0.95
  ≥90d:    1.00

PREP DAYS (by Product_Type):
  CL:  prep = ceil(1.3 × Total_CL_Weight_kg / 100)  # Shared for batch
  ELS: prep = 1 (constant)

EFFECTIVE LEAD TIME:
  Effective_L = L + prep_days
  CL:  Effective_L = 21 + Total_Prep_Clothes
  ELS: Effective_L = 21 + 1 = 22

ROIC GATES:
  ≥20%:  ORDER_FULL
  10-20%: ORDER_WITH_FLAG
  <10%:  REVIEW_REQUIRED

CAPITAL ALLOCATION: Rank by ROIC, allocate top-down, 15% gaussian smoothing on tail
```

---

## 12. VALIDATION CHECKLIST (Before Any Freeze)

Before promoting any version to FROZEN status:

- [ ] Fact_Sales_Daily.Revenue (D) sums Fact_Sales column **L** (Line_NetRev)
- [ ] Fact_Sales_Daily.Delivery (E) sums Fact_Sales column **J** (Delivery_fee)
- [ ] Fact_Sales_Daily.COGS (F) sums Fact_Sales column **N** (COGS_line)
- [ ] Fact_Sales_Daily.Profit (G) sums Fact_Sales column **P** (Profit_line)
- [ ] Fact_Sales_Daily.Units (C) sums Fact_Sales column **F** (Quantity)
- [ ] No hard-coded values in Fact_Sales_Daily data body (all formulas)
- [ ] ABC_View.Status uses 3-state logic: `IF(E<U, "REORDER", IF(C<U, "WAIT", "OK"))`
- [ ] Fact_PO_Lines.Status has no formula dependency on deleted sheets
- [ ] Sheet count = 13
- [ ] New SKU factors applied correctly per Product_Type
- [ ] Size mix guardrails only applied to CL items

---

## VERSION HISTORY

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-28 | Initial consolidation |
| 1.1 | 2025-11-28 | Fixed Product_Type, added table map |
| 1.2 | 2025-11-28 | Fixed Kaspi commission to 12.5% |
| 1.3 | 2025-12-02 | COGS overhaul: freight formula |
| 1.4 | 2025-12-02 | Delivery tiers, 17,562 transactions |
| 1.5 | 2025-12-03 | Sigma approximation (σ=D×0.4) |
| 5.2 | 2025-12-04 | V15 fixes: Status logic, Fact_Sales_Daily formulas |
| 5.3 | 2025-12-04 | V15_FINAL column structure |
| **6.0** | **2025-12-12** | **Channel inheritance model:** Added §3.0 structure, §3.2 WB channel. **Capital allocation:** Added §4.2 ROIC gates with ranked allocation + gaussian smoothing. **Risk management:** Added §4.3 Max_new_SKU_capital (20% for new items only (No sales history)), §4.4 size mix (CL only), §4.5 new SKU factors with 0d baseline and ELS_risk multiplier. **VAT_rate:** Now Master-owned only. |
| **6.1** | **2025-12-19** | **Prep days:** Added §4.5 Prep Days by Product Type with shared CL batch formula, ELS constant=1, Model B/C definitions, Effective_L calculation. **Quick reference:** Added prep days and effective_L formulas. |

---

## PROJECT ARCHITECTURE NOTE

This document is the **SINGLE SOURCE OF TRUTH** for inventory parameters across all projects:

- **Project 1 (Business Brain):** Excel UI implementation in Inventory_Core_V15_FINAL.xlsx
- **Project 2 (WB Entry):** References §3.2 and §6.2 for WB unit economics — see `WB_policy_v4.md` for full strategy
- **Project 3 (CRM Build):** Must implement these exact formulas in Python; owns Fact_Sales_Raw

**Inheritance principle:** If a parameter is not explicitly overridden in a channel section, it inherits the Master value. Never duplicate values across docs.

**V15_FINAL is the frozen Excel contract. Python/DB is the brain.**

---

*This document is the single source of truth for inventory formulas and parameters. Reference from all Claude projects. Do not duplicate parameters elsewhere.*
