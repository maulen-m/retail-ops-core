# Agent Opus Execution Plan: PO Dashboard Webapp

**Version:** 1.0  
**Created:** 2025-12-14  
**Purpose:** Step-by-step instructions for building a PO recommendation webapp  
**Target:** React artifact displaying size-level PO suggestions with ROIC ≥ 15%

---

## Prerequisites

**Repo Location:** `~/Docs/Autonomous_business/`

**Key Files:**
| File | Path | Purpose |
|------|------|---------|
| Database | `db/app.db` | SQLite with sales, inventory, SKU data |
| Size Allocation | `core/calc/size_allocation.py` | PO generation engine |
| PO Generator | `core/automation/po_generator.py` | `generate_po_draft_size_aware()` |
| Inventory Params | `core/config/inventory_params.py` | L=21, R=10, z=1.65, etc. |
| Queries | `core/db/queries.py` | Data retrieval functions |

**Critical Constraint:** Exclude `order_date = '2025-12-14'` (today, incomplete data)

---

## Phase 1: Data Verification

### 1.1 Check Sales Data Freshness

```bash
cd ~/Docs/Autonomous_business
sqlite3 db/app.db "
SELECT 
    MIN(order_date) as earliest,
    MAX(order_date) as latest,
    COUNT(*) as total_rows,
    COUNT(DISTINCT sku_key) as unique_skus
FROM fact_sales
WHERE order_date < '2025-12-14';
"
```

**Expected:**
- `latest` = `2025-12-13`
- If `latest < 2025-12-12` → Data stale, flag in report

### 1.2 Find Date Gaps (Last 60 Days)

```bash
sqlite3 db/app.db "
WITH RECURSIVE dates AS (
    SELECT date('now', '-60 days') as dt
    UNION ALL
    SELECT date(dt, '+1 day') FROM dates WHERE dt < date('now', '-1 day')
)
SELECT dt as missing_date
FROM dates
WHERE dt NOT IN (SELECT DISTINCT order_date FROM fact_sales)
ORDER BY dt;
"
```

**Action:**
- If > 3 gaps → Add `Notes: "DATA GAP: [dates]"` to affected SKUs
- If 0 gaps → Proceed

### 1.3 Check SKU Cost Data Completeness

```bash
sqlite3 db/app.db "
SELECT 
    sku_key,
    base_cost_cny,
    weight_kg,
    product_type
FROM dim_sku
WHERE base_cost_cny IS NULL 
   OR weight_kg IS NULL
   OR product_type IS NULL;
"
```

**Action:**
- SKUs with NULL fields → `Notes: "INPUTS NEEDED: [field1, field2]"`
- These SKUs cannot have ROIC calculated

### 1.4 Verification Checkpoint

Before proceeding, report:
- [ ] Total sales rows (excluding Dec 14)
- [ ] Date range (min → max)
- [ ] Count of SKUs with complete cost data
- [ ] Count of SKUs with incomplete data
- [ ] List of date gaps (if any)

---

## Phase 2: Script Discovery & Validation

### 2.1 Existing Functions to Use

| Function | Location | Purpose |
|----------|----------|---------|
| `generate_po_draft()` | `core/calc/size_allocation.py` | Main PO engine |
| `calc_roic()` | `core/calc/size_allocation.py` | ROIC calculation |
| `calc_rop_for_size()` | `core/calc/size_allocation.py` | Size-level ROP |
| `calc_status_for_size()` | `core/calc/size_allocation.py` | REORDER/WAIT/OK |
| `get_size_sales_history()` | `core/db/queries.py` | Historical sales |
| `get_size_current_stock()` | `core/db/queries.py` | Current inventory |
| `get_size_inbound()` | `core/db/queries.py` | In-transit stock |
| `get_params()` | `core/config/inventory_params.py` | L, R, B, z, TV |

### 2.2 Functions to Implement (New)

These do NOT exist in codebase — implement in the data generation script:

