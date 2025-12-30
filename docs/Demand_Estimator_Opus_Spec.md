# Demand Estimator & PO Dashboard Fix — Opus Execution Spec

**Version:** 1.0  
**Created:** 2025-12-14  
**Purpose:** Fix demand estimation, OOS detection, and dashboard data generation  
**Executor:** Agent Opus  
**Estimated Time:** 4-5 hours

---

## Executive Summary

The PO Dashboard currently shows stale data (cutoff 2025-12-03) with only 3 test SKUs. The demand calculation (`D`) and `last_sale_date` are unreliable due to OOS noise. This spec implements:

1. **Dynamic cutoff** — Always yesterday in Asia/Almaty timezone
2. **Robust OOS detection** — Extended, partial, and intermittent patterns
3. **Anchor-blended demand** — Use `D_size_mix_reference.xlsx` as ground truth anchor
4. **Size share blending** — Data + anchor with renormalization
5. **Dashboard data generator** — Outputs JSON for all active SKUs

---

## Problem Statement

| Issue | Current State | Target State |
|-------|---------------|--------------|
| Cutoff date | Hardcoded 2025-12-03 | `yesterday` in Asia/Almaty TZ |
| SKUs displayed | 3 (test data) | All active SKUs from DB |
| OOS handling | Simple day filter | Extended/partial/intermittent detection |
| Demand source | Data only | Blended: data + anchor |
| Size shares | Raw from sales | Blended with anchor, renormalized |

---

## Source Files

### Reference Data
| File | Path | Purpose |
|------|------|---------|
| D_size_mix_reference.xlsx | `~/Docs/Autonomous_business/excel/D_size_mix_reference.xlsx` | Anchor D and size shares for 19 SKUs |

### Code to Modify
| File | Path | Changes |
|------|------|---------|
| size_allocation.py | `core/calc/size_allocation.py` | Replace demand calc with DemandEstimator |
| queries.py | `core/db/queries.py` | Add daily sales/stock queries |
| PO_Dashboard.html | Project root | Embed fresh JSON |

### Code to Create
| File | Path | Purpose |
|------|------|---------|
| demand_estimator.py | `core/calc/demand_estimator.py` | New demand estimation engine |
| generate_po_dashboard_data.py | `scripts/generate_po_dashboard_data.py` | JSON data generator |

---

## Anchor File Structure

`D_size_mix_reference.xlsx` contains 19 SKUs with columns:

```
SKU_key          | D_active | S_D | M_D | L_D | XL_D | 2XL_D | 3XL_D | 4XL_D | 22_D | 24_D | 26_D | 28_D | 30_D |
                 |          | S_share | M_share | L_share | XL_share | 2XL_share | 3XL_share | 4XL_share | 22_share | 24_share | 26_share | 28_share | 30_share | sigma
```

Key columns:
- `D_active` = Total SKU daily demand (anchor)
- `{size}_D` = Size-level daily demand
- `{size}_share` = Size share (0.0 to 1.0)
- `sigma` = Demand volatility

---

## Algorithm Specification

### 1. Dynamic Cutoff Date

```python
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, date

def get_cutoff_date() -> date:
    """
    Return yesterday in Asia/Almaty timezone.
    This ensures we never use incomplete "today" data.
    """
    almaty = ZoneInfo("Asia/Almaty")
    now = datetime.now(almaty)
    return (now - timedelta(days=1)).date()
```

### 2. Last Sale Date Calculation

Two fields:
- `last_sale_date_raw`: Max date where `total_sales(sku_key) > 0`
- `last_sale_date_valid`: End of most recent stable sales regime

