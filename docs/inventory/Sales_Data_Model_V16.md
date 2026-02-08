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
- Kaspi `Артикул` embeds `sku_key` at the beginning. Parsers must strip trailing size/id tokens and use the prefix as `SKU_key` (and `SKU_ID = SKU_key + size` when size is present).

---

## 5. Portfolio Scope (DB)

**Table:** `portfolio_active`  
**Purpose:** Explicit list of SKUs that must be covered by dashboard readiness gates.

| Col | Header | Type | Notes |
|---:|---|---|---|
| A | sku_key | TEXT (PK) | Style-level SKU |
| B | active_flag | INTEGER | 1 = in portfolio, 0 = excluded |
| C | notes | TEXT | Optional reason/context |
| D | updated_at | DATETIME | Auto-updated timestamp |

---

## 6. Size Synonyms (DB)

**Table:** `dim_size_synonyms`  
**Purpose:** Canonicalize size aliases to a single MY_SIZE value.

| Col | Header | Type | Notes |
|---:|---|---|---|
| A | alias | TEXT (PK) | Normalized alias (uppercase, no spaces) |
| B | canonical_size | TEXT | Canonical size (e.g., 2XL, ONE_SIZE) |
| C | notes | TEXT | Optional context |
| D | updated_at | DATETIME | Auto-updated timestamp |

---

## 7. PO Part Tracking (DB)

**Tables:** `po_header`, `po_part`, `po_line`  
**Purpose:** Preserve split-shipment truth (`po_part_id`) while keeping PO-level lifecycle aggregates.

### 7.1 `po_part`

| Col | Type | Notes |
|---|---|---|
| `po_part_id` | TEXT (PK) | Split shipment identity (for example `PO-5.1`, `ARC-1.0`) |
| `po_id` | TEXT | Parent PO (`PO-5`, `PO_ARC-1`) |
| `supplier_id` | TEXT | Supplier code from inbound calendar |
| `message_date` | TEXT | Part-level message date |
| `cargo_send_date` | TEXT | Part-level cargo send date |
| `estimated_arrival_date` | TEXT | Part-level ETA |
| `actual_arrival_date` | TEXT | Part-level actual arrival date |
| `status` | TEXT | `IN_TRANSIT` / `RECEIVED` / other normalized lifecycle states |
| `total_units` | INTEGER | Total units in this part |
| `base_cost_cny` | REAL | Part-level base cost in CNY |
| `base_cost_kzt` | REAL | Part-level base cost in KZT |
| `est_weight_kg` | REAL | Part-level estimated weight |
| `total_bags` | INTEGER | Part-level bag count |
| `est_delivery_usd` | REAL | Estimated delivery in USD |
| `est_delivery_kzt` | REAL | Estimated delivery in KZT |
| `is_paid_base` | INTEGER | 1 when base cost is paid |
| `is_paid_dlv` | INTEGER | 1 when delivery is paid |
| `to_pay_base_kzt` | REAL | Remaining base amount unpaid |
| `to_pay_dlv_kzt` | REAL | Remaining delivery amount unpaid |

### 7.2 `po_line` addition

| Col | Type | Notes |
|---|---|---|
| `po_part_id` | TEXT | New linkage to `po_part.po_part_id`; required for split inbound truth |

### 7.3 Inbound workbook sync source

- Workbook: `Inbound_calendar_V10.002.xlsx`
- Sheets:
  - `Inbounds_sheet` (size-grain line truth)
  - `PO_part_id_Totals` (part-level totals and status)
  - `DIM_SKU_light_v5` (ARC target sell price source via `AvgPrc`)

*Kaspi-only until further notice.*
