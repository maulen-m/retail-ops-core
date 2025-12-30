# PO Making Logic v2.0
## Python Implementation Spec for Purchase Order Generation
**Version:** 2.0  
**Purpose:** Deterministic PO generation logic for CRM/Python system  
**Scope:** Kaspi/WB clothing SKUs with size variants

---

## 1. Objective

Generate accurate PO quantities at **size level** that:
1. Prevent stockouts across all sizes
2. Maintain target Days of Cover (DoC)
3. Respect capital efficiency (ROIC gates)

---

## 2. Data Inputs Required

### 2.1 Per SKU Ã— Size (from DB)

| Field | Type | Source |
|-------|------|--------|
| `sku_key` | str | Dim_SKU |
| `my_size` | str | Size dimension |
| `current_stock` | int | Stock snapshot |
| `inbound_qty` | int | Fact_PO_Lines WHERE status = 'IN_TRANSIT' |
| `d_size` | float | Daily demand for this size |
| `cogs_unit` | float | Dim_SKU |
| `unit_profit` | float | Calculated |

### 2.2 Parameters (from Dim_Params / Dim_Params_PT)

| Param | Default | Description |
|-------|---------|-------------|
| `L` | 21 | Lead time (days) |
| `R` | 10 | Review period (days) |
| `B` | 14 | Buffer floor (days) |
| `z` | 1.65 | Service level factor (~95%) |
| `TV` | 0.23 | Size mix volatility |

---

## 3. Demand Calculation

### 3.1 SKU-Level Daily Demand

```python
def calc_d_sku(sales_90d: list[int], stock_history: list[int]) -> float:
    """
    Calculate daily demand with basic OOS filtering.
    
    Args:
        sales_90d: Daily sales for last 90 days
        stock_history: Stock at start of each day (parallel to sales_90d)
    
    Returns:
        D_sku: Average daily demand
    """
    good_days = []
    
    for sales, stock_start in zip(sales_90d, stock_history):
        # Exclude zero-sales days only if stock was also zero (OOS)
        if sales == 0 and stock_start == 0:
            continue
        good_days.append(sales)
    
    if len(good_days) < 30:
        # Flag as LOW_DATA, use conservative estimate
        return sum(good_days) / max(len(good_days), 1) * 0.7
    
    return sum(good_days) / len(good_days)
```

### 3.2 Size-Level Daily Demand

```python
def calc_d_size(d_sku: float, size_mix: float) -> float:
    """
    D_size = D_sku Ã— size_mix_percentage
    
    Args:
        d_sku: SKU-level daily demand
        size_mix: Size share as decimal (e.g., 0.30 for 30%)
    
    Returns:
        D_size: Daily demand for this size
    """
    return d_sku * size_mix
```

### 3.3 Size Mix Calculation

```python
def calc_size_mix(size_sales_90d: dict[str, int]) -> dict[str, float]:
    """
    Calculate size distribution from 90-day sales.
    
    Args:
        size_sales_90d: {size: total_units_sold}
    
    Returns:
        {size: mix_percentage} summing to 1.0
    """
    total = sum(size_sales_90d.values())
    if total == 0:
        # No sales data - return uniform distribution
        n_sizes = len(size_sales_90d)
        return {s: 1.0 / n_sizes for s in size_sales_90d}
    
    mix = {s: units / total for s, units in size_sales_90d.items()}
    
    # Apply guardrails
    mix = apply_mix_guardrails(mix)
    
    return mix


def apply_mix_guardrails(mix: dict[str, float]) -> dict[str, float]:
    """
    Floor at 3%, cap at 40%, renormalize.
    """
    MIN_MIX = 0.03
    MAX_MIX = 0.40
    
    # Apply bounds
    adjusted = {}
    for size, pct in mix.items():
        adjusted[size] = max(MIN_MIX, min(MAX_MIX, pct))
    
    # Renormalize to sum to 1.0
    total = sum(adjusted.values())
    return {s: p / total for s, p in adjusted.items()}
```

---

## 4. Volatility (Ïƒ)

Simple, static approximation. No EWMA complexity.

```python
def calc_sigma(d_sku: float) -> float:
    """
    Ïƒ = D Ã— 0.4 (conservative approximation)
    
    Sufficient for clothing retail with weekly review cycle.
    """
    return d_sku * 0.4
```

---

## 5. Safety Stock (Size-Level)

### 5.1 Components