```python
# 1. PrepDays Calculation
def calc_prep_days(po_weight_kg: float, product_type: str) -> int:
    """
    Clothes: CEILING(1.3 × (PO_weight_kg / 100), 1)
    Electronics: 1
    """
    if product_type in ('ELS', 'ELEC', 'Electronics'):
        return 1
    return max(1, ceil(1.3 * po_weight_kg / 100))


# 2. PO Date Calculations
def calc_po_dates(
    needed_by: date, 
    prep_days: int, 
    L: int = 21
) -> tuple[date, date, date]:
    """
    Returns: (needed_by, po_send_date, po_message_date)
    
    PO_Send_Date = Needed_By - L
    PO_Message_Date = PO_Send_Date - PrepDays
    """
    po_send_date = needed_by - timedelta(days=L)
    po_message_date = po_send_date - timedelta(days=prep_days)
    return needed_by, po_send_date, po_message_date


# 3. Priority Flag
def calc_priority_flag(po_send_date: date) -> bool:
    """
    TRUE if PO_Send_Date <= 2025-12-31 (holiday deadline)
    """
    return po_send_date <= date(2025, 12, 31)


# 4. Needed-By Date
def calc_needed_by_date(
    current_stock: int, 
    d_sku: float, 
    today: date = None
) -> date:
    """
    When will we run out?
    Needed_By = today + (current_stock / d_sku)
    """
    if today is None:
        today = date.today()
    
    if d_sku <= 0:
        return today + timedelta(days=365)  # No demand = not urgent
    
    days_of_cover = current_stock / d_sku
    return today + timedelta(days=int(days_of_cover))


# 5. Deficit Calculation (for display)
def calc_deficit_size(
    rop_size: float, 
    stock_size: int, 
    inbound_size: int
) -> int:
    """
    Deficit = ROP - (Stock + Inbound)
    Shows gap to safety threshold (different from order_qty)
    """
    return max(0, int(rop_size - stock_size - inbound_size))
```

### 2.3 Key Formula Clarification

**Deficit vs Order Quantity:**

| Metric | Formula | Purpose |
|--------|---------|---------|
| `deficit_size` | `ROP - (stock + inbound)` | Display: gap to safety threshold |
| `order_qty` | `max(0, Target - Pre_arrival)` | Action: what to actually order |

Where:
- `Target = T_post × D_size`
- `T_post = R + SS/D`
- `Pre_arrival = current + inbound - (D × days_to_arrival)`

These values can differ — deficit shows urgency, order_qty shows action.

---

## Phase 3: PO Calculation Logic

### 3.1 Core Formulas (from existing code)

```python
# Parameters (from inventory_params.py)
L = 21    # Lead time (days)
R = 10    # Review period (days)
B = 14    # Buffer floor (days)
z = 1.65  # Service level (95%)
TV = 0.23 # Mix variability

# Demand
D_sku = sum(good_days_sales) / good_days_count  # OOS-filtered
D_size = D_sku × size_mix
σ = D_sku × 0.4

# Safety Stock (per size)
SS_demand = z × σ_size × √L
SS_floor = D_size × B
SS_mix = TV × D_size × L
SS_total = SS_demand + SS_floor + SS_mix

# Reorder Point (per size)
ROP_size = D_size × L + SS_total

# Target (for ordering)
T_post = R + (SS_total / D_size)
Target = T_post × D_size

# Order Quantity
Pre_arrival = current + inbound - (D_size × L)
Order_qty = max(0, Target - Pre_arrival)

# ROIC
K_avg = D_sku × (L + R/2) × COGS + SS_total × COGS
Monthly_ROIC = (Unit_profit × D_sku × 30) / K_avg
```

### 3.2 ROIC Filter

```python
ROIC_THRESHOLD = 0.15  # 15%

# In main loop:
if draft.roic_monthly < ROIC_THRESHOLD:
    continue  # Exclude from output
```

### 3.3 Edge Case Rules

| Condition | Detection | Action |
|-----------|-----------|--------|
| No sales data | `d_sku = 0` or `last_sale_date = NULL` | `Notes: "NO SALES DATA"`, exclude |
| Missing weight | `weight_kg IS NULL` | `Notes: "INPUTS NEEDED: weight_kg"` |
| Missing cost | `base_cost_cny IS NULL` | `Notes: "INPUTS NEEDED: base_cost_cny"`, skip ROIC |
| Missing product_type | `product_type IS NULL` | `Notes: "INPUTS NEEDED: product_type"`, use PrepDays=1 |
| ROIC < 15% | `roic_monthly < 0.15` | Exclude entirely |
| Today's sales | `order_date = '2025-12-14'` | Filter out in all queries |

