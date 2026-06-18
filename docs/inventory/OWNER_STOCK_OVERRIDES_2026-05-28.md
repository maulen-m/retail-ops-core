# Owner Stock Overrides And Planning Anchors - 2026-05-28

Status: owner-confirmed planning truth until a later real-life recount or CodeCaptain-approved replacement.

This document records owner-provided stock and economics corrections from `2026-05-28`. Use these corrections before any sales-state, ads, inventory-capital, or PO planning decision. This document is not production DB truth by itself and does not authorize any live write.

## Current Depleted Inventory Planning Anchor

Use the latest all-products depleted planning packet as the current general stock anchor until a newer real-life recount is provided:

`~/Docs/Autonomous_business/exports/validation/inventory_capital_po_decision_all_products_depleted_v3_20260527_192134`

Primary workbook:

`~/Docs/Autonomous_business/exports/validation/inventory_capital_po_decision_all_products_depleted_v3_20260527_192134/inventory_capital_po_decision_all_products_depleted_v3_workbook.xlsx`

Important boundary:

- Gate was `RED_BOUNDARY_DRIFT_OBSERVED`, so this is decision-support/planning truth, not production inventory truth.
- It represented all `256` April 23 anchor rows and applied explicit physical/economic depletion.
- Physical depletion uses ship-date evidence.
- Economic final-sales depletion uses WebUI status-change date for delivered rows.
- It remains subject to retained blockers: unmatched depletion rows, inbound addbacks, return-QC addbacks, and confidence gaps.

## Product-Specific Overrides

These owner overrides take precedence over the general V3 planning anchor for the listed SKU families/sizes.

### RUSH31

Timestamp: `28.05.2026_21_38_20`

SKU key: `CL_NC_MEN_RUSH-31_BLACK`

Product identity: independent men's RUSH `3 in 1` product: shorts, leggings, and longsleeve/rashguard. Do not treat this as a LINE61 parent child-bundle depletion route.

Owner-confirmed stock:

| size | qty |
| --- | ---: |
| S | 60 |
| M | 30 |
| L | 50 |
| XL | 70 |
| 2XL | 50 |
| 3XL | 30 |
| 4XL | 0 |
| Total | 290 |

4XL note: no sellable 4XL quantity was included in the owner-confirmed `290` units. Treat RUSH31 4XL as `0` / not sellable unless a later owner count explicitly overrides this.

Commercial planning note:

- First RUSH31 price step should be `9,990 KZT`.
- Then test lower price points such as `8,990 KZT` and `7,990 KZT`.
- Use `5-7` day intervals unless a later external expert answer gives a stronger reason to change the interval.
- Earlier owner context suggested `BID >= 100` may be needed because historical `40-80` bids starved this exact product of views. Treat this as a candidate for dry-run planning, not live approval.

### LINE61

Timestamp: `2026-05-25 17:10:38 +05`

SKU key: `CL_NEW-CLO2_MEN_SUIT-61_BLACK`

Owner override:

| size | qty |
| --- | ---: |
| L | 151 |
| XL | 100 |
| 2XL | 24 |
| 3XL | 25 |

Use these values for LINE61 stock-sensitive parent and bundle planning unless a later real-life recount supersedes them.

### LINE51 4XL

SKU key: `CL_OC_MEN_LINE51_WHITE`

Owner override:

| size | qty |
| --- | ---: |
| 4XL | 0 |

Use this to block/scrutinize any LINE51 4XL sale-state, campaign, or stock activation route.

### LINE52

Timestamp: `28.05.2026_21_47_52`

SKU key: `CL_OC_MEN_LINE52_BLACK`

Owner override:

| size | qty |
| --- | ---: |
| S | 118 |
| M | 50 |
| L | 80 |
| XL | 0 |
| 2XL | 0 |
| 3XL | 50 |
| 4XL | 0 |
| Total | 298 |

Use this override before reorder, inventory-capital, sales-state, or marketing decisions for LINE52.

## LINE31 Exception To The General V3 Anchor

LINE31 stock cannot be trusted only from the general depleted V3 anchor because it does not fully reflect later PO-1A receipt and there is a more specific LINE31 snapshot.

For LINE31, use this source as the stock snapshot anchor:

`~/Cowork/Projects/E-commerce/docs/inventory/products/LINE31_sales__STOCK_13.4.26.md`

Then subtract following-day sales after that snapshot using the same depletion logic used by the inventory rebuild. Add PO-1A received stock where separately proven.

Related LINE31 sales evidence:

`~/Cowork/Projects/E-commerce/docs/inventory/products/LINE31_sales__LINE31_sales.md`

LINE31 sales-price note:

- LINE31 had historical April sales at `16,990 KZT`.
- Do not treat LINE31 as an unproven `8,990 KZT` discovery product without first reconciling this historical sales evidence.

## Gift Bag COGS Rule

Owner-confirmed rule:

- Gift belt bag COGS applies internally to all current ACMEWEAR/Kaspi offers and near-term Instagram/countrywide/local campaign offers.
- Use `3 CNY` per unit and `100 g` added weight as the internal economics adjustment unless a later source provides a more exact value.
- Internal COGS should include the gift bag: `COGS = garment/base cost + delivery cost + gift bag cost + gift bag delivery weight effect`.

Customer-facing copy boundary:

- Kaspi customer-facing `Комплектация` / description should not necessarily list the gift bag unless it is already part of the approved copy.
- Instagram ad descriptions, ad videos, and landing pages may specify the gift bag if the route already supports it and the copy is owner-approved.

## Safety Boundary

This document records owner truth and planning overrides only. It does not authorize:

- production DB writes,
- workbook writes,
- source-pointer writes,
- scheduler changes,
- Web_automation writes,
- Kaspi/API/WebUI/Meta/CRM mutations,
- campaign bid/budget/state changes,
- price changes,
- stock changes,
- supplier messages,
- payment,
- PO commitment,
- owner publication,
- production preflight,
- production apply.

