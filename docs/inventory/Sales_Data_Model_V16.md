# Sales Data Model V16 (Kaspi-only)
## Inventory_Core_V18.1_V2.xlsx
**Created:** 2026-01-05  
**Scope:** Kaspi-only sales data model aligned to `Master_Inventory_Rules_v9.md`

---

## 1. Overview

This document defines the authoritative **Fact_Sales** and **Fact_Sales_Daily** layouts
used by the Excel UI and Python/DB pipeline. Any formula deviation must be reflected
in `Master_Inventory_Rules_v9.md` first, then here and in code/tests.

**Source of truth:** `inventory/Master_Inventory_Rules_v9.md`

### 1.1 Canonical date vocabulary lock

Sales and inventory rebuilds must keep warehouse movement dates separate from final
sales economics dates:

- `order_intake_date` is the customer order/creation date. WebUI source column:
  `Дата поступления заказа`; API source fields: `createdAt` / `creationDate`.
  It is demand/intake evidence only.
- `ship_date` is courier handoff, waybill, Telegram PDF shipped-workflow, or actual
  shipped workflow date. It is the date basis for warehouse on-hand depletion only.
- `sale_date`, `transaction_date`, and `delivered_at` are the WebUI
  `Дата изменения статуса` date for `Выдан` / delivered / completed rows. These
  are the date basis for COGS, cash, PnL, sales economics, and final-sales stock.
- `cancel_date` is the status-change date for cancelled rows. It is never a
  positive sale.
- `return_date` is the status-change date for returned rows. Returned units do not
  become active sellable stock unless a separate return-QC/source rule accepts them.

Do not collapse warehouse stock and final-sales/economic stock into one number.
`PHYSICAL_WAREHOUSE_STOCK_ESTIMATE` deducts shipped/sent orders by `ship_date`.
`ECONOMIC_FINAL_SALES_STOCK` deducts completed/bought-out sales by `sale_date`.
`order_intake_date` must not be used as final sale truth.

---

## 2. Fact_Sales (V16)

**Grain:** Order/public-offer line (OrderID x public offer identity x SKU_ID x Store).
`SKU_ID` is the internal mapped product/size identity, not the unique line key.
Separate Kaspi public offers/articles in the same order must remain separate rows
even when they map to the same internal SKU family.  
**Purpose:** Transaction-level economics for inventory math

| Col | Header | Type | Notes |
|---:|---|---|---|
| A | Date | Data | `sale_date` / `transaction_date`: WebUI status-change date for delivered/completed rows after the strict cutover; never order intake for stock, COGS, cash, or PnL |
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
| M | COGS_unit | Calc | See `Master_Inventory_Rules_v9.md` (FX + cargo + base cost) |
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

- Delivery fees must use the **matrix lookup** from `Master_Inventory_Rules_v9.md`. No legacy tiers.
- VAT = **0.04** is enforced in Net_rev_unit.
- All formulas follow `Master_Inventory_Rules_v9.md`.
- Kaspi `Артикул` embeds `sku_key` at the beginning. Parsers must strip trailing size/id tokens and use the prefix as `SKU_key` (and `SKU_ID = SKU_key + size` when size is present).
- ACMEWEAR child-bundle compact articles (`SUIT-*` / `LINE-*`, for example `SUIT-31-TS-ST-3XL-54`) are canonical article-map inputs, not raw text fallbacks. Their `Kaspi_name_core` is the owner-facing bundle core from `dim_kaspi_article_map` (for example `3в1_Черный_Футболка_+Сумка`), while compact `SKU_key` values such as `SUIT-31-TS` remain the parser/output key unless a future migration explicitly changes the SKU namespace.

### 4.1 ACMEWEAR child-bundle article-map contract

The May 2026 ACMEWEAR child-bundle launch introduced eight ST child groups for
LINE61 and LINE51. All platform articles for these groups must be present in
`dim_kaspi_article_map` before daily order processing, Google Ops Board publish,
waybill grouping, or sales replay treats them as resolved.

Required behavior:
- `dim_kaspi_article_map.kaspi_article` stores the platform merchant article, such as `SUIT-31-TS-ST-3XL-54`.
- `dim_kaspi_article_map.sku_key` stores the compact child offer key, such as `SUIT-31-TS`, matching the current parser contract.
- `dim_kaspi_article_map.sku_id` stores `sku_key + "_" + MY_SIZE`, such as `SUIT-31-TS_3XL`; duplicated platform tokens like `XL-48` and `XL-50` both resolve to internal `XL`.
- `dim_kaspi_article_map.kaspi_name_core` stores the operator-facing bundle core, such as `3в1_Черный_Футболка_+Сумка`, never the generic `Спортивный_костюм_ACMEWEAR`.
- Articles currently archived or no-stock on Kaspi must remain mapped for historical and overdue order parsing; article-map `active_flag=1` means "identity mapping is active", not "offer has sellable stock".
- Campaign attribution for child-bundle orders before campaign creation time remains blocked unless direct click/campaign evidence exists.