```python
import math

def calc_safety_stock(d_size: float, sigma_size: float, params: dict) -> dict:
    """
    Calculate safety stock components for a single size.
    
    Args:
        d_size: Daily demand for this size
        sigma_size: Volatility for this size (Ïƒ_sku Ã— size_mix)
        params: {L, B, z, TV}
    
    Returns:
        {ss_demand, ss_floor, ss_mix, ss_total}
    """
    L = params['L']
    B = params['B']
    z = params['z']
    TV = params['TV']
    
    ss_demand = z * sigma_size * math.sqrt(L)  # Demand uncertainty
    ss_floor = d_size * B                       # Minimum buffer
    ss_mix = TV * d_size * L                    # Size mix uncertainty
    ss_total = ss_demand + ss_floor + ss_mix
    
    return {
        'ss_demand': ss_demand,
        'ss_floor': ss_floor,
        'ss_mix': ss_mix,
        'ss_total': ss_total
    }
```

### 5.2 Size-Level Ïƒ

```python
def calc_sigma_size(sigma_sku: float, size_mix: float) -> float:
    """
    Distribute SKU volatility to size level.
    """
    return sigma_sku * size_mix
```

---

## 6. Reorder Point & Target (Size-Level)

```python
def calc_rop_size(d_size: float, ss_total: float, L: int) -> float:
    """
    ROP_size = D_size Ã— L + SS_total_size
    
    When stock_size drops below this, trigger reorder.
    """
    return d_size * L + ss_total


def calc_t_post(ss_total: float, d_size: float, R: int) -> float:
    """
    T_post = R + (SS_total / D_size)
    
    Target days of cover after PO arrival.
    """
    if d_size <= 0:
        return R  # Fallback for zero-demand sizes
    return R + (ss_total / d_size)
```

---

## 7. Status Flag (Size-Level)

**Critical change from V1:** Status is evaluated per SIZE, not per SKU.

```python
def calc_status_size(
    current_stock: int,
    inbound_qty: int,
    rop_size: float
) -> str:
    """
    Determine reorder status for a single size.
    
    Logic (check Total first, then Current):
    1. If Total < ROP â†’ REORDER (nothing covers the gap)
    2. If Current < ROP but Total â‰¥ ROP â†’ WAIT (inbound covers)
    3. Else â†’ OK
    
    Args:
        current_stock: Units on hand for this size
        inbound_qty: Units in transit for this size
        rop_size: Reorder point for this size
    
    Returns:
        Status string: "REORDER", "WAIT", or "OK"
    """
    total_stock = current_stock + inbound_qty
    
    if total_stock < rop_size:
        return "REORDER"
    elif current_stock < rop_size:
        return "WAIT"
    else:
        return "OK"
```

---

## 8. Size Allocation (Equal Days of Cover)

### 8.1 Core Principle

After PO arrives, all sizes should have **â‰ˆ T_post days of cover**. This naturally allocates more units to high-demand sizes.

### 8.2 Allocation Formula

```python
def calc_order_qty_size(
    d_size: float,
    current_stock: int,
    inbound_qty: int,
    t_post: float,
    days_until_arrival: int
) -> int:
    """
    Calculate order quantity for a single size using Equal DoC.
    
    Args:
        d_size: Daily demand for this size
        current_stock: Units on hand
        inbound_qty: Units already in transit
        t_post: Target days of cover
        days_until_arrival: Days until this PO arrives
    
    Returns:
        Units to order for this size (integer, â‰¥ 0)
    """
    # Project stock at arrival (consume during lead time)
    consumption_until_arrival = d_size * days_until_arrival
    pre_arrival_stock = current_stock + inbound_qty - consumption_until_arrival
    pre_arrival_stock = max(0, pre_arrival_stock)  # Can't go negative
    
    # Target stock at arrival
    target_stock = t_post * d_size
    
    # Order the gap
    order_qty = target_stock - pre_arrival_stock
    
    return max(0, int(order_qty))
```

### 8.3 Full SKU Allocation

```python
def allocate_sku(
    sku_key: str,
    sizes: list[str],
    size_data: dict,  # {size: {d_size, current_stock, inbound_qty, ss_total, ...}}
    params: dict,
    days_until_arrival: int
) -> dict[str, int]:
    """
    Generate allocation for all sizes of a SKU.
    
    Returns:
        {size: order_qty}
    """
    allocation = {}
    
    for size in sizes:
        data = size_data[size]
        
        t_post = calc_t_post(data['ss_total'], data['d_size'], params['R'])
        
        order_qty = calc_order_qty_size(
            d_size=data['d_size'],
            current_stock=data['current_stock'],
            inbound_qty=data['inbound_qty'],
            t_post=t_post,
            days_until_arrival=days_until_arrival
        )
        
        allocation[size] = order_qty
    
    return allocation
```

