# Excel UI Contract for CRM (V1)
## Bridge Document: Project 1 (Excel) ↔ Project 3 (Python/DB)
**Created:** December 4, 2025  
**Status:** Active contract

---

## 1. Purpose

This document defines the **interface contract** between:
- **Project 1 (Excel):** Inventory_Core_V15_FINAL.xlsx — frozen as UI
- **Project 3 (CRM):** Python/DB system — automated brain

Both systems must implement identical business logic as defined in `Master_Inventory_Rules_v5.3.md`.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   KASPI/WB                      PROJECT 3 (Python/DB)                       │
│   ────────                      ─────────────────────                       │
│                                                                             │
│   Raw Export    ─────────────►  Fact_Sales_Raw (DB table)                   │
│   (ActiveOrders format)         ├── OrderID                                 │
│                                 ├── Kaspi_Offer_name                        │
│                                 ├── Full order details                      │
│                                 └── Status tracking                         │
│                                          │                                  │
│                                          ▼                                  │
│                                 Fact_Sales (cleaned)                        │
│                                 ├── SKU_key + economics                     │
│                                 └── Derived calculations                    │
│                                          │                                  │
│                                          ▼                                  │
│                                 ROIC/ROP/SS calculations                    │
│                                          │                                  │
│                    ┌─────────────────────┴─────────────────────┐            │
│                    ▼                                           ▼            │
│   PROJECT 1 (Excel UI)                              Dashboards/APIs         │
│   ────────────────────                              ────────────────        │
│   Inventory_Core_V15_FINAL.xlsx                     Web UI / Mobile         │
│   ├── ABC_View (manual review)                      WhatsApp alerts         │
│   ├── Fact_Sales (reference)                        Kaspi API calls         │
│   └── tb_Inbound (validation)                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. What Project 3 Must Provide to Excel

### 3.1 Required Data Exports (if Excel needs refresh)

| Export | Format | Frequency | Columns |
|--------|--------|-----------|---------|
| `sales_daily.csv` | CSV | On-demand | Date, SKU_key, Units, Revenue, Delivery, COGS, Profit |
| `sku_master.csv` | CSV | On-demand | SKU_key, Product_Type, Weight, COGS_unit, Current_stock |
| `po_status.csv` | CSV | On-demand | PO_Id, SKU_KEY, MY_SIZE, Status, Ast_arrival_date |

### 3.2 Format Requirements

**Date format:** `YYYY-MM-DD` (ISO 8601)  
**Decimal separator:** `.` (dot)  
**Encoding:** UTF-8  
**Currency:** KZT (integers, no decimals)

### 3.3 When Excel Needs Data

Excel is **passive** — it doesn't pull data automatically. Scenarios where Adil might manually import:

| Scenario | Action |
|----------|--------|
| Validate Python calculations | Export daily aggregates, compare to Fact_Sales_Daily |
| Manual PO decision | Review ABC_View, cross-check with Python dashboard |
| Debug discrepancy | Compare SKU-level ROIC between Excel and DB |

---

## 4. What Excel Provides (Reference Outputs)

### 4.1 ABC_View Columns

These are the **decision columns** Python must replicate:

| Column | Excel | Formula | Python Must Match |
|--------|-------|---------|-------------------|
| J | D_30 | `SUMIFS(sales_30d) / 30` | ✓ |
| K | Sigma_MAD | `D_30 × 0.4` | ✓ |
| Q | SS_demand | `z × σ × √L` | ✓ |
| R | SS_floor | `D × B` | ✓ |
| S | SS_mix | `TV × D × L` | ✓ |
| T | SS_total | `Q + R + S` | ✓ |
| U | ROP | `D × L + SS_total` | ✓ |
| V | T_post_days | `R + SS_total / D` | ✓ |
| AB | ROIC_pct | `(Profit × D × 30) / K_avg` | ✓ |
| AC | Suggested_Order_Qty | `MAX(0, T_post × D - Total_stock)` | ✓ |
| AD | Status | 3-state logic (see §5.2) | ✓ |

### 4.2 Fact_Sales Column Map (V15)

| Col | Header | Type | Python Equivalent |
|-----|--------|------|-------------------|
| A | Date | Data | `order_date` |
| B | OrderID | Data | `order_id` |
| C | Kaspi_Offer_name | Data | `offer_name` |
| D | SKU_key | Data | `sku_key` |
| E | SKU_ID | Data | `sku_id` |
| F | Quantity | Data | `quantity` |
| G | Sell_price_kzt | Data | `sell_price` |
| H | Product_Type | Data | `product_type` |
| I | Channel | Data | `channel` |
| J | Delivery_fee | Calc | `delivery_fee` |
| K | Net_rev_unit | Calc | `net_rev_unit` |
| L | Line_NetRev | Calc | `line_net_rev` |
| M | COGS_unit | Calc | `cogs_unit` |
| N | COGS_line | Calc | `cogs_line` |
| O | Profit_unit | Calc | `profit_unit` |
| P | Profit_line | Calc | `profit_line` |

---

## 5. Business Logic Contract

### 5.1 Formulas Python Must Implement Identically

**Source:** `Master_Inventory_Rules_v5.3.md`