---

## Phase 4: Data Generation Script

### 4.1 Create Script

**File:** `scripts/generate_po_dashboard_data.py`

```python
#!/usr/bin/env python3
"""
Generate PO dashboard data for webapp.
Outputs JSON with SKU-level and size-level PO recommendations.
"""

import sqlite3
import json
from datetime import date, timedelta
from pathlib import Path
from math import ceil
from dataclasses import dataclass, asdict
from typing import Optional
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.calc.size_allocation import (
    generate_po_draft,
    PODraft,
    ROICAction,
    OrderStatus
)
from core.db.queries import (
    get_size_sales_history,
    get_size_current_stock,
    get_size_inbound,
    get_size_sales_90d,
    get_sku_age_days
)
from core.config.inventory_params import get_params

# Constants
DB_PATH = PROJECT_ROOT / "db" / "app.db"
OUTPUT_PATH = PROJECT_ROOT / "exports" / "po_dashboard_data.json"
ROIC_THRESHOLD = 0.15
HOLIDAY_DEADLINE = date(2025, 12, 31)
TODAY = date(2025, 12, 14)
DATA_CUTOFF = "2025-12-13"  # Exclude today (incomplete)


@dataclass
class SizePOLine:
    """Size-level PO recommendation."""
    sku_key: str
    sku_id: str
    size: str
    stock: int
    inbound: int
    rop_size: float
    deficit_size: int
    order_qty: int
    weight_kg: float
    prep_days: int
    needed_by_date: str
    po_send_date: str
    po_message_date: str
    priority_flag: bool
    roic_pct: float
    notes: str


@dataclass
class SkuPOLine:
    """SKU-level PO summary."""
    sku_key: str
    stock: int
    inbound: int
    rop_total: float
    deficit_total: int
    po_qty_total: int
    po_weight_kg: float
    prep_days: int
    needed_by_date: str
    po_send_date: str
    po_message_date: str
    priority_flag: bool
    roic_pct: float
    notes: str


def calc_prep_days(po_weight_kg: float, product_type: str) -> int:
    """Clothes: CEILING(1.3 × (weight_kg / 100), 1). Electronics: 1."""
    if product_type in ('ELS', 'ELEC', 'Electronics'):
        return 1
    return max(1, ceil(1.3 * po_weight_kg / 100))


def calc_needed_by_date(current_stock: int, d_sku: float) -> date:
    """When will we run out?"""
    if d_sku <= 0:
        return TODAY + timedelta(days=365)
    days_of_cover = current_stock / d_sku
    return TODAY + timedelta(days=int(days_of_cover))


def calc_po_dates(needed_by: date, prep_days: int, L: int = 21):
    """Calculate PO send and message dates."""
    po_send_date = needed_by - timedelta(days=L)
    po_message_date = po_send_date - timedelta(days=prep_days)
    return po_send_date, po_message_date


def get_all_active_skus(conn) -> list[dict]:
    """Get all active SKUs with their attributes."""
    cursor = conn.execute("""
        SELECT 
            sku_key,
            base_cost_cny,
            weight_kg,
            product_type
        FROM dim_sku
        WHERE active_flag = 1
    """)
    return [dict(row) for row in cursor.fetchall()]


def check_sku_inputs(sku: dict) -> list[str]:
    """Check for missing required inputs."""
    missing = []
    if sku['base_cost_cny'] is None:
        missing.append('base_cost_cny')
    if sku['weight_kg'] is None:
        missing.append('weight_kg')
    if sku['product_type'] is None:
        missing.append('product_type')
    return missing


def generate_po_data() -> dict:
    """Main function to generate PO dashboard data."""
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    params = get_params()
    
    # Get all active SKUs
    skus = get_all_active_skus(conn)
    
    sku_lines = []
    size_lines = []
    
    for sku in skus:
        sku_key = sku['sku_key']
        
        # Check for missing inputs
        missing = check_sku_inputs(sku)
        if 'base_cost_cny' in missing:
            # Can't calculate ROIC without cost
            continue
        
        notes_list = []
        if missing:
            notes_list.append(f"INPUTS NEEDED: {', '.join(missing)}")
        
        # Get size-level data
        size_sales_90d = get_size_sales_90d(sku_key, "UNIVERSAL", DB_PATH)
        if not size_sales_90d:
            continue  # No sales data
        
        size_current = get_size_current_stock(sku_key, "UNIVERSAL", DB_PATH)
        size_inbound = get_size_inbound(sku_key, "UNIVERSAL", DB_PATH)
        size_sales_hist = get_size_sales_history(sku_key, "UNIVERSAL", 90, DB_PATH)
        size_stock_hist = {}  # Simplified: assume stock history not tracked
        
        # Get SKU cost/profit
        base_cost_cny = sku['base_cost_cny'] or 50
        weight_kg = sku['weight_kg'] or 0.5
        product_type = sku['product_type'] or 'CL'
        
        # COGS calculation
        cny_to_kzt = 78
        shipping_per_kg = 150
        unit_cogs = base_cost_cny * cny_to_kzt + weight_kg * shipping_per_kg
        
        # Get average sell price
        price_row = conn.execute("""
            SELECT AVG(sell_price_kzt) as avg_price
            FROM fact_sales
            WHERE sku_key = ?
            AND order_date >= date('now', '-90 days')
            AND order_date <= ?
        """, (sku_key, DATA_CUTOFF)).fetchone()
        
        avg_price = price_row['avg_price'] if price_row and price_row['avg_price'] else 15000
        unit_profit = avg_price - unit_cogs
        
        # Calculate sigma
        total_daily = []
        for size, sales_list in size_sales_hist.items():
            for i, s in enumerate(sales_list):
                if i >= len(total_daily):
                    total_daily.append(0)
                total_daily[i] += s
        
        if total_daily and len(total_daily) > 1:
            import statistics
            sigma_sku = statistics.stdev(total_daily)
        else:
            sigma_sku = sum(total_daily) / max(len(total_daily), 1) * 0.4 if total_daily else 0
        
        # Get SKU age
        sku_age = get_sku_age_days(sku_key, "UNIVERSAL", DB_PATH)
        
        # Generate PO draft
        draft = generate_po_draft(
            sku_key=sku_key,
            store_code="UNIVERSAL",
            size_sales_90d=size_sales_90d,
            size_current_stock=size_current,
            size_inbound_stock=size_inbound,
            size_sales_history=size_sales_hist,
            size_stock_history=size_stock_hist,
            unit_cogs=unit_cogs,
            unit_profit=unit_profit,
            sigma_sku=sigma_sku,
            sku_age_days=sku_age
        )
        
        if not draft or not draft.should_order:
            continue
        
        # ROIC filter
        if draft.roic_monthly < ROIC_THRESHOLD:
            continue
        
        # Calculate dates
        total_stock = draft.current_stock_total
        d_sku = draft.d_sku
        needed_by = calc_needed_by_date(total_stock, d_sku)
        
        po_weight = weight_kg * draft.total_qty
        prep_days = calc_prep_days(po_weight, product_type)
        po_send, po_message = calc_po_dates(needed_by, prep_days, params.L)
        priority = po_send <= HOLIDAY_DEADLINE
        
        # SKU-level line
        sku_line = SkuPOLine(
            sku_key=sku_key,
            stock=draft.current_stock_total,
            inbound=draft.inbound_stock_total,
            rop_total=round(draft.rop_sku, 1),
            deficit_total=max(0, int(draft.rop_sku - draft.total_stock)),
            po_qty_total=draft.total_qty,
            po_weight_kg=round(po_weight, 2),
            prep_days=prep_days,
            needed_by_date=needed_by.isoformat(),
            po_send_date=po_send.isoformat(),
            po_message_date=po_message.isoformat(),
            priority_flag=priority,
            roic_pct=round(draft.roic_monthly * 100, 1),
            notes="; ".join(notes_list) if notes_list else ""
        )
        sku_lines.append(asdict(sku_line))
        
        # Size-level lines
        for size, alloc in draft.allocations.items():
            if alloc.order_qty_adjusted <= 0:
                continue
            
            size_data = None
            for s, data in draft.allocations.items():
                if s == size:
                    size_data = data
                    break
            
            size_stock = size_current.get(size, 0)
            size_inb = size_inbound.get(size, 0)
            
            # Get ROP for this size from draft
            rop_size = 0
            for s in draft.allocations:
                if s == size:
                    # Approximate from target
                    rop_size = alloc.target_stock
            
            deficit = max(0, int(rop_size - size_stock - size_inb))
            size_weight = weight_kg * alloc.order_qty_adjusted
            
            size_line = SizePOLine(
                sku_key=sku_key,
                sku_id=f"{sku_key}_{size}",
                size=size,
                stock=size_stock,
                inbound=size_inb,
                rop_size=round(rop_size, 1),
                deficit_size=deficit,
                order_qty=alloc.order_qty_adjusted,
                weight_kg=round(size_weight, 2),
                prep_days=prep_days,
                needed_by_date=needed_by.isoformat(),
                po_send_date=po_send.isoformat(),
                po_message_date=po_message.isoformat(),
                priority_flag=priority,
                roic_pct=round(draft.roic_monthly * 100, 1),
                notes=""
            )
            size_lines.append(asdict(size_line))
    
    conn.close()
    
    # Sort by PO message date (most urgent first)
    sku_lines.sort(key=lambda x: x['po_message_date'])
    size_lines.sort(key=lambda x: (x['po_message_date'], x['sku_key'], x['size']))
    
    return {
        "generated_at": TODAY.isoformat(),
        "roic_threshold": ROIC_THRESHOLD * 100,
        "holiday_deadline": HOLIDAY_DEADLINE.isoformat(),
        "summary": {
            "total_skus": len(sku_lines),
            "total_units": sum(s['po_qty_total'] for s in sku_lines),
            "priority_skus": sum(1 for s in sku_lines if s['priority_flag']),
            "total_weight_kg": round(sum(s['po_weight_kg'] for s in sku_lines), 1)
        },
        "sku_level": sku_lines,
        "size_level": size_lines
    }


if __name__ == "__main__":
    print("Generating PO dashboard data...")
    data = generate_po_data()
    
    # Ensure output directory exists
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"✓ Generated: {OUTPUT_PATH}")
    print(f"  - SKUs: {data['summary']['total_skus']}")
    print(f"  - Units: {data['summary']['total_units']}")
    print(f"  - Priority: {data['summary']['priority_skus']}")
    print(f"  - Weight: {data['summary']['total_weight_kg']} kg")
```

