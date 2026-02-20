# Excel UI Contract for CRM (V1)
## Bridge Document: Project 1 (Excel) ↔ Project 3 (Python/DB)
**Created:** December 4, 2025  
**Status:** Active contract (Kaspi-only, v8/V16)

---

## 1. Purpose

This document defines the **interface contract** between:
- **Project 1 (Excel UI):** `Inventory_Core_V18.1_V2.xlsx` — UI only
- **Project 3 (CRM/DB):** Python/DB system — system of record

Both systems must implement identical business logic as defined in
`inventory/Master_Inventory_Rules_v8.md` (Kaspi-only).

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   KASPI                         PROJECT 3 (Python/DB)                       │
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
│   Inventory_Core_V18.1_V2.xlsx                      Web UI / Mobile         │
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

These are the **decision columns** Python must replicate.  
**Formula source of truth:** `inventory/Master_Inventory_Rules_v8.md`  
**Note:** safety stock and ROP must use **Effective_L** (not raw L).

| Column | Excel | Meaning | Python Must Match |
|--------|-------|---------|-------------------|
| J | D_30 | Daily demand | ✓ |
| K | Sigma_MAD | Demand volatility | ✓ |
| Q | SS_demand | Demand safety stock | ✓ |
| R | SS_floor | Buffer floor | ✓ |
| S | SS_mix | Size-mix buffer (CL only) | ✓ |
| T | SS_total | Total safety stock | ✓ |
| U | ROP | Reorder point | ✓ |
| V | T_post_days | Coverage post-arrival | ✓ |
| AB | ROIC_pct | Monthly ROIC | ✓ |
| AC | Suggested_Order_Qty | Suggested order qty | ✓ |
| AD | Status | 3-state logic (see §5.2) | ✓ |

### 4.2 Fact_Sales Column Map (V16)

| Col | Header | Type | Python Equivalent |
|-----|--------|------|-------------------|
| A | Date | Data | `order_date` |
| B | OrderID | Data | `order_id` |
| C | Kaspi_Offer_name | Data | `kaspi_offer_name` |
| D | SKU_key | Data | `sku_key` |
| E | SKU_ID | Data | `sku_id` |
| F | Quantity | Data | `quantity` |
| G | Sell_price_kzt | Data | `sell_price_kzt` |
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

## 5. Logic Invariants (no formulas in this doc)

All formulas live in `docs/inventory/Master_Inventory_Rules_v8.md`; do not duplicate formulas in this contract doc.

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

1. Start from known-good template (Inventory_Core_V18.1_V2.xlsx)
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
3. Check `inventory/Master_Inventory_Rules_v8.md`
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
| New Kaspi delivery type | Update `Dim_Delivery_Fees` | Coordinate both systems |

### 9.2 Version Sync

| Document | Excel Version | Python Must Match |
|----------|---------------|-------------------|
| `inventory/Master_Inventory_Rules_v8.md` | V18.1_V2 | Same formulas |
| `inventory/Sales_Data_Model_V16.md` | V18.1_V2 | Same column layout |

---

## 10. Summary

**Excel (Inventory_Core_V18.1_V2.xlsx):**
- Frozen as UI
- Manual review and validation
- Reference implementation of formulas

**Python (Project 3):**
- Automated brain
- Real-time ingestion
- Same formulas as Excel

**Contract:**
- `Master_Inventory_Rules_v8.md` is the shared truth
- Both systems must produce identical outputs for same inputs

---

*This contract is binding for both Project 1 (Excel) and Project 3 (CRM). Any changes require doc update first.*
