# API Gap Opportunity Examples

This document summarizes what the Kaspi API gap implementation unlocks and gives concrete examples of the operational and financial opportunities.

## 1) Accurate line‑item economics

**What changes:** We stop treating a multi‑line order as a single unit with totalPrice. We store each line with quantity, basePrice, deliveryCost, and weight.

**Opportunity:** Accurate margin per SKU and correct COGS allocation.

**Example:**
- Order has 3 items (A, B, C). Today it appears as qty=1 and totalPrice=6,700.
- After line‑item capture:
  - SKU A: net rev 3,000; cogs 1,800; delivery fee 150 → margin 1,050
  - SKU B: net rev 2,500; cogs 2,100; delivery fee 120 → margin 280
  - SKU C: net rev 1,200; cogs 900; delivery fee 80 → margin 220

## 2) Inventory depletion by SKU + size

**What changes:** We use order entry data for exact SKU/size consumption.

**Opportunity:** Better size allocation and earlier OOS detection.

**Example:**
- A product sells in sizes S/M/L, but today the order is treated as qty=1.
- After line‑item capture, we see size‑level demand distribution and can adjust PO sizing.

## 3) Delivery cost allocation

**What changes:** deliveryCost and deliveryCostForSeller can be associated with specific order entries.

**Opportunity:** Detect SKUs with delivery‑cost pressure (low‑margin after fee).

**Example:**
- SKU X has good margin before fees, but net margin becomes negative after delivery cost.
- You can flag SKU X for pricing or shipping policy changes.

## 4) Warehouse / pickup‑point visibility

**What changes:** pointofservices data provides warehouse addresses and geo.

**Opportunity:** Identify slow warehouses, logistics bottlenecks, or routing issues.

**Example:**
- Warehouse PP3 has +2.4 days delay vs PP1.
- You can prioritize PP3 orders or reroute where feasible.

## 5) SKU mapping fallback (merchantProduct)

**What changes:** Use `merchantProduct.code/name` when offer_name or артикуl mapping fails.

**Opportunity:** Reduce missing COGS/profit lines.

**Example:**
- Today a line shows net revenue but 0 COGS.
- After fallback mapping, SKU_key is recovered and cost attaches correctly.

## 6) Partial cancel / underweight handling

**What changes:** `orderPartialCancel` allows partial quantity/weight adjustments.

**Opportunity:** Correct inventory + cashflow for measurable or shorted items.

**Example:**
- Measurable item delivered at lower weight.
- Partial cancel updates the remaining weight so net revenue and COGS align.

## 7) Customer metadata consistency

**What changes:** `customer.id` and `customer.name` captured in addition to phone.

**Opportunity:** Better CRM merge and identity resolution across channels.

## 8) Safer phased rollout

**What changes:** New endpoints can be read‑only first, with enrichment gated by flags.

**Opportunity:** Improve data quality without destabilizing existing pipelines.

