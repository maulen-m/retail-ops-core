# Master Inventory Rules v5.3
## Authoritative Reference for Adil's Kazakhstan/Russia E-commerce Business
**Last Updated:** December 4, 2025  
**Scope:** Kaspi (Kazakhstan) + Wildberries (Russia) - shared SKU inventory management
**Implementation:** `Inventory_Core_V15_FINAL.xlsx`

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

| Code | Meaning | Status | Notes |
|------|---------|--------|-------|
| `CL` | Clothes | **Active** | Main business - New-clo line, Line51, Line52 |
| `ELS` | Electronics | Active (risky) | Epson printers |
| `FUR` | Furniture | Not selling yet | Future category |

---

## 2. CURRENT FX RATES & COSTS (Dec 2025)

| Parameter | Value | Notes |
|-----------|-------|-------|
| `USD/KZT` | 530 | |
| `CNY/KZT` | 78 | |
| `RUB/KZT` | 6.6 | Favorable for WB revenue |

### 2.1 Cargo Rates (China → Astana)

| Product_Type | Rate (USD/kg) | Notes |
|--------------|---------------|-------|
| `CL` (Clothes) | **2.66** | Improved from 3.4 |
| `ELS` (Electronics) | **2.26** | Lower rate |
| `FUR` (Furniture) | **1.76** | Lowest rate |

---

## 3. PLATFORM PARAMETERS

### 3.1 Kaspi (Kazakhstan) - Product_Type: CL

| Parameter | Value | Notes |
|-----------|-------|-------|
| `Commission` | 12.5% | |
| `VAT_rate` | 3% (4% from 2026-01-01) | |
| `L_days` | 21 days | Lead time |
| `R_days` | 10 days | Review period |
| `Payout_lag` | 2 days | |

#### 3.1.1 Kaspi Delivery Fee Tiers

| Price Range (KZT) | Fee (KZT) |
|-------------------|-----------|
| 0 - 4,999 | **0** |
| 5,000 - 14,999 | **856** |
| 15,000+ | **1,259** |

```excel
Delivery_fee = IF(Price<=4999, 0, IF(Price<=14999, 856, 1259))
```

---

## 4. SAFETY STOCK POLICY PARAMETERS

### 4.1 Global Defaults (in tb_Params)

| Param | Value | Notes |
|-------|-------|-------|
| `R_days` | 10 | Review period (days) |
| `L_days` | 21 | Lead days (cargo transit) |
| `B_days` | 14 | Safety floor buffer (days) |
| `z_factor` | 1.65 | ≈95% service level |
| `TV_mix_floor` | 0.23 | Size-mix volatility floor |
| `VAT_rate_used` | 0.03 | 3% current |
| `Platform_fee_pct_used` | 0.125 | Kaspi commission |

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

### 5.2 Safety Stock Components

```
SS_demand = z × σ × √L          # Demand variability during lead time
SS_floor  = D × B               # Minimum buffer (14 days of demand)
SS_mix    = TV × D × L          # Size mix uncertainty buffer
SS_total  = SS_demand + SS_floor + SS_mix
```

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
Net_rev_unit = (Sell_price × (1 - 0.125) - Delivery_fee) × (1 - 0.03)
COGS_unit    = BaseCost_CNY × 78 + Weight_kg × 2.66 × 530
Unit_Profit  = Net_rev_unit - COGS_unit
```

### 6.2 COGS by SKU

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

## 8. FACT_SALES COLUMN STRUCTURE (V15_FINAL) — UPDATED v5.3

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
| **K** | **Net_rev_unit** | Formula | `=(G*(1-Commission)-J)*(1-VAT)` |
| **L** | **Line_NetRev** | Formula | `=K*F` |
| **M** | **COGS_unit** | Formula | Lookup from Dim_SKU |
| **N** | **COGS_line** | Formula | `=M*F` |
| **O** | **Profit_unit** | Formula | `=K-M` |
| **P** | **Profit_line** | Formula | `=L-N` |

**Row count:** 13,372 (1 header + 13,371 data rows)

**Canonical data source:** `SALES_KSP_CRM_GPT_15.9.25.xlsx` → Archive_sales sheet

---

## 9. FACT_SALES_DAILY COLUMN STRUCTURE (V15_FINAL) — UPDATED v5.3

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

**Column mapping (Fact_Sales_Daily → Fact_Sales):**
| Daily Column | → Fact_Sales Column | Letter |
|--------------|---------------------|--------|
| Units | Quantity | F |
| Revenue | Line_NetRev | L |
| Delivery | Delivery_fee | J |
| COGS | COGS_line | N |
| Profit | Profit_line | P |

---

## 10. DATA SOURCE HIERARCHY (for CRM automation)

### 10.1 Legacy Sales Data

| File | Role | Use |
|------|------|-----|
| `SALES_KSP_CRM_GPT_15.9.25.xlsx` | **Canonical row source** | All 13,371 legacy transactions (Archive_sales sheet) |
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

> **Note:** `Fact_Sales_Raw` is a **Project 3 (CRM/DB) responsibility**, not an Excel sheet. Excel's Fact_Sales receives cleaned data only.

---

## 11. QUICK REFERENCE CARD

```
COGS = Base_CNY × 78 + Weight × 2.66 × 530
  LINE52: 47×78 + 0.95×2.66×530 = 5,005 KZT
  LINE51:  60×78 + 0.95×2.66×530 = 6,019 KZT

DELIVERY FEE (Kaspi, for clothing ~1kg):
  Price ≤ 4,999   → 0 KZT
  Price 5,000-14,999 → 856 KZT
  Price ≥ 15,000  → 1,259 KZT

NetRev = (Price × 0.875 - Delivery_fee) × 0.97

σ = D_30 × 0.4

SS_total = z×σ×√L + D×B + TV×D×L
ROP = D×L + SS_total

Status = Total<ROP ? "⚠️ REORDER" : (Current<ROP ? "📦 WAIT" : "✅ OK")
         → Check Total FIRST (v5.2+ fix)

FACT_SALES COLUMN MAP (V15):
  A: Date | B: OrderID | C: Kaspi_Offer | D: SKU_key | E: SKU_ID
  F: Quantity | G: Sell_price | H: Product_Type | I: Channel
  J: Delivery_fee | K: Net_rev_unit | L: Line_NetRev
  M: COGS_unit | N: COGS_line | O: Profit_unit | P: Profit_line
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
| 5.2 | 2025-12-04 | V15 fixes: Status logic, Fact_Sales_Daily formulas, Dim_PO_Header deleted |
| **5.3** | **2025-12-04** | **V15_FINAL column structure:** Fact_Sales rebuilt with data columns A–I, formula columns J–P. Updated §8-9 with correct column mapping. Added §10 data source hierarchy. Added §12 validation checklist. Clarified Fact_Sales_Raw as Project 3 (DB) scope. |

---

## PROJECT ARCHITECTURE NOTE

This document is the **SYNC MECHANISM** across all Claude projects:
- **Project 1 (Business Brain):** Excel UI implementation in Inventory_Core_V15_FINAL.xlsx
- **Project 2 (WB Entry):** References these formulas for unit economics
- **Project 3 (CRM Build):** Must implement these exact formulas in Python; owns Fact_Sales_Raw

**V15_FINAL is the frozen contract. Excel is now "UI mode" — Python/DB is the brain.**

---

*This document is the single source of truth for inventory formulas. Reference from all Claude projects.*