### 4.2 Run Data Generation

```bash
cd ~/Docs/Autonomous_business
python scripts/generate_po_dashboard_data.py
```

**Expected output:**
```
Generating PO dashboard data...
✓ Generated: exports/po_dashboard_data.json
  - SKUs: 45
  - Units: 1,250
  - Priority: 12
  - Weight: 625.5 kg
```

---

## Phase 5: Webapp Build

### 5.1 Create React Artifact

Create a React component that:
1. Embeds the generated JSON data
2. Displays two tables (SKU-level and Size-level)
3. Supports filtering and sorting
4. Highlights priority items

### 5.2 Table 1: SKU-Level Columns

| Column | Type | Description |
|--------|------|-------------|
| `sku_key` | string | SKU identifier |
| `stock` | int | Current on-hand |
| `inbound` | int | In-transit |
| `rop_total` | float | Sum of size ROPs |
| `deficit_total` | int | Gap to ROP |
| `po_qty_total` | int | Units to order |
| `po_weight_kg` | float | Total PO weight |
| `prep_days` | int | Supplier prep time |
| `needed_by_date` | date | Stockout date |
| `po_send_date` | date | Ship-by date |
| `po_message_date` | date | Contact supplier by |
| `priority_flag` | bool | ≤ Dec 31 deadline |
| `roic_pct` | float | Monthly ROIC % |
| `notes` | string | Warnings/flags |

