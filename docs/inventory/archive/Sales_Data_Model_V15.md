# DEPRECATED — superseded by `inventory/Sales_Data_Model_V16.md`. Do not implement from this file.

# Sales Data Model V15
## Project 1: Business Brain Excel Core
**Created:** December 4, 2025  
**Purpose:** Define the authoritative table structure for sales data flow in Inventory_Core.xlsx

---

## 1. Overview: Three-Table Pipeline

```
┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
│   Fact_Sales_Raw    │  →   │     Fact_Sales      │  →   │  Fact_Sales_Daily   │
│   (Raw Ingest)      │      │  (Transaction Math) │      │  (Daily Aggregates) │
└─────────────────────┘      └─────────────────────┘      └─────────────────────┘
     OrderID, full              SKU_key + economics         Date × SKU_key
     Kaspi identifiers          for inventory math          fully formula-driven
```

### M-006 Resolution: Option C Adopted

**Decision:** Create `Fact_Sales_Raw` to hold full Kaspi identifiers while keeping `Fact_Sales` clean for mathematical operations.

**Rationale:**
1. **Traceability:** OrderID/Kaspi_offer needed for returns, disputes, Kaspi reconciliation
2. **Clean math:** Fact_Sales stays focused on inventory economics (Date × SKU_key × economics)
3. **Separation of concerns:** Raw data vs calculation layers
4. **Automation-friendly:** Python CRM can extract either layer as needed

---

## 2. Table Definitions

### 2.1 Fact_Sales_Raw (NEW - To Be Created in V15)

**Purpose:** Landing zone for raw Kaspi orders. Contains full order-level traceability.

**Grain:** Order line (OrderID × SKU_key × size)

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| **OrderID** | Text | `№ заказа` | Kaspi order number (e.g., "725777649") |
| **Order_date** | Date | `Дата поступления заказа` | Order placement date |
| **Kaspi_offer** | Text | `Название товара в Kaspi Магазине` | Kaspi listing name |
| **Kaspi_article** | Text | `Артикул` | Kaspi article/SKU identifier |
| **SKU_key** | Text | Derived | Normalized SKU (Category_Line_Gender_Model_Color) |
| **SKU_ID** | Text | Derived | Size-level SKU (SKU_key_SIZE) |
| **MY_SIZE** | Text | Parsed | Normalized size (XL, 2XL, 24, etc.) |
| **Quantity** | Integer | `Количество` | Units sold |
| **Sell_price_kzt** | Number | `Сумма` | Sale price per unit (KZT) |
| **Delivery_fee_seller** | Number | `Стоимость доставки для продавца` | Seller-paid delivery |
| **Delivery_fee_buyer** | Number | `Стоимость доставки для покупателя` | Buyer-paid delivery |
| **Status** | Text | `Статус` | Order status (Kaspi language) |
| **Channel** | Text | Derived | "Kaspi" (hardcoded for now) |
| **Product_Type** | Text | Derived | CL, ELS, FUR, WB |

**Source mapping:**
- **Future ingestion:** ActiveOrders_Example.xlsx format
- **Legacy data:** SALES_KSP_CRM_GPT_15.9.25.xlsx (row completeness)
- **Column semantics:** SALES_KSP_CRM_V3.xlsx + ActiveOrders_Example.xlsx

**Notes:**
- This table is for **traceability and reconciliation only**
- Not used directly in inventory calculations
- Fact_Sales is derived from this table

---

### 2.2 Fact_Sales (EXISTING - Keep Current Structure)

**Purpose:** Transaction-level economics for inventory math. One row per sale event.

**Grain:** Date × SKU_key × transaction