```python
def calc_last_sale_dates(
    sku_key: str,
    daily_sales: dict[str, int],   # {date_str: total_units}
    daily_stock: dict[str, int],   # {date_str: total_stock}
    cutoff: date,
    lookback_days: int = 90
) -> tuple[date, date, str]:
    """
    Returns:
        (last_sale_date_raw, last_sale_date_valid, oos_flag)
    
    Algorithm:
    1. last_sale_date_raw = max(date where sales > 0)
    2. Scan backward from cutoff to find stable regime
    3. Stable = consecutive days where (sales > 0) OR (sales=0 AND stock > 0)
    4. If gap > 14 days exists before current regime → extended_oos
    5. last_sale_date_valid = end of pre-gap stable regime (or raw if no gap)
    """
```

### 3. OOS Detection Logic

Three OOS patterns to detect:

#### 3.1 Extended OOS
```python
def detect_extended_oos(
    daily_sales: dict[str, int],
    daily_stock: dict[str, int],
    cutoff: date,
    gap_threshold: int = 14
) -> tuple[bool, Optional[date], Optional[date]]:
    """
    Extended OOS = gap of >14 consecutive days where sales=0 AND stock=0
    
    Returns:
        (is_extended_oos, gap_start, gap_end)
    
    If detected: demand should use pre-gap regime data
    """
```

#### 3.2 Partial OOS (Size-Level)
```python
def detect_partial_oos(
    sku_key: str,
    size_sales: dict[str, dict[str, int]],  # {size: {date: units}}
    anchor_shares: dict[str, float],         # {size: share}
    cutoff: date,
    lookback_days: int = 30
) -> list[str]:
    """
    Partial OOS = specific sizes are OOS while siblings sell.
    
    Detection rules (check BOTH):
    
    Rule 1 - Zero sales with significant anchor share:
        anchor_share >= 0.15 AND sales = 0 for >3 consecutive days
        while at least one sibling size has sales > 0
    
    Rule 2 - Severely depressed share:
        observed_share <= anchor_share / 5 for >3 consecutive days
        Example: L anchor = 20%, observed <= 4% for 4+ days → partial OOS
    
    Returns:
        List of size codes flagged as partial OOS (e.g., ["XL", "2XL"])
    """
```

#### 3.3 Intermittent OOS
```python
def detect_intermittent_oos(
    daily_sales: dict[str, int],
    daily_stock: dict[str, int],
    cutoff: date,
    lookback_days: int = 30,
    threshold_days: int = 5
) -> bool:
    """
    Intermittent OOS = scattered OOS days within recent window.
    
    Detection:
        Count days where (sales = 0 AND stock = 0) in last 30 days
        If count > 5 → intermittent_oos = True
    
    Impact: Increases anchor weight in blending
    """
```

### 4. Demand Estimation (Blended)

```python
@dataclass
class DemandResult:
    d_data: float           # From OOS-filtered sales
    d_anchor: float         # From reference file
    d_final: float          # Blended result
    w: float                # Anchor weight used
    good_days: int          # Days with valid data
    confidence: str         # ACTUAL/MARGINAL/FALLBACK/NO_DATA
    oos_flags: list[str]    # Extended/partial/intermittent


def calc_d_blended(
    d_data: float,
    d_anchor: float,
    good_days: int,
    oos_flags: list[str],
    has_anchor: bool
) -> tuple[float, float]:
    """
    Blend data-driven demand with anchor.
    
    Weight calculation:
    
    Base weight (from data confidence):
        good_days >= 60  → w_base = 0.1  (trust data)
        good_days >= 30  → w_base = 0.3
        good_days >= 14  → w_base = 0.5
        good_days < 14   → w_base = 0.8  (trust anchor)
    
    OOS adjustments (additive, capped at 0.9):
        extended_oos     → +0.3
        partial_oos      → +0.2
        intermittent_oos → +0.1
    
    Deviation penalty:
        If |d_data - d_anchor| / d_anchor > 0.5 → +0.2
    
    Final:
        d_final = w * d_anchor + (1 - w) * d_data
    
    Edge cases:
        - No anchor (has_anchor=False) → use d_data only, emit warning
        - d_anchor = 0 → use d_data only
        - d_data = 0 AND has_anchor → use d_anchor with w=1.0
    
    Returns:
        (d_final, w)
    """
    if not has_anchor or d_anchor <= 0:
        return d_data, 0.0
    
    if d_data <= 0:
        return d_anchor, 1.0
    
    # Base weight from confidence
    if good_days >= 60:
        w = 0.1
    elif good_days >= 30:
        w = 0.3
    elif good_days >= 14:
        w = 0.5
    else:
        w = 0.8
    
    # OOS adjustments
    if "extended_oos" in oos_flags:
        w = min(0.9, w + 0.3)
    if "partial_oos" in oos_flags:
        w = min(0.9, w + 0.2)
    if "intermittent_oos" in oos_flags:
        w = min(0.9, w + 0.1)
    
    # Deviation penalty
    deviation = abs(d_data - d_anchor) / d_anchor
    if deviation > 0.5:
        w = min(0.9, w + 0.2)
    
    d_final = w * d_anchor + (1 - w) * d_data
    return d_final, w
```

