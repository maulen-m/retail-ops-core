# Sales Data Model V16 (Kaspi-only)
## Inventory_Core_V18.1_V2.xlsx
**Created:** 2026-01-05  
**Scope:** Kaspi-only sales data model aligned to `Master_Inventory_Rules_v8.md`

---

## 1. Overview

This document defines the authoritative **Fact_Sales** and **Fact_Sales_Daily** layouts
used by the Excel UI and Python/DB pipeline. Any deviations must be reflected in v8.

**Source of truth:** `inventory/Master_Inventory_Rules_v8.md`

---

## 2. Fact_Sales (V16)

**Grain:** Order line (OrderID × SKU_ID × Store)  
**Purpose:** Transaction-level economics for inventory math

| Col | Header | Type | Notes |
|---:|---|---|---|
| A | Date | Data | Order date |
| B | OrderID | Data | Kaspi order ID |
| C | Kaspi_Offer_name | Data | Listing title |
| D | SKU_key | Data | Style-level SKU |
| E | SKU_ID | Data | Size-level SKU |
| F | Quantity | Data | Units sold |
| G | Sell_price_kzt | Data | Unit price |
| H | Product_Type | Data | CL / ELS / FUR |
| I | Channel | Data | Always `Kaspi` |
| J | Delivery_fee | Calc | From `Dim_Delivery_Fees` matrix |
| K | Net_rev_unit | Calc | `(G*(1-0.125)-J)*(1-0.04)` |
| L | Line_NetRev | Calc | `K*F` |
| M | COGS_unit | Calc | See v8 (FX + cargo + base cost) |
| N | COGS_line | Calc | `M*F` |
| O | Profit_unit | Calc | `K-M` |
| P | Profit_line | Calc | `O*F` |

---

## 3. Fact_Sales_Daily (V16)

**Grain:** Date × SKU_key  
**Purpose:** Daily aggregates for demand and ABC_View

| Col | Header | Type | Notes |
|---:|---|---|---|
| A | Date | Key | Calendar date |
| B | SKU_key | Key | Style-level SKU |
| C | Product_Type | Data | CL / ELS / FUR |
| D | Channel | Data | Always `Kaspi` |
| E | Units | Calc | Σ Quantity |
| F | Orders | Calc | Count of OrderID |
| G | ASP_kzt | Calc | Revenue / Units |
| H | Delivery_kzt | Calc | Σ Delivery_fee |
| I | Revenue_kzt | Calc | Σ Line_NetRev |
| J | COGS_kzt | Calc | Σ COGS_line |
| K | Profit_kzt | Calc | Σ Profit_line |

---

## 4. Notes

- Delivery fees must use the **matrix lookup** (v8). No legacy tiers.
- VAT = **0.04** is enforced in Net_rev_unit.
- All formulas follow `Master_Inventory_Rules_v8.md`.

---

*Kaspi-only until further notice.*
