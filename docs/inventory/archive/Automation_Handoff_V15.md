# ARCHIVED — superseded by current owners. Do not implement from this file.

Current owners (authoritative):
- Formulas: `inventory/Master_Inventory_Rules_v8.md`
- Schema: `Sales_Data_Model_V16.md`
- Tolerances/contracts: `docs/validation/PO_CONTRACT.md`, `docs/validation/DASHBOARD_CONTRACT.md`, `docs/validation/DAY_COMPLETE_CONTRACT.md`

This document is retained for historical reference only.

# Automation Handoff — V15_FINAL
## Project 1 → Project 3 Transition Document
**Created:** December 4, 2025  
**Source:** Inventory_Core_V15_FINAL.xlsx  
**Target:** Project 3 CRM/Python Implementation

---

## 1. Executive Summary

Project 1 (Excel Business Brain) is now **FROZEN AS UI**. This document hands off to Project 3 (CRM/Python) the specifications needed to implement identical business logic in code.

**Key files (legacy, historical only):**
- `Inventory_Core_V15_FINAL.xlsx` — Legacy reference implementation
- `Master_Inventory_Rules_v5.3.md` — Legacy formula contract (superseded by v8)
- `Excel_UI_Contract_for_CRM_V1.md` — Interface specification

---

## 2. What Project 3 Must Build

### 2.1 Database Tables

| Table | Purpose | Grain |
|-------|---------|-------|
| `fact_sales_raw` | Raw Kaspi/WB exports | Order line |
| `fact_sales` | Cleaned transactions | Date × SKU × OrderID |
| `fact_sales_daily` | Daily aggregates | Date × SKU |
| `dim_sku` | SKU master | SKU_key |
| `dim_params` | Global parameters | Param name |
| `dim_params_pt` | Product_Type overrides | Product_Type |
| `fact_po_lines` | PO tracking | PO × SKU × Size |

### 2.2 Core Calculations

Python must implement these identically to Excel:

```python
# From Master_Inventory_Rules_v5.3.md

# COGS
cogs_unit = base_cost_cny * 78 + weight_kg * 2.66 * 530

# Delivery fee (Kaspi)
delivery_fee = 0 if price <= 4999 else (856 if price <= 14999 else 1259)

# Net revenue
net_rev_unit = (price * 0.875 - delivery_fee) * 0.97

# Demand
d_30 = sum(sales_30d) / 30
sigma = d_30 * 0.4

# Safety stock
ss_demand = z * sigma * sqrt(L)
ss_floor = d_30 * B
ss_mix = TV * d_30 * L
ss_total = ss_demand + ss_floor + ss_mix

# Reorder point
rop = d_30 * L + ss_total

# ROIC
k_avg = d_30 * (L + R/2) * cogs + ss_total * cogs
monthly_roic = (unit_profit * d_30 * 30) / k_avg

# Status (CRITICAL: check Total first)
status = "REORDER" if total_stock < rop else ("WAIT" if current_stock < rop else "OK")
```

### 2.3 Automation Workflows

| Workflow | Trigger | Action |
|----------|---------|--------|
| Sales ingestion | Daily/scheduled | Parse Kaspi export → fact_sales_raw → fact_sales |
| Daily aggregation | After ingestion | Rebuild fact_sales_daily |
| ROIC refresh | After aggregation | Recalculate ABC metrics per SKU |
| Reorder alerts | When status = REORDER | WhatsApp/Telegram notification |
| PO status update | When goods ship/arrive | Update fact_po_lines.status |

---

## 3. Data Sources

### 3.1 Legacy Sales (One-Time Import)

| File | Rows | Use |
|------|------|-----|
| `SALES_KSP_CRM_GPT_15.9.25.xlsx` | 13,371 | Canonical historical transactions |

**Sheet:** Archive_sales  
**Import to:** fact_sales_raw, then clean → fact_sales

### 3.2 Future Ingestion

| Source | Format | Notes |
|--------|--------|-------|
| Kaspi daily export | ActiveOrders_Example.xlsx format | See column mapping below |
| WB export | TBD | Similar structure expected |

### 3.3 ActiveOrders Column Mapping

| Kaspi Column (Russian) | DB Column |
|------------------------|-----------|
| `№ заказа` | order_id |
| `Дата поступления заказа` | order_date |
| `Название товара в Kaspi Магазине` | kaspi_offer |
| `Артикул` | kaspi_article |
| `Сумма` | sell_price_kzt |
| `Количество` | quantity |
| `Стоимость доставки для продавца` | delivery_fee_seller |
| `Стоимость доставки для покупателя` | delivery_fee_buyer |
| `Статус` | order_status |

---

## 4. Excel V15 Column Reference

### 4.1 Fact_Sales (V15 Layout)