### 5. Size Share Blending

```python
def calc_size_share_blended(
    share_data: dict[str, float],    # {size: share from sales}
    share_anchor: dict[str, float],  # {size: share from reference}
    w: float,                         # Same weight as demand
    partial_oos_sizes: list[str]     # Sizes flagged OOS
) -> dict[str, float]:
    """
    Blend observed size shares with anchor shares.
    
    Steps:
    1. For partial OOS sizes: force share toward anchor (increase w locally)
    2. Blend: share_final[size] = w * anchor + (1-w) * data
    3. Renormalize so sum = 1.0
    
    Returns:
        {size: final_share} summing to 1.0
    """
    sizes = set(share_data.keys()) | set(share_anchor.keys())
    blended = {}
    
    for size in sizes:
        s_data = share_data.get(size, 0.0)
        s_anchor = share_anchor.get(size, 0.0)
        
        # For partial OOS sizes, trust anchor more
        if size in partial_oos_sizes:
            local_w = min(0.95, w + 0.3)
        else:
            local_w = w
        
        blended[size] = local_w * s_anchor + (1 - local_w) * s_data
    
    # Renormalize
    total = sum(blended.values())
    if total > 0:
        blended = {s: v / total for s, v in blended.items()}
    
    return blended
```

### 6. Total Demand with Partial OOS Correction

```python
def estimate_total_demand_with_partial_oos(
    observed_sales_by_size: dict[str, float],  # Daily avg per size
    anchor_shares: dict[str, float],
    partial_oos_sizes: list[str]
) -> float:
    """
    When some sizes are OOS, estimate true total demand by scaling up.
    
    Example:
        Observed: M=6/day, L=8/day, XL=0/day (XL is OOS)
        Anchor shares: M=0.30, L=0.40, XL=0.30
        
        In-stock share = 0.30 + 0.40 = 0.70
        D_total = (6 + 8) / 0.70 = 20/day
        XL virtual demand = 20 * 0.30 = 6/day
    
    Returns:
        Estimated total daily demand (corrected for partial OOS)
    """
    in_stock_sizes = [s for s in anchor_shares if s not in partial_oos_sizes]
    in_stock_share = sum(anchor_shares.get(s, 0) for s in in_stock_sizes)
    in_stock_sales = sum(observed_sales_by_size.get(s, 0) for s in in_stock_sizes)
    
    if in_stock_share >= 0.10:  # Need at least 10% coverage to extrapolate
        return in_stock_sales / in_stock_share
    else:
        # Not enough coverage, return raw sum
        return sum(observed_sales_by_size.values())
```

---

## Data Structures

### DemandEstimator Class