| Column | Letter | Type | Formula/Source | Description |
|--------|--------|------|----------------|-------------|
| Date | A | Date | Direct | Sale date |
| Channel | B | Text | Direct | "Kaspi" or "WB" |
| SKU_key | C | Text | Direct | Normalized SKU |
| SKU_ID | D | Text | Direct | Size-level SKU |
| Quantity | E | Integer | Direct | Units sold |
| Sell_price_kzt | F | Number | Direct | Unit price |
| Delivery_fee | G | Number | Lookup | Tiered delivery (0/856/1259) |
| Net_rev_unit | H | Number | Formula | `=(F*(1-Commission)-G)*(1-VAT)` |
| Line_NetRev | I | Number | Formula | `=H*E` |
| COGS_unit | J | Number | Lookup | From Dim_SKU |
| COGS_line | K | Number | Formula | `=J*E` |
| Profit_unit | L | Number | Formula | `=H-J` |
| Profit_line | M | Number | Formula | `=I-K` |

**Column letter reference (critical for SUMIFS):**
```
A: Date | B: Channel | C: SKU_key | D: SKU_ID | E: Quantity
F: Sell_price_kzt | G: Delivery_fee | H: Net_rev_unit | I: Line_NetRev
J: COGS_unit | K: COGS_line | L: Profit_unit | M: Profit_line
```

**Current state (V14):** 13,364 rows, structure is correct. No OrderID (lives in Fact_Sales_Raw).

---

### 2.3 Fact_Sales_Daily (EXISTING - FIX FORMULAS)

**Purpose:** Daily aggregates by SKU for demand analysis and ABC_View lookups.

**Grain:** Date × SKU_key (one row per day per SKU)

| Column | Letter | Type | Formula | Description |
|--------|--------|------|---------|-------------|
| Date | A | Date | Direct | Calendar date |
| SKU_key | B | Text | Direct | Normalized SKU |
| Units | C | Number | `=SUMIFS(Fact_Sales!$E:$E,...)` | Daily quantity |
| Revenue | D | Number | `=SUMIFS(Fact_Sales!$I:$I,...)` | Daily Line_NetRev |
| Delivery | E | Number | `=SUMIFS(Fact_Sales!$G:$G,...)` | Daily Delivery_fee |
| COGS | F | Number | `=SUMIFS(Fact_Sales!$K:$K,...)` | Daily COGS_line |
| Profit | G | Number | `=SUMIFS(Fact_Sales!$M:$M,...)` | Daily Profit_line |

**CRITICAL: Current V14 bugs (M-003):**
- D: Sums column G (Delivery_fee) → WRONG, should sum column I (Line_NetRev)
- E: Hard-coded value → WRONG, should be SUMIFS to column G
- F: Hard-coded 0 → WRONG, should be SUMIFS to column K
- G: `=D-F` → Gives Delivery-0=Delivery, not true profit

**Required fix formulas (row 2 example):**
```excel
C2: =SUMIFS(Fact_Sales!$E:$E,Fact_Sales!$A:$A,A2,Fact_Sales!$C:$C,B2)
D2: =SUMIFS(Fact_Sales!$I:$I,Fact_Sales!$A:$A,A2,Fact_Sales!$C:$C,B2)
E2: =SUMIFS(Fact_Sales!$G:$G,Fact_Sales!$A:$A,A2,Fact_Sales!$C:$C,B2)
F2: =SUMIFS(Fact_Sales!$K:$K,Fact_Sales!$A:$A,A2,Fact_Sales!$C:$C,B2)
G2: =SUMIFS(Fact_Sales!$M:$M,Fact_Sales!$A:$A,A2,Fact_Sales!$C:$C,B2)
```

**Rule:** Fact_Sales_Daily is a **derived view**. No manual editing allowed. All values come from Fact_Sales via formulas.

---

## 3. Legacy Data Source Mapping

### 3.1 Canonical Legacy Data

| File | Role | Row Count | Use |
|------|------|-----------|-----|
| `SALES_KSP_CRM_GPT_15.9.25.xlsx` | **Row completeness** | 13,371 | All legacy sales transactions |
| `SALES_KSP_CRM_V3.xlsx` | **Column semantics** | 476 | Column meaning reference |
| `ActiveOrders_Example.xlsx` | **Future ingest shape** | 148 | Target schema for new orders |

### 3.2 Column Mapping: ActiveOrders → Fact_Sales_Raw