Child-bundle COGS boundary:
- Compact child bundles must not be made "resolved" by inventing fake `dim_sku.base_cost_cny` or `dim_sku.weight_kg` values on the compact child SKU.
- When approved component-level economics exist, copied-temp ChildSum proof may calculate unit COGS as `sum(component_base_cost_cny) * CNY_KZT + sum(component_weight_kg) * USD_KZT * DLV`.
- ChildSum proof requires explicit component rows for the child bundle, positive component cost and weight, `copied_temp_only=true`, and `production_write_authorized=false`.
- Parent aggregate economics, such as a full LINE61 parent cost/weight, are not enough to split a child bundle into top, shorts, and leggings by inference.
- Exact owner-approved production exceptions may resolve only the named sales rows through `fact_sales_owner_cogs_override`; this is row-level authority, not SKU-wide child-bundle economics.
- Missing component-level economics remain unresolved/YELLOW until a later owner-approved source route or production DB contract is reviewed.

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

---

## 8. PO Schedule / Lane Config

Runtime schedule and prep-lane truth for dashboard projections:
- `config/po_schedule.yaml`
  - `plan0_anchor_message_date`
  - `reorder_cycle_days`
  - `archive_sort`
  - `prep_lanes` (`CORE_PRINT_SUIT`, `GENERAL_CL`, `ELS`)

Dashboard row additions:
- `sku_level.prep_lane`, `sku_level.prep_days_lane`
- `size_level.prep_lane`, `size_level.prep_days_lane`

---

## 9. OPEX Commitments (Cashflow Link)

Canonical OPEX schedule artifacts:
- `config/opex/opex_schedule.yaml`
- `config/opex/opex_commitments.csv`

DB table:
- `fact_cashflow_commitments` (`commit_type='OPEX'`)

Sync entrypoint:
- `scripts/sync_opex_schedule.py` (dry-run by default; apply requires `ENABLE_CASHFLOW_WRITE=1` and `--apply`)

---

## 10. Operational Stock Truth P0 Schema

The operational-stock truth rollout uses these DB contracts before stock, order,
PO, ads, cashflow, or owner reports can be published as decision-grade:

| Table | Role |
|---|---|
| `source_manifest` | Source path/hash/freshness ledger |
| `pipeline_run` | Run-level status and source manifest binding |
| `validation_result` | Gate result records |
| `exception_queue` | Fail-closed exception records |
| `stock_anchor` | Immutable approved stock anchor metadata |
| `stock_adjustment_batch` | Audited adjustment batch metadata |
| `stock_ledger` | Append-only stock events with idempotency key support |
| `fact_inventory_snapshot_size` | Derived size-level physical stock snapshot |
| `offer_availability_snapshot` | Store offer availability separated from physical stock |
| `order_status_event` | Append-only order lifecycle spine |
| `return_qc_event` | Return/cancel quarantine and QC acceptance events |
| `fact_orders_kaspi`, `fact_order_entries_kaspi`, `sales_fact_v2` | Order and sales projections |
| `po_header`, `po_part`, `po_line` | PO and inbound part/line grain |
| `fact_cashflow_events`, `fact_cashflow_daily` | Cashflow event spine and daily roll-forward |
| `ads_source_refresh_runs`, `ads_campaign_product_daily` | Ads source coverage and product spend |
| `owner_report_snapshot` | Published owner report lineage and trust status |

Schema source:
- `scripts/migrate_028_operational_stock_truth_p0_schema.py`
- `scripts/validate_operational_stock_schema.py`

### 10.1 Operational Stock Integration Gates

Decision-grade owner outputs that depend on operational stock must also pass the
read-only Agent 7 integration gate:

- sales rows must bind to `order_status_event` completed lifecycle evidence and
  canonical `fact_order_entries_kaspi` rows; duplicate delivered projections for
  the same order/SKU grain block publication.
- returned or cancelled units must stay out of active sellable stock until
  `return_qc_event.accepted_active_qty` covers the positive restock quantity.
- PO inbound must be keyed to `po_part` or `po_line` grain, and received inbound
  must not remain in `fact_inventory_snapshot_size.inbound_stock`.
- missing, blocked, or stale ads coverage, including STOREB gaps, is not zero
  spend; it blocks profit/product-test decisions.
- D1 Kaspi Pay cashflow recognizes delivered orders as same-day cash-in, not
  receivables, and `fact_cashflow_daily` must roll forward opening balances from
  prior closes.

Gate source:
- `core/ops/operational_stock_integration_gates.py`
- `scripts/validate_operational_stock_integration_gates.py`