```python
# core/calc/demand_estimator.py

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo
import pandas as pd
import sqlite3


@dataclass
class DemandResult:
    """Result of demand estimation for a SKU."""
    sku_key: str
    cutoff_date: date
    
    # Last sale dates
    last_sale_date_raw: Optional[date]
    last_sale_date_valid: Optional[date]
    
    # OOS detection
    oos_flags: list[str] = field(default_factory=list)
    partial_oos_sizes: list[str] = field(default_factory=list)
    
    # Demand values
    d_data: float = 0.0
    d_anchor: float = 0.0
    d_final: float = 0.0
    w: float = 0.0
    
    # Confidence
    good_days: int = 0
    confidence: str = "NO_DATA"
    
    # Size shares
    share_data: dict[str, float] = field(default_factory=dict)
    share_anchor: dict[str, float] = field(default_factory=dict)
    share_final: dict[str, float] = field(default_factory=dict)
    
    # Flags
    has_anchor: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class DemandDiagnostics:
    """Diagnostic output row for debugging/validation."""
    sku_key: str
    cutoff_date: str
    last_sale_date_raw: str
    last_sale_date_valid: str
    oos_flags: str              # Comma-separated
    partial_oos_sizes: str      # Comma-separated
    good_days: int
    d_data: float
    d_anchor: float
    w: float
    d_final: float
    share_data_str: str         # "S:0.05,M:0.15,..."
    share_anchor_str: str
    share_final_str: str
    share_mae: float            # Mean absolute error
    has_anchor: bool
    warnings: str


class DemandEstimator:
    """
    Robust demand estimator with OOS detection and anchor blending.
    """
    
    def __init__(
        self,
        anchor_path: Path,
        db_path: Path,
        lookback_days: int = 90
    ):
        self.anchor_path = anchor_path
        self.db_path = db_path
        self.lookback_days = lookback_days
        self.anchors = self._load_anchors()
    
    def _load_anchors(self) -> dict[str, dict]:
        """
        Load D_size_mix_reference.xlsx into dict.
        
        Returns:
            {sku_key: {
                'd_active': float,
                'sigma': float,
                'size_d': {size: float},      # Daily demand per size
                'size_share': {size: float}   # Share per size
            }}
        """
        pass  # IMPLEMENT
    
    def get_cutoff_date(self) -> date:
        """Return yesterday in Asia/Almaty timezone."""
        almaty = ZoneInfo("Asia/Almaty")
        now = datetime.now(almaty)
        return (now - timedelta(days=1)).date()
    
    def get_daily_sales(
        self,
        sku_key: str,
        cutoff: date
    ) -> dict[str, int]:
        """
        Get daily total sales for SKU.
        
        Returns:
            {date_str: total_units}
        """
        pass  # IMPLEMENT
    
    def get_daily_stock(
        self,
        sku_key: str,
        cutoff: date
    ) -> dict[str, int]:
        """
        Get daily total stock for SKU.
        
        Returns:
            {date_str: total_stock}
        """
        pass  # IMPLEMENT
    
    def get_size_daily_sales(
        self,
        sku_key: str,
        cutoff: date
    ) -> dict[str, dict[str, int]]:
        """
        Get daily sales by size.
        
        Returns:
            {size: {date_str: units}}
        """
        pass  # IMPLEMENT
    
    def detect_oos_flags(
        self,
        sku_key: str,
        cutoff: date
    ) -> tuple[list[str], list[str]]:
        """
        Detect all OOS patterns.
        
        Returns:
            (oos_flags, partial_oos_sizes)
        """
        pass  # IMPLEMENT
    
    def get_demand(
        self,
        sku_key: str,
        store_code: str = "UNIVERSAL",
        cutoff: Optional[date] = None
    ) -> DemandResult:
        """
        Main entry point: get blended demand for a SKU.
        """
        pass  # IMPLEMENT
    
    def generate_diagnostics(
        self,
        sku_key: str,
        result: DemandResult
    ) -> DemandDiagnostics:
        """
        Generate diagnostic row for this SKU.
        """
        pass  # IMPLEMENT
```

---

## Implementation Phases

### Phase A: Anchor Loading (30 min)

**Files:** `core/calc/demand_estimator.py`

**Tasks:**
1. Create `DemandEstimator` class skeleton
2. Implement `_load_anchors()`:
   - Read Excel with pandas
   - Parse size columns (S_D, M_D, ... and S_share, M_share, ...)
   - Handle NaN values (some kids sizes have NaN for adult columns)
   - Return structured dict