| ActiveOrders Column (Russian) | Fact_Sales_Raw Column | Notes |
|-------------------------------|----------------------|-------|
| `№ заказа` | OrderID | Kaspi order number |
| `Дата поступления заказа` | Order_date | Order placement date |
| `Название товара в Kaspi Магазине` | Kaspi_offer | Kaspi listing title |
| `Артикул` | Kaspi_article | Kaspi article ID |
| `Сумма` | Sell_price_kzt | Unit price |
| `Количество` | Quantity | Units |
| `Стоимость доставки для продавца` | Delivery_fee_seller | Seller pays |
| `Стоимость доставки для покупателя` | Delivery_fee_buyer | Buyer pays |
| `Статус` | Status | Order status |

### 3.3 Column Mapping: GPT_15.9.25 → Fact_Sales (Current State)

| GPT File Column | Fact_Sales Column | Notes |
|-----------------|-------------------|-------|
| Date | Date | Direct |
| OrderID | (Missing in V14) | → Goes to Fact_Sales_Raw |
| SKU_key | SKU_key | Direct |
| SKU_ID | SKU_ID | Direct |
| Quantity | Quantity | Direct |
| Sell_price_kzt | Sell_price_kzt | Direct |
| Delivery_fee_kzt | Delivery_fee | Direct |
| - | Net_rev_unit | Calculated |
| - | Line_NetRev | Calculated |
| - | COGS_unit | Lookup |
| - | COGS_line | Calculated |
| - | Profit_unit | Calculated |
| - | Profit_line | Calculated |

---

## 4. Future Ingestion Workflow

### 4.1 Standard Weekly Process

```
1. Export from Kaspi → ActiveOrders_[date].xlsx

2. Append to Fact_Sales_Raw (manual paste or Python script)
   - Map columns per §3.2
   - Derive SKU_key, SKU_ID from Kaspi_article

3. Append to Fact_Sales (formula-based or Python)
   - Calculate Net_rev_unit, COGS_unit, etc.
   - One row per transaction

4. Extend Fact_Sales_Daily (Date × SKU_key pairs)
   - Add new (Date, SKU_key) rows
   - SUMIFS auto-calculate from Fact_Sales

5. Refresh ABC_View (XLOOKUP from Fact_Sales_Daily)
   - D_30 recalculates
   - Status flags update
```

### 4.2 V15 Implementation Note

For V15, we will **NOT create Fact_Sales_Raw** as a separate sheet. Instead:

1. Document that OrderID/Kaspi identifiers live in `SALES_KSP_CRM_GPT_15.9.25.xlsx` (legacy) and future raw exports
2. Fix Fact_Sales_Daily formulas first
3. Fact_Sales_Raw becomes a Project 3 (CRM) responsibility

**Rationale:** Adding a new sheet risks Mac Excel complexity. The immediate priority is fixing M-003, M-004, M-005.

---

## 5. Documentation Updates Required

| Document | Section | Change |
|----------|---------|--------|
| Master_Inventory_Rules_v5.2 | §10 Table Map | Add Fact_Sales_Raw definition |
| Master_Inventory_Rules_v5.2 | §5.1.1 | Confirm 3-state Status logic |
| Automation_Handoff.md | Data Sources | List legacy file roles |
| Mismatch_Resolution_Log_v3 | M-006 | Mark as RESOLVED (Option C) |

---

## 6. Validation Checklist

Before promoting V15:

- [ ] Fact_Sales_Daily.Revenue (D) sums Fact_Sales.Line_NetRev (column I)
- [ ] Fact_Sales_Daily.Delivery (E) sums Fact_Sales.Delivery_fee (column G)
- [ ] Fact_Sales_Daily.COGS (F) sums Fact_Sales.COGS_line (column K)
- [ ] Fact_Sales_Daily.Profit (G) sums Fact_Sales.Profit_line (column M)
- [ ] No hard-coded values in Fact_Sales_Daily data body
- [ ] ABC_View.Status uses 3-state logic (Total first, then Current)
- [ ] Fact_PO_Lines.Status has no formula dependency on Dim_PO_Header

---

*Document version: 1.0*  
*Last updated: December 4, 2025*