### 5.3 Table 2: Size-Level Columns

| Column | Type | Description |
|--------|------|-------------|
| `sku_key` | string | Parent SKU |
| `sku_id` | string | `{sku_key}_{size}` |
| `size` | string | S/M/L/XL/etc. |
| `stock` | int | Size on-hand |
| `inbound` | int | Size in-transit |
| `rop_size` | float | Size ROP |
| `deficit_size` | int | Size gap to ROP |
| `order_qty` | int | Size order qty |
| `weight_kg` | float | Size PO weight |
| `prep_days` | int | (inherited) |
| `needed_by_date` | date | (inherited) |
| `po_send_date` | date | (inherited) |
| `po_message_date` | date | (inherited) |
| `priority_flag` | bool | (inherited) |
| `roic_pct` | float | (inherited) |
| `notes` | string | Size-specific |

### 5.4 Webapp Features

1. **Summary Cards:**
   - Total SKUs needing PO
   - Total units to order
   - Priority items count
   - Total weight (kg)

2. **Filters:**
   - Priority-only toggle
   - Search by sku_key

3. **Sorting:**
   - Default: `po_message_date` ASC (urgent first)
   - Clickable columns: ROIC, qty, weight

4. **Styling:**
   - Priority rows: Yellow background
   - ROIC 15-20%: Amber text
   - ROIC ≥20%: Green text
   - Notes with warnings: Red text