3. Implement `get_cutoff_date()` with Asia/Almaty timezone
4. Write unit tests

**Acceptance:**
```python
estimator = DemandEstimator(anchor_path, db_path)
assert len(estimator.anchors) == 19
assert "CL_OC_MEN_LINE52_BLACK" in estimator.anchors
assert estimator.anchors["CL_OC_MEN_LINE52_BLACK"]["d_active"] == 70.0
```

### Phase B: Data Queries (30 min)

**Files:** `core/calc/demand_estimator.py`, `core/db/queries.py`

**Tasks:**
1. Implement `get_daily_sales(sku_key, cutoff)`:
   ```sql
   SELECT order_date, SUM(quantity) as units
   FROM fact_sales
   WHERE sku_key = ?
     AND order_date >= date(?, '-90 days')
     AND order_date <= ?
   GROUP BY order_date
   ```
2. Implement `get_daily_stock(sku_key, cutoff)`:
   ```sql
   SELECT snapshot_date, SUM(stock_qty) as stock
   FROM fact_inventory_snapshot_size
   WHERE sku_key = ?
     AND snapshot_date >= date(?, '-90 days')
     AND snapshot_date <= ?
   GROUP BY snapshot_date
   ```
   - If no snapshot table, use stock_ledger with running balance
3. Implement `get_size_daily_sales(sku_key, cutoff)`:
   ```sql
   SELECT my_size, order_date, SUM(quantity) as units
   FROM fact_sales
   WHERE sku_key = ?
     AND order_date >= date(?, '-90 days')
     AND order_date <= ?
   GROUP BY my_size, order_date
   ```
4. Write unit tests

**Acceptance:**
```python
sales = estimator.get_daily_sales("CL_OC_MEN_LINE52_BLACK", cutoff)
assert isinstance(sales, dict)
assert all(isinstance(k, str) and isinstance(v, int) for k, v in sales.items())
```

### Phase C: OOS Detection (60 min)

**Files:** `core/calc/demand_estimator.py`

**Tasks:**
1. Implement `detect_extended_oos()`:
   - Scan for gaps >14 days where sales=0 AND stock=0
   - Return gap boundaries
2. Implement `detect_partial_oos()`:
   - **Rule 1:** anchor_share >= 0.15 AND sales=0 for >3 days while siblings sell
   - **Rule 2:** observed_share <= anchor_share/5 for >3 consecutive days
   - Check both rules for each size
3. Implement `detect_intermittent_oos()`:
   - Count OOS days (sales=0 AND stock=0) in last 30 days
   - Return True if count > 5
4. Implement `detect_oos_flags()` combining all detectors
5. Write unit tests with mock data:
   - Test extended OOS with 20-day gap
   - Test partial OOS with XL at 0 while M/L selling
   - Test intermittent with 7 scattered OOS days

**Acceptance:**
```python
# Extended OOS test
sales = {"2025-12-01": 5, "2025-12-02": 0, ..., "2025-12-20": 0, "2025-12-21": 3}
stock = {"2025-12-01": 10, "2025-12-02": 0, ..., "2025-12-20": 0, "2025-12-21": 50}
flags, _ = estimator.detect_oos_flags(...)
assert "extended_oos" in flags

# Partial OOS test (Rule 1)
size_sales = {"M": {...}, "L": {...}, "XL": {"2025-12-10": 0, "2025-12-11": 0, ...}}
anchor_shares = {"M": 0.30, "L": 0.40, "XL": 0.30}
_, partial = estimator.detect_oos_flags(...)
assert "XL" in partial

# Partial OOS test (Rule 2 - depressed share)
# L anchor = 0.35 (35%), observed = 0.05 (5%) for 5 days
# 0.05 < 0.35/5 = 0.07 → partial OOS
_, partial = estimator.detect_oos_flags(...)
assert "L" in partial
```

### Phase D: Demand Blending (45 min)