### 8.4 Example Calculation

| Size | Mix | D_size | Current | Inbound | T_post | Target | Pre | Order |
|------|-----|--------|---------|---------|--------|--------|-----|-------|
| S | 6% | 0.6 | 5 | 0 | 30 | 18 | 5 | **13** |
| M | 10% | 1.0 | 10 | 0 | 30 | 30 | 10 | **20** |
| L | 24% | 2.4 | 30 | 0 | 30 | 72 | 30 | **42** |
| XL | 30% | 3.0 | 80 | 0 | 30 | 90 | 80 | **10** |
| 2XL | 20% | 2.0 | 10 | 20 | 30 | 60 | 30 | **30** |
| 3XL | 10% | 1.0 | 25 | 0 | 30 | 30 | 25 | **5** |

Note: XL orders only 10 units because current stock is already near target. This is correct behaviorâ€”don't over-order sizes that are well-stocked.

---

## 9. PO Trigger Logic

### 9.1 When to Generate PO

```python
def should_generate_po(size_statuses: dict[str, str]) -> bool:
    """
    Trigger PO if ANY size has status = REORDER.
    
    Args:
        size_statuses: {size: status}
    
    Returns:
        True if PO should be generated
    """
    return any(status == "REORDER" for status in size_statuses.values())
```

### 9.2 SKU-Level Suggested Order

```python
def calc_suggested_order_sku(allocation: dict[str, int]) -> int:
    """
    Sum of all size allocations.
    """
    return sum(allocation.values())
```

---

## 10. ROIC Gate

Before confirming PO, validate capital efficiency.

```python
def calc_roic(
    unit_profit: float,
    d_sku: float,
    cogs_unit: float,
    ss_total_sku: float,
    L: int,
    R: int
) -> float:
    """
    Monthly ROIC for the SKU.
    
    Returns:
        ROIC as decimal (e.g., 0.25 for 25%)
    """
    # Average capital tied up
    k_avg = d_sku * (L + R / 2) * cogs_unit + ss_total_sku * cogs_unit
    
    if k_avg <= 0:
        return 0.0
    
    # Monthly profit
    monthly_profit = unit_profit * d_sku * 30
    
    return monthly_profit / k_avg


def roic_gate(roic: float, order_qty: int) -> dict:
    """
    Apply ROIC thresholds to order decision.
    
    Returns:
        {approved: bool, action: str, adjusted_qty: int}
    """
    if roic >= 0.20:
        return {'approved': True, 'action': 'ORDER_FULL', 'adjusted_qty': order_qty}
    elif roic >= 0.10:
        return {'approved': True, 'action': 'ORDER_WITH_FLAG', 'adjusted_qty': order_qty}
    else:
        return {'approved': False, 'action': 'REVIEW_REQUIRED', 'adjusted_qty': 0}
```

---

## 11. Edge Cases

### 11.1 New SKU (< 90 days history)

```python
def is_new_sku(days_of_history: int) -> bool:
    return days_of_history < 90


def adjust_for_new_sku(order_qty: int, days_of_history: int) -> int:
    """
    Apply conservative multiplier for new SKUs.
    """
    if days_of_history < 30:
        return int(order_qty * 0.5)  # Very new, be cautious
    elif days_of_history < 60:
        return int(order_qty * 0.7)
    elif days_of_history < 90:
        return int(order_qty * 0.85)
    return order_qty
```

### 11.2 Very Low Demand (D_size < 0.1/day)

```python
def handle_low_demand_size(d_size: float, size_mix: float, order_qty: int) -> int:
    """
    Ensure minimum viable order for slow sizes.
    """
    if d_size < 0.1 and size_mix >= 0.05:
        return max(1, order_qty)  # At least 1 unit if mix > 5%
    return order_qty
```

### 11.3 Size Discontinuation Detection

```python
def should_discontinue_size(
    sales_90d: int,
    current_stock: int,
    days_with_stock: int
) -> bool:
    """
    Flag size for discontinuation if:
    - Zero sales in 90 days
    - Had stock for 60+ of those days
    """
    return sales_90d == 0 and days_with_stock >= 60 and current_stock > 0
```

---

## 12. Complete PO Generation Flow