### 5.5 Artifact Output Location

```
/mnt/user-data/outputs/po_dashboard.jsx
```

---

## Verification Checklist

### Phase 1 Complete:
- [ ] Sales data latest = 2025-12-13
- [ ] Date gaps documented
- [ ] Missing cost data list generated

### Phase 2 Complete:
- [ ] All existing functions identified
- [ ] New functions documented

### Phase 3 Complete:
- [ ] Formula review passed
- [ ] Edge cases handled

### Phase 4 Complete:
- [ ] `generate_po_dashboard_data.py` created
- [ ] Script runs without errors
- [ ] JSON output generated

### Phase 5 Complete:
- [ ] React artifact created
- [ ] Both tables render correctly
- [ ] Filters work
- [ ] Priority highlighting works
- [ ] Sum of size qty = SKU total qty

### Final Validation:
- [ ] ROIC ≥ 15% filter applied (no SKUs below threshold)
- [ ] Dec 14 data excluded
- [ ] Deficit calculation: `ROP - (stock + inbound)`
- [ ] Order qty calculation: `Target - Pre_arrival`

---

## Quick Reference: Key Formulas

```
# Demand
D_sku = avg(sales, OOS-filtered)
D_size = D_sku × size_mix

# Safety Stock
SS = z×σ×√L + D×B + TV×D×L

# Reorder Point
ROP = D×L + SS

# Target (for ordering)
Target = T_post × D
T_post = R + SS/D

# Order Quantity
Pre_arrival = current + inbound - (D × L)
Order_qty = max(0, Target - Pre_arrival)

# Deficit (for display)
Deficit = ROP - (stock + inbound)

# ROIC
K_avg = D×(L+R/2)×COGS + SS×COGS
ROIC = (Profit×D×30) / K_avg

# Dates
Needed_By = today + (stock / D)
PO_Send = Needed_By - L
PO_Message = PO_Send - PrepDays

# PrepDays
Clothes: ceil(1.3 × weight_kg / 100)
Electronics: 1

# Priority
PO_Send ≤ 2025-12-31
```

---

## Handoff Notes

1. **Data script first** — Run Phase 4 before building webapp
2. **JSON embedding** — For simplicity, embed JSON directly in React artifact (can refactor to fetch later)
3. **Deficit vs Order** — Display deficit (gap to ROP) but order uses Target (T_post × D)
4. **ROIC threshold** — Hard filter at 15%, not a display column filter
5. **Dec 14 exclusion** — Critical: today's data is incomplete

---

*Agent Opus: Execute phases sequentially. Report checkpoint results before proceeding to next phase.*