**Files:** `core/calc/demand_estimator.py`

**Tasks:**
1. Implement `calc_last_sale_dates()`:
   - Find raw (max date with sales)
   - Find valid (end of stable regime before any gap)
2. Implement `calc_d_data_oos_filtered()`:
   - Filter out OOS days
   - Calculate average from good days
   - Apply confidence uplift (1.2× for marginal, 1.5× for fallback)
3. Implement `calc_d_blended()`:
   - Base weight from good_days
   - OOS adjustments
   - Deviation penalty
   - Final blend
4. Implement `estimate_total_demand_with_partial_oos()`:
   - Scale up based on in-stock share
5. Wire everything into `get_demand()` method
6. Write unit tests

**Acceptance:**
```python
result = estimator.get_demand("CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK")
assert result.d_final > 0
assert 0 <= result.w <= 1.0
assert result.d_final == result.w * result.d_anchor + (1 - result.w) * result.d_data
```

### Phase E: Size Share Blending (30 min)

**Files:** `core/calc/demand_estimator.py`

**Tasks:**
1. Implement `calc_size_share_data()`:
   - Calculate shares from last 30 days of sales
   - Handle sizes with 0 sales
2. Implement `calc_size_share_blended()`:
   - Blend with anchor
   - Boost anchor weight for partial OOS sizes
   - Renormalize to sum=1.0
3. Integrate into `get_demand()` method
4. Write unit tests

**Acceptance:**
```python
result = estimator.get_demand("CL_OC_MEN_LINE52_BLACK")
assert abs(sum(result.share_final.values()) - 1.0) < 0.001
assert all(0 <= v <= 1.0 for v in result.share_final.values())
```

### Phase F: Dashboard Data Generator (60 min)

**Files:** `scripts/generate_po_dashboard_data.py`

**Tasks:**
1. Create script skeleton with argparse
2. Load all active SKUs:
   ```sql
   SELECT DISTINCT sku_key FROM dim_sku_size WHERE active_flag = 1
   ```
3. For each SKU:
   - Call `estimator.get_demand()`
   - Calculate PO metrics (ROP, deficit, order_qty, dates)
   - Generate SKU-level and size-level rows
4. Apply ROIC filter (≥15%)
5. Output JSON to `exports/po_dashboard_data.json`
6. Output diagnostics CSV to `exports/demand_diagnostics.csv`

**JSON Schema:**
```json
{
  "generated_at": "2025-12-14T10:30:00+05:00",
  "cutoff_date": "2025-12-13",
  "roic_threshold_pct": 15.0,
  "holiday_deadline": "2025-12-31",
  "summary": {
    "total_skus": 45,
    "total_units": 1250,
    "priority_skus": 12,
    "total_weight_kg": 625.5,
    "skus_without_anchor": 3
  },
  "sku_level": [...],
  "size_level": [...],
  "diagnostics": [...]
}
```

**Acceptance:**
```bash
python scripts/generate_po_dashboard_data.py
# Output:
# ✓ Loaded 19 anchor SKUs
# ✓ Found 52 active SKUs in database
# ✓ Generated 45 SKUs with ROIC >= 15%
# ✓ Wrote exports/po_dashboard_data.json
# ✓ Wrote exports/demand_diagnostics.csv
```

### Phase G: Integration (45 min)

**Files:** `core/calc/size_allocation.py`, `PO_Dashboard.html`

**Tasks:**
1. Modify `size_allocation.py`:
   - Import `DemandEstimator`
   - Replace `calc_d_sku_with_oos_filter()` calls with `estimator.get_demand()`
   - Use blended size shares for allocation
2. Update `PO_Dashboard.html`:
   - Keep React template
   - Document how to embed fresh JSON
   - Add "data freshness" indicator showing cutoff_date
3. Write integration tests