```python
def generate_po(
    sku_key: str,
    sizes: list[str],
    size_data: dict,
    params: dict,
    days_until_arrival: int = None
) -> dict:
    """
    Main entry point for PO generation.
    
    Args:
        sku_key: SKU identifier
        sizes: List of size codes
        size_data: {size: {d_size, current_stock, inbound_qty, cogs_unit, ...}}
        params: {L, R, B, z, TV}
        days_until_arrival: Override for lead time (default: params['L'])
    
    Returns:
        {
            sku_key: str,
            should_order: bool,
            allocation: {size: qty},
            total_qty: int,
            total_cost: float,
            roic: float,
            size_statuses: {size: status}
        }
    """
    if days_until_arrival is None:
        days_until_arrival = params['L']
    
    # Step 1: Calculate status for each size
    size_statuses = {}
    for size in sizes:
        data = size_data[size]
        rop = calc_rop_size(data['d_size'], data['ss_total'], params['L'])
        status = calc_status_size(
            data['current_stock'],
            data['inbound_qty'],
            rop
        )
        size_statuses[size] = status
    
    # Step 2: Check if PO needed
    should_order = should_generate_po(size_statuses)
    
    if not should_order:
        return {
            'sku_key': sku_key,
            'should_order': False,
            'allocation': {s: 0 for s in sizes},
            'total_qty': 0,
            'total_cost': 0,
            'roic': None,
            'size_statuses': size_statuses
        }
    
    # Step 3: Calculate allocation
    allocation = allocate_sku(
        sku_key, sizes, size_data, params, days_until_arrival
    )
    
    # Step 4: Apply edge case adjustments
    for size in sizes:
        data = size_data[size]
        allocation[size] = handle_low_demand_size(
            data['d_size'],
            data.get('size_mix', 0.1),
            allocation[size]
        )
    
    # Step 5: Calculate totals
    total_qty = sum(allocation.values())
    cogs_unit = size_data[sizes[0]]['cogs_unit']  # Same for all sizes
    total_cost = total_qty * cogs_unit
    
    # Step 6: ROIC check
    d_sku = sum(size_data[s]['d_size'] for s in sizes)
    ss_total_sku = sum(size_data[s]['ss_total'] for s in sizes)
    unit_profit = size_data[sizes[0]].get('unit_profit', 0)
    
    roic = calc_roic(unit_profit, d_sku, cogs_unit, ss_total_sku, params['L'], params['R'])
    
    return {
        'sku_key': sku_key,
        'should_order': True,
        'allocation': allocation,
        'total_qty': total_qty,
        'total_cost': total_cost,
        'roic': roic,
        'size_statuses': size_statuses
    }
```

---

## 13. Prep Days & Effective Lead Time

### 13.1 Prep Days by Product Type

**Key principle:** Each supplier can only ship once ALL their items are prepared. Prep time is calculated per supplier batch, not per individual SKU.

| Product_Type | Prep Days Calculation | Rationale |
|--------------|----------------------|-----------|
| `CL` (Clothes) | `ceil(1.3 × Total_CL_Weight_kg / 100)` | Shared across all CL items in PO |
| `ELS` (Electronics) | **1 day (constant)** | Minimal prep for electronics |
| `FUR` (Furniture) | TBD | Not active |

**Total_Prep_Clothes formula:**
```python
def calc_prep_days_clothes(approved_cl_items: list) -> int:
    """
    Calculate shared prep days for all approved CL items.

    Args:
        approved_cl_items: List of CL SKUs with order_qty > 0

    Returns:
        prep_days: Shared prep time for entire CL batch
    """
    total_weight_kg = sum(item['po_weight_kg'] for item in approved_cl_items)
    if total_weight_kg == 0:
        return 0
    return math.ceil(1.3 * total_weight_kg / 100)
```

### 13.2 Prep Models

Two models exist for prep days calculation:

| Model | Name | Formula | Use Case |
|-------|------|---------|----------|
| **Model B** | Worst-Case | `prep_days = ceil(1.3 × weight / 100)` (uncapped) | Planning with high prep uncertainty |
| **Model C** | Capacity-Capped | `prep_days = min(ceil(1.3 × weight / 100), R)` | Default; assumes prep ≤ review cycle |

**Default:** Model C (capacity-capped at R=10 days)

### 13.3 Effective Lead Time (Effective_L)

**Effective_L** is the total time from PO creation until items arrive in warehouse.

```
Effective_L = L + prep_days
```

Where:
- `L` = Transit lead time (21 days for China → Astana)
- `prep_days` = Supplier prep time (shared per Product_Type)