| Col | Header | Type |
|-----|--------|------|
| A | Date | Data |
| B | OrderID | Data |
| C | Kaspi_Offer_name | Data |
| D | SKU_key | Data |
| E | SKU_ID | Data |
| F | Quantity | Data |
| G | Sell_price_kzt | Data |
| H | Product_Type | Data |
| I | Channel | Data |
| J | Delivery_fee | Formula |
| K | Net_rev_unit | Formula |
| L | Line_NetRev | Formula |
| M | COGS_unit | Formula |
| N | COGS_line | Formula |
| O | Profit_unit | Formula |
| P | Profit_line | Formula |

### 4.2 Fact_Sales_Daily (V15 Layout)

| Col | Header | Source Column |
|-----|--------|---------------|
| A | Date | — |
| B | SKU_key | — |
| C | Units | F (Quantity) |
| D | Revenue | L (Line_NetRev) |
| E | Delivery | J (Delivery_fee) |
| F | COGS | N (COGS_line) |
| G | Profit | P (Profit_line) |

### 4.3 ABC_View Key Columns

| Col | Header | Python Variable |
|-----|--------|-----------------|
| C | Current_stock | current_stock |
| E | Total_stock | total_stock |
| J | D_30 | d_30 |
| K | Sigma_MAD | sigma |
| T | SS_total | ss_total |
| U | ROP | rop |
| AB | ROIC_pct | monthly_roic |
| AC | Suggested_Order_Qty | suggested_order |
| AD | Status | status |

---

## 5. Parameters Reference

### 5.1 Global (Dim_Params)

| Param | Value |
|-------|-------|
| R_days | 10 |
| L_days | 21 |
| B_days | 14 |
| z_factor | 1.65 |
| TV_mix_floor | 0.23 |
| VAT_rate | 0.03 |
| Commission | 0.125 |
| CNY_KZT | 78 |
| USD_KZT | 530 |
| Cargo_rate_CL | 2.66 |

### 5.2 By Product_Type (Dim_Params_PT)

| Product_Type | L_days | B_days | Commission | Platform |
|--------------|--------|--------|------------|----------|
| CL | 21 | 14 | 0.125 | Kaspi |
| ELS | 20 | 21 | 0.125 | Kaspi |
| WB | 32 | 14 | 0.245 | Wildberries |

---

## 6. Validation Requirements

Before Project 3 goes live:

| Check | Method | Threshold |
|-------|--------|-----------|
| D_30 accuracy | Compare to Excel ABC_View.J | ±1% |
| SS_total accuracy | Compare to Excel ABC_View.T | ±1% |
| ROIC accuracy | Compare to Excel ABC_View.AB | ±2% |
| Status flags | Compare to Excel ABC_View.AD | 100% match |
| Suggested order | Compare to Excel ABC_View.AC | ±1 unit |

### 6.1 Test SKUs

| SKU | Volume | Notes |
|-----|--------|-------|
| CL_OC_MEN_LINE52_BLACK | 74% of sales | Main validation target |
| CL_OC_MEN_LINE51_WHITE | 10% of sales | Second priority |
| Any ELS SKU | Low volume | Edge case testing |

---

## 7. Handoff Checklist

For Project 3 to accept handoff:

- [ ] Reviewed `Master_Inventory_Rules_v5.3.md`
- [ ] Reviewed `Sales_Data_Model_V15.md`
- [ ] Reviewed `Excel_UI_Contract_for_CRM_V1.md`
- [ ] Understood Fact_Sales column layout (A-P)
- [ ] Understood Fact_Sales_Daily as derived view
- [ ] Understood 3-state Status logic (Total first)
- [ ] Imported legacy sales from GPT file
- [ ] Built fact_sales_raw schema
- [ ] Implemented core formulas
- [ ] Validated against Excel test cases

---

## 8. Contact Points

| Question | Resource |
|----------|----------|
| Formula definitions | Master_Inventory_Rules_v5.3.md |
| Column mappings | This document + Sales_Data_Model_V15.md |
| Interface contract | Excel_UI_Contract_for_CRM_V1.md |
| Excel internals | Mac_Excel_Agent_Protocol_V2.md |
| Business context | Adil_Business_Profile.md |

---

## 9. Known Limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| σ is approximation (D×0.4) | Not true MAD | Acceptable for operational decisions |
| No real-time stock sync | Stock drift possible | Weekly reconciliation |
| Manual PO status | Delay in inbound visibility | Project 3 automates |
| Excel is passive | No auto-refresh | Python is the brain |

---

## 10. Next Steps for Project 3

1. **Import legacy sales** from `SALES_KSP_CRM_GPT_15.9.25.xlsx`
2. **Build DB schema** per §2.1
3. **Implement formulas** per §2.2
4. **Validate** against Excel test cases
5. **Build ingestion pipeline** for daily Kaspi exports
6. **Build alerting** for REORDER status
7. **Go live** when validation passes

---

*This document transfers responsibility for automated inventory calculations from Project 1 (Excel) to Project 3 (Python/DB). Excel remains as UI and validation reference.*