**Acceptance:**
```python
from core.calc.size_allocation import generate_po_draft
from core.calc.demand_estimator import DemandEstimator

# Old behavior (data only)
draft_old = generate_po_draft("CL_OC_MEN_LINE52_BLACK", use_estimator=False)

# New behavior (blended)
draft_new = generate_po_draft("CL_OC_MEN_LINE52_BLACK", use_estimator=True)

# New should be more stable
assert draft_new.d_sku > 0
assert draft_new.demand_confidence != "NO_DATA"
```

### Phase H: Validation (30 min)

**Tasks:**
1. Run full validation checklist (see below)
2. Spot-check 3 SKUs against manual calculation
3. Verify dashboard renders all SKUs
4. Document any issues found

---

## Diagnostics Table Schema

Output file: `exports/demand_diagnostics.csv`

| Column | Type | Description |
|--------|------|-------------|
| sku_key | str | SKU identifier |
| cutoff_date | str | YYYY-MM-DD |
| last_sale_date_raw | str | Max date with any sales |
| last_sale_date_valid | str | Planning-safe date |
| oos_flags | str | Comma-separated: extended_oos,partial_oos,intermittent_oos |
| partial_oos_sizes | str | Comma-separated size codes |
| good_days | int | Days with valid data |
| d_data | float | Demand from sales data |
| d_anchor | float | Demand from reference |
| w | float | Anchor weight (0-1) |
| d_final | float | Blended demand |
| share_data_str | str | "S:0.05,M:0.15,L:0.35,..." |
| share_anchor_str | str | Same format |
| share_final_str | str | Same format |
| share_mae | float | Mean absolute error vs anchor |
| has_anchor | bool | True if SKU in reference file |
| warnings | str | Any warning messages |

---

## Validation Checklist

| # | Check | Pass Criteria | Command/Method |
|---|-------|---------------|----------------|
| 1 | Cutoff is dynamic | `cutoff_date = yesterday in Asia/Almaty` | Check JSON output |
| 2 | All active SKUs queried | Count matches DB | `SELECT COUNT(DISTINCT sku_key) FROM dim_sku_size WHERE active_flag=1` |
| 3 | Anchors loaded | 19 SKUs from reference | `len(estimator.anchors) == 19` |
| 4 | Missing anchor flagged | SKUs not in reference have `has_anchor=False` | Check diagnostics CSV |
| 5 | Extended OOS detected | SKU with 15+ day gap gets flag | Create test case |
| 6 | Partial OOS Rule 1 | Size with ≥15% share, 0 sales, siblings selling → flagged | Create test case |
| 7 | Partial OOS Rule 2 | Size with share ≤ anchor/5 for >3 days → flagged | Create test case |
| 8 | Intermittent OOS | >5 OOS days in 30 → flagged | Create test case |
| 9 | D_final in range | 0.5×min ≤ D_final ≤ 1.5×max of (d_data, d_anchor) | Check diagnostics |
| 10 | Size shares sum to 1.0 | All share_final sums to 1.0 ± 0.001 | Check all SKUs |
| 11 | ROIC filter works | No SKUs with ROIC < 15% in output | Check JSON |
| 12 | Dashboard renders | HTML loads without JS errors | Open in browser |
| 13 | All SKUs visible | No pagination bug limiting to N rows | Count rows in browser |

---

## Edge Cases to Handle

| Case | Detection | Action |
|------|-----------|--------|
| New SKU (<14 days) | `good_days < 14` | w = 0.8 (trust anchor) |
| No anchor row | `sku_key not in anchors` | Use data only, emit warning |
| All sizes OOS | `sum(daily_sales) == 0` for all recent days | Keep anchor D, mark "currently_oos" |
| Single size has anchor but no sales | anchor_share > 0, sales = 0 | Treat as partial OOS candidate |
| Highly seasonal | Large deviation from anchor | Blend still applies; future: use D_peak |
| Missing days in history | Date not in sales dict | Treat as unknown (not zero) |
| Stock data unavailable | No inventory snapshot table | Use sales-only OOS inference |

---

## File Structure After Implementation