**By Product_Type:**
```
CL items:  Effective_L = L + Total_Prep_Clothes
ELS items: Effective_L = L + 1
```

**Code implementation:**
```python
# Calculate effective_L per SKU (using shared prep values)
if sku_key.startswith('CL_'):
    effective_L = L + shared_clothes_prep
elif sku_key.startswith('ELS_'):
    effective_L = L + 1  # ELS always 1 day prep
else:
    effective_L = L + 3  # fallback
```

### 13.4 Impact on PO Calculations

All downstream metrics must use `effective_L`:

| Metric | Formula with Effective_L |
|--------|--------------------------|
| `consumption_until_arrival` | `d_size × effective_L` |
| `pre_arrival_stock` | `current + inbound - consumption_until_arrival` |
| `po_send_date` | `po_message_date + prep_days` |
| `est_arrival_date` | `po_send_date + L` |
| `days_until_arrival` | `prep_days + L = effective_L` |

---

## 14. Multi-PO Interdependence

### 14.1 Core Principle

PO-N must account for approved orders from all previous POs (PO-1 through PO-(N-1)) as inbound inventory.

```
PO-N.inbound_qty = sum(approved_orders from PO-1 to PO-(N-1))
```

### 14.2 Cascade Logic

When calculating PO-N:

1. **Read approvals** from PO-(N-1), PO-(N-2), ..., PO-1
2. **Add to inbound** for each size:
   ```python
   inbound_qty = existing_inbound + sum(
       prior_po.size_orders[size]
       for prior_po in approved_prior_pos
   )
   ```
3. **Calculate need** using updated inbound
4. **Generate orders** for PO-N based on gap

### 14.3 Date Offset

Each PO is offset by R days from the previous:

| PO | Message Date | Offset from PO-4 |
|----|--------------|------------------|
| PO-4 | T₀ | 0 |
| PO-5 | T₀ + R | +10 days |
| PO-6 | T₀ + 2R | +20 days |
| PO-7 | T₀ + 3R | +30 days |

### 14.4 Implementation Notes

```python
def generate_multi_po_data(base_po: dict, num_pos: int = 7) -> dict:
    """
    Generate PO-4 through PO-10 with interdependence.

    For each PO-N where N > 4:
    1. Get approved items from PO-(N-1)
    2. Add their order quantities to inbound
    3. Recalculate need and orders
    4. Apply same prep_days (shared per supplier type)
    """
    # PO-4 is base, calculated independently
    # PO-5+ read from previous PO's approved orders
```

---

## 15. Parameter Reference

| Param | Value | Formula Usage |
|-------|-------|---------------|
| L | 21 | Lead time in ROP, SS_mix |
| R | 10 | Review period in T_post |
| B | 14 | Buffer floor in SS_floor |
| z | 1.65 | Service level in SS_demand |
| TV | 0.23 | Mix volatility in SS_mix |

---

## 16. Formula Quick Reference

```
# Demand
D_sku = avg(good_days_sales)         # 90d, exclude OOS zeros
D_size = D_sku Ã— size_mix
Ïƒ = D_sku Ã— 0.4

# Safety Stock (per size)
SS_demand = z Ã— Ïƒ_size Ã— âˆšL
SS_floor = D_size Ã— B
SS_mix = TV Ã— D_size Ã— L
SS_total = SS_demand + SS_floor + SS_mix

# Reorder Point (per size)
ROP_size = D_size Ã— L + SS_total_size

# Target Coverage
T_post = R + SS_total / D_size

# Allocation (Equal DoC)
Pre_size = Current + Inbound - (D_size Ã— days_to_arrival)
Target_size = T_post Ã— D_size
Order_size = max(0, Target_size - Pre_size)

# Status (per size)
Status = Total_size < ROP_size ? "REORDER" : (Current < ROP_size ? "WAIT" : "OK")

# ROIC
K_avg = D_sku Ã— (L + R/2) Ã— COGS + SS_total_sku Ã— COGS
Monthly_ROIC = (Unit_profit Ã— D_sku Ã— 30) / K_avg
```

---

## 17. Validation Checklist

Before deploying:

- [ ] D_size sums to D_sku across all sizes
- [ ] Size mix sums to 1.0 (100%)
- [ ] No size gets 0 allocation if mix > 5% and status = REORDER
- [ ] Total_qty = sum of all size allocations
- [ ] ROIC calculation matches Excel ABC_View within Â±2%
- [ ] Status flags match Excel for test SKUs

---

*This document is the authoritative spec for PO generation logic. Python implementation must match these formulas exactly.*