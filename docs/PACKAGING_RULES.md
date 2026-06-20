# Packaging Rules for Kaspi Orders

## Overview

This document defines the rules for packaging Kaspi orders, including heavy item handling and package counting ("Количество мест").

## Package Counting Rules

### Basic Principle

Each package ("место") is a separate physical shipment that the courier handles. The number of packages affects:
- Courier fees
- Waybill generation
- Customer expectations

### Order Categories

#### 1. NORMAL (Single-Item Orders)

**Definition:** Order with 1 line item, quantity = 1

**Package Count:**
- NOT heavy item → **1 package**
- Heavy item → **1 package**

#### 2. MULTI_QTY (Multiple Quantity Orders)

**Definition:** Order with 1 line item, quantity > 1

**Package Count:**
| Condition | Packages |
|-----------|----------|
| qty ≤ 3, no heavy items | 1 |
| qty > 3 | qty |
| Any heavy item present | qty |

**Examples:**
- 2x T-shirt (light) → 1 package
- 4x T-shirt (light) → 4 packages
- 2x Heavy item → 2 packages

#### 3. MULTI_LINE (Multiple Line Items)

**Definition:** Order with 2+ different products

**Package Count:**
| Condition | Packages |
|-----------|----------|
| total_qty ≤ 3, no heavy | 1 |
| Heavy items present | heavy_count + (1 if light items exist) |
| total_qty > 3, all light | total_qty |

**Examples:**
- T-shirt + Shorts (both light) → 1 package
- T-shirt + Heavy item → 2 packages (1 for heavy, 1 for light)
- 2x Heavy + 1x Light → 3 packages

## Heavy Items

### What Makes an Item Heavy?

Items are considered "heavy" if they:
- Weigh > 2 kg
- Are bulky (equipment, large boxes)
- Cannot be combined with other items

### Heavy Items List

Heavy items are configured in `config/heavy_items.yaml`:

```yaml
heavy_skus:
  - "HEAVY_SKU_001"  # Example: Gym equipment
  - "HEAVY_SKU_002"  # Example: Large box set
```

**To add a heavy item:**
1. Find the SKU/Article code in the CRM
2. Add to `config/heavy_items.yaml`
3. Changes take effect on next waybill build

### Current Heavy Items

Refer to `config/heavy_items.yaml` for the current list.

## Waybill PDF Naming

PDFs are named with package information:

```
{Kaspi_name_core}_{Size}-{Qty}[_additional].pdf
```

**Multi-line orders show all items:**
```
Местовая-1_{Item1}_Size-Qty(1-2)_{Item2}_Size-Qty(2-2).pdf
```

## Package Labels

Each package should be labeled with:
1. Order number (№ заказа)
2. Package X of Y (e.g., "1 из 2")
3. Customer name (from waybill)
4. Delivery address

## Quality Checks

Before courier handover:
1. ✓ Package count matches waybill
2. ✓ All items present
3. ✓ Heavy items packaged separately
4. ✓ Labels visible and correct
5. ✓ Fragile items marked if needed

## Special Handling

### Signature Required

Orders with "Требуется подписание = Да":
- Customer must sign on delivery
- Cannot leave with neighbor/concierge
- Courier must verify ID

### Same-Day Orders

Orders received at or before the 17:00 cutoff:
- Prioritize for immediate packing
- Mark as "СРОЧНО" if close to deadline

## Troubleshooting

### Wrong Package Count on Waybill

1. Check if heavy items are in `heavy_items.yaml`
2. Verify order quantity in CRM
3. Re-run waybill builder if needed

### Missing Items in Package

1. Check `missing_orders.csv` in Today folder
2. Verify SKU exists in waybill ZIP
3. Contact Kaspi support if waybill missing

### Heavy Item Not Detected

1. Add SKU to `config/heavy_items.yaml`
2. Re-run waybill builder
3. Manually adjust package count if urgent