```python
# COGS
COGS_unit = BaseCost_CNY * 78 + Weight_kg * 2.66 * 530

# Delivery fee (Kaspi)
if sell_price <= 4999:
    delivery_fee = 0
elif sell_price <= 14999:
    delivery_fee = 856
else:
    delivery_fee = 1259

# Net revenue
net_rev_unit = (sell_price * (1 - 0.125) - delivery_fee) * (1 - 0.03)

# Sigma (approximation)
sigma = D_30 * 0.4

# Safety stock
SS_demand = z * sigma * math.sqrt(L)
SS_floor = D * B
SS_mix = TV * D * L
SS_total = SS_demand + SS_floor + SS_mix

# Reorder point
ROP = D * L + SS_total

# ROIC
K_avg = D * (L + R/2) * COGS + SS_total * COGS
monthly_profit = unit_profit * D * 30
monthly_ROIC = monthly_profit / K_avg
```

### 5.2 Status Flag Logic (Critical)

**Order matters:** Check Total FIRST, then Current.

```python
def get_status(current_stock, total_stock, rop):
    if total_stock < rop:
        return "⚠️ REORDER"
    elif current_stock < rop:
        return "📦 WAIT (inbound)"
    else:
        return "✅ OK"
```

| Scenario | Current | Inbound | Total | ROP | Result |
|----------|---------|---------|-------|-----|--------|
| Nothing covers | 50 | 0 | 50 | 100 | REORDER |
| Inbound covers | 50 | 60 | 110 | 100 | WAIT |
| All good | 110 | 0 | 110 | 100 | OK |

---

## 6. Mac Excel Safety Constraints

Project 3 must NOT generate files that violate Mac Excel compatibility:

| Constraint | Reason |
|------------|--------|
| No external links | Mac Excel corrupts cross-workbook refs |
| No volatile array formulas | Performance + corruption risk |
| Preserve `sharedStrings.xml` | Required for Mac |
| Preserve `calcChain.xml` | Required for Mac |
| No `wb.create_sheet()` via openpyxl | Generates minimal XML |
| Use lxml for modifications | See `Mac_Excel_Agent_Protocol_V2.md` |

### 6.1 If Python Generates Excel Files

Use the safe pattern from `Mac_Excel_Agent_Protocol_V2.md`:

1. Start from known-good template (V15_FINAL)
2. Extract to temp folder
3. Modify XML with lxml
4. Repack with zipfile
5. Verify before delivering

---

## 7. Data Source Hierarchy

### 7.1 Legacy Sales

| File | Role | Python Access |
|------|------|---------------|
| `SALES_KSP_CRM_GPT_15.9.25.xlsx` | Canonical legacy rows | Import Archive_sales sheet |
| `SALES_KSP_CRM_V3.xlsx` | Column semantics | Reference only |

### 7.2 Future Ingestion

| Source | Format | Python Responsibility |
|--------|--------|----------------------|
| Kaspi raw export | ActiveOrders_Example.xlsx format | Parse → Fact_Sales_Raw |
| WB export | TBD | Parse → Fact_Sales_Raw |

### 7.3 Fact_Sales_Raw (DB only)

**This table exists in Python/DB, not Excel.**

| Column | Source |
|--------|--------|
| OrderID | № заказа |
| Order_date | Дата поступления заказа |
| Kaspi_offer | Название товара в Kaspi Магазине |
| Kaspi_article | Артикул |
| Sell_price_kzt | Сумма |
| Quantity | Количество |
| Delivery_fee_seller | Стоимость доставки для продавца |
| Delivery_fee_buyer | Стоимость доставки для покупателя |
| Status | Статус |

---

## 8. Validation Protocol

### 8.1 When Python and Excel Disagree

1. Identify the SKU and metric
2. Compare formula implementations
3. Check `Master_Inventory_Rules_v5.3.md`
4. **Rules doc is authoritative**
5. Fix whichever system is wrong

### 8.2 Acceptance Criteria for Python

Before declaring Python "production ready":

| Check | Threshold |
|-------|-----------|
| D_30 matches Excel | ±1% |
| SS_total matches Excel | ±1% |
| ROIC matches Excel | ±2% |
| Status flags identical | 100% |
| Suggested_Order_Qty | ±1 unit |

### 8.3 Test SKUs

Use these for validation:

| SKU | Why |
|-----|-----|
| `CL_OC_MEN_LINE52_BLACK` | High volume, 74% of sales |
| `CL_OC_MEN_LINE51_WHITE` | Second highest, monopoly position |
| Any slow-mover | Edge case: low D_30, high uncertainty |

---

## 9. Change Control

### 9.1 Who Can Change What

| Change Type | Authority | Process |
|-------------|-----------|---------|
| Formula change | Must update `Master_Inventory_Rules` first | Doc → Excel → Python |
| Parameter change (L, B, z) | Update `Dim_Params` or `Dim_Params_PT` | Both systems update |
| New SKU | Add to `Dim_SKU` | Python DB is source of truth |
| New platform (Ozon) | Add row to `Dim_Params_PT` | Coordinate both systems |

### 9.2 Version Sync

| Document | Excel Version | Python Must Match |
|----------|---------------|-------------------|
| `Master_Inventory_Rules_v5.3.md` | V15_FINAL | Same formulas |
| `Sales_Data_Model_V15.md` | V15_FINAL | Same column layout |

---

## 10. Summary

**Excel (V15_FINAL):**
- Frozen as UI
- Manual review and validation
- Reference implementation of formulas

**Python (Project 3):**
- Automated brain
- Real-time ingestion
- Same formulas as Excel

**Contract:**
- `Master_Inventory_Rules_v5.3.md` is the shared truth
- Both systems must produce identical outputs for same inputs

---

*This contract is binding for both Project 1 (Excel) and Project 3 (CRM). Any changes require doc update first.*