```
~/Docs/Autonomous_business/
├── core/
│   ├── calc/
│   │   ├── demand_estimator.py    # NEW
│   │   ├── size_allocation.py     # MODIFIED
│   │   └── ...
│   └── db/
│       └── queries.py             # MODIFIED
├── scripts/
│   └── generate_po_dashboard_data.py  # NEW
├── exports/
│   ├── po_dashboard_data.json     # Generated
│   └── demand_diagnostics.csv     # Generated
├── excel/
│   └── D_size_mix_reference.xlsx  # Reference (read-only)
├── docs/
│   └── Demand_Estimator_Opus_Spec.md  # This file
└── PO_Dashboard.html              # MODIFIED (embed fresh JSON)
```

---

## Test Data Scenarios

### Scenario 1: Clean SKU (no OOS)
```python
# CL_OC_MEN_LINE52_BLACK - high volume, clean data
# Expected: low w (trust data), d_final ≈ d_data
```

### Scenario 2: Extended OOS
```python
# SKU was OOS for 20 days, just restocked
# Expected: extended_oos flag, high w, d_final ≈ d_anchor
```

### Scenario 3: Partial OOS (Rule 1)
```python
# XL has anchor_share=0.30 but sales=0 for 5 days
# M and L selling normally
# Expected: XL in partial_oos_sizes, d_final scaled up
```

### Scenario 4: Partial OOS (Rule 2)
```python
# L has anchor_share=0.35 but observed_share=0.05 (≤0.07) for 4 days
# Expected: L in partial_oos_sizes
```

### Scenario 5: New SKU
```python
# Only 10 days of sales data
# Expected: good_days=10, confidence=FALLBACK, high w
```

### Scenario 6: No Anchor
```python
# SKU not in D_size_mix_reference.xlsx
# Expected: has_anchor=False, w=0, d_final=d_data, warning emitted
```

---

## Success Metrics

After implementation:
1. Dashboard shows **all active SKUs** (not 3)
2. Cutoff date is **yesterday** (not 2025-12-03)
3. Demand estimates are **stable** despite OOS noise
4. Size allocations **match business intuition** for known SKUs
5. Diagnostics CSV enables **debugging** of any SKU

---

## Appendix: Reference SKUs in Anchor File

```
1.  CL_NEW-CLO_MEN_SPIDER-RUSH_BLACK    D=4.25
2.  CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK     D=16.72
3.  CL_NEW-CLO_MEN_NIKE-SHIRT_WHITE     D=10.00
4.  CL_NEW-CLO_MEN_NIKE-SHIRT_GREY      D=4.00
5.  CL_NEW-CLO_MEN_RUSH-PRO_BLACK       D=5.10
6.  CL_NEW-CLO_MEN_RUSH-PRO_WHITE       D=6.31
7.  CL_NEW-CLO_MEN_T-SHIRT_BLACK        D=5.95
8.  CL_NEW-CLO_MEN_T-SHIRT_White        D=4.50
9.  CL_NEW-CLO_MEN_BERSERK-SHIRT_BLACK  D=6.40
10. CL_NEW-CLO_MEN_BERSERK-SHIRT_WHITE  D=4.80
11. CL_NEW-CLO_MEN_BERSERK-SHIRT_GREY-BLK D=2.00
12. CL_NEW-CLO_MEN_BERSERK-RUSH_BLACK   D=3.06
13. CL_NEW-CLO_MEN_ROMBIK_BLACK         D=7.41
14. CL_NEW-CLO_KID_ROMBIK_BLACK         D=4.73
15. CL_NEW-CLO_KIDS_KID-31_BLACK        D=5.40
16. CL_NEW-CLO2_MEN_HUS_GREEN           D=5.00
17. CL_NEW-CLO2_MEN_SUIT-61_BLACK       D=5.00
18. CL_OC_MEN_LINE52_BLACK             D=70.00
19. CL_OC_MEN_LINE51_WHITE              D=12.16
```

---

*End of specification. Agent Opus: execute phases A through H sequentially, reporting checkpoint results before proceeding.*
