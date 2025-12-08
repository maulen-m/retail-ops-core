# Phase 9.6: Size-Aware PO Engine
## Implementation Task Breakdown for Opus

**Date:** December 9, 2025  
**Spec Document:** `AutoPO_Size_Logic_Diagnosis_V2.md`  
**Estimated Effort:** 16 hours  
**Priority:** HIGH (capital efficiency improvement)

---

## Prerequisites

Before starting:
1. This document must be in repo at `/docs/Phase_9_6_Size_Aware_PO_Engine.md`
2. Spec doc `AutoPO_Size_Logic_Diagnosis_V2.md` must be in `/docs/`
3. All Phase 9.5 tests passing (201+ tests)

---

## Phase 9.6 Overview

**Problem:** Current Auto-PO uses static 90-day mix percentages, ignoring per-size stock levels and demand.

**Solution:** Implement true size-level allocation per spec:
- OOS-filtered demand calculation
- Size mix with 3%/40% guardrails
- Per-size safety stock, ROP, T_post
- Lead time consumption projection
- ANY-size REORDER trigger
- 3-tier ROIC gate

---

## Task List

### Section A: Parameter Management (Foundation)

#### TASK-150: Create inventory_params.py
**File:** `core/config/inventory_params.py`

**What to build:**
```python
@dataclass(frozen=True)
class InventoryParams:
    L: int = 21
    R: int = 10
    B: int = 14
    z: float = 1.65
    TV: float = 0.23
    sigma_factor: float = 0.4
    min_size_mix: float = 0.03
    max_size_mix: float = 0.40
    roic_full_approval: float = 0.20
    roic_flag_threshold: float = 0.10
    new_sku_30d_factor: float = 0.75
    new_sku_60d_factor: float = 0.85
    new_sku_90d_factor: float = 0.95

PARAMS = InventoryParams()
def get_params() -> InventoryParams: ...
```

**Validation:**
- Values match `Master_Inventory_Rules_v5.3.md` exactly
- Dataclass is frozen (immutable)
- `get_params()` returns singleton

**Tests:** 5 tests
- test_params_match_master_rules
- test_params_immutable
- test_get_params_singleton
- test_all_params_have_values
- test_no_none_values

---

#### TASK-151: Create size_allocation.py data structures
**File:** `core/calc/size_allocation.py`

**What to build:**
```python
class OrderStatus(Enum): REORDER, WAIT, OK
class ROICAction(Enum): ORDER_FULL, ORDER_WITH_FLAG, REVIEW_REQUIRED

@dataclass
class SizeData: ...
@dataclass  
class SizeAllocation: ...
@dataclass
class PODraft: ...
```

**Copy exact definitions from spec Section 3.1**

**Tests:** 3 tests
- test_order_status_values
- test_roic_action_values
- test_dataclass_creation

---

### Section B: Demand Calculation

#### TASK-152: Implement OOS-filtered demand calculation
**File:** `core/calc/size_allocation.py`

**Function:** `calc_d_sku_with_oos_filter()`

**Logic:**
1. Loop through sales_history and stock_history in parallel
2. Skip days where BOTH sales=0 AND stock=0 (true OOS)
3. Return average of good days with confidence level

**Confidence levels:**
- ≥30 good days → "ACTUAL"
- 14-29 good days → "MARGINAL" (1.2× uplift)
- <14 good days → "FALLBACK" (1.5× uplift)
- 0 good days → "NO_DATA"

**Tests:** 8 tests
- test_oos_filter_excludes_stockout_days
- test_oos_filter_keeps_zero_sales_with_stock
- test_oos_filter_actual_confidence
- test_oos_filter_marginal_confidence
- test_oos_filter_fallback_confidence
- test_oos_filter_no_data
- test_oos_filter_all_good_days
- test_oos_filter_mixed_oos_periods

---

#### TASK-153: Implement size mix with guardrails
**File:** `core/calc/size_allocation.py`

**Function:** `calc_size_mix_with_guardrails()`

**Logic:**
1. Calculate raw mix from size_sales dict
2. Apply floor (3%) and cap (40%)
3. Renormalize to sum to 1.0
4. Handle edge case: total=0 → uniform distribution

**Tests:** 6 tests
- test_mix_sums_to_one
- test_mix_floor_applied
- test_mix_cap_applied
- test_mix_renormalization
- test_mix_zero_sales_uniform
- test_mix_single_dominant_size

---

### Section C: Safety Stock & ROP (Per-Size)

#### TASK-154: Implement per-size safety stock
**File:** `core/calc/size_allocation.py`

**Function:** `calc_safety_stock_for_size()`

**Formulas (from Master_Inventory_Rules_v5.3.md):**
```
σ_size = σ_sku × size_mix
SS_demand = z × σ_size × √L
SS_floor = D_size × B
SS_mix = TV × D_size × L
SS_total = SS_demand + SS_floor + SS_mix
```

**Tests:** 6 tests
- test_sigma_size_scales_with_mix
- test_ss_demand_formula
- test_ss_floor_formula
- test_ss_mix_formula
- test_ss_total_sum
- test_ss_zero_demand

---

#### TASK-155: Implement per-size ROP and T_post
**File:** `core/calc/size_allocation.py`

**Functions:**
- `calc_rop_for_size()`: ROP = D × L + SS_total
- `calc_t_post_for_size()`: T_post = R + (SS_total / D)

**Edge case:** D=0 → T_post = R (fallback)

**Tests:** 5 tests
- test_rop_formula
- test_t_post_formula
- test_t_post_zero_demand_fallback
- test_rop_increases_with_demand
- test_t_post_increases_with_ss

---

### Section D: Stock Projection & Status

#### TASK-156: Implement lead time consumption
**File:** `core/calc/size_allocation.py`

**Function:** `calc_pre_arrival_stock()`

**Formula:**
```
Pre = Current + Inbound - (D_size × days_to_arrival)
Pre = max(0, Pre)  # Can't go negative
```

**Tests:** 5 tests
- test_pre_arrival_basic
- test_pre_arrival_with_inbound
- test_pre_arrival_high_consumption
- test_pre_arrival_floor_zero
- test_pre_arrival_no_consumption

---

#### TASK-157: Implement per-size status calculation
**File:** `core/calc/size_allocation.py`

**Function:** `calc_status_for_size()`

**Logic (check Total FIRST):**
1. Total < ROP → REORDER
2. Current < ROP (but Total ≥ ROP) → WAIT
3. Else → OK

**Tests:** 5 tests
- test_status_reorder
- test_status_wait
- test_status_ok
- test_status_boundary_total_equals_rop
- test_status_boundary_current_equals_rop

---

#### TASK-158: Implement PO trigger logic
**File:** `core/calc/size_allocation.py`

**Function:** `should_generate_po()`

**Rule:** ANY size in REORDER → trigger PO for whole SKU

**Returns:** (should_order: bool, trigger_sizes: list)

**Tests:** 4 tests
- test_trigger_single_reorder
- test_trigger_multiple_reorder
- test_no_trigger_all_ok
- test_no_trigger_all_wait

---

### Section E: Allocation & Adjustments

#### TASK-159: Implement size allocation calculation
**File:** `core/calc/size_allocation.py`

**Function:** `calc_order_qty_for_size()`

**Formula:**
```
target = T_post × D_size
order = max(0, round(target - pre_arrival))
```

**Tests:** 5 tests
- test_allocation_basic
- test_allocation_overstocked_zero
- test_allocation_rounds_correctly
- test_allocation_floor_zero
- test_allocation_high_demand

---

#### TASK-160: Implement new SKU adjustments
**File:** `core/calc/size_allocation.py`

**Function:** `adjust_for_new_sku()`

**Factors:**
- <30 days: 0.75×
- 30-60 days: 0.85×
- 60-90 days: 0.95×
- ≥90 days: 1.0×

**Tests:** 5 tests
- test_new_sku_under_30
- test_new_sku_30_to_60
- test_new_sku_60_to_90
- test_new_sku_full_history
- test_new_sku_minimum_one

---

#### TASK-161: Implement low demand insurance
**File:** `core/calc/size_allocation.py`

**Function:** `apply_low_demand_insurance()`

**Rule:** If D_size < 0.1 AND mix ≥ 5% → add 1% of total PO

**Tests:** 4 tests
- test_insurance_applied
- test_insurance_not_needed_high_demand
- test_insurance_not_needed_low_mix
- test_insurance_minimum_one

---

### Section F: ROIC Gate

#### TASK-162: Implement ROIC calculation
**File:** `core/calc/size_allocation.py`

**Function:** `calc_roic()`

**Formula (from Master_Inventory_Rules_v5.3.md):**
```
K_avg = D × (L + R/2) × COGS + SS_total × COGS
Monthly_ROIC = (Unit_profit × D × 30) / K_avg
```

**Tests:** 4 tests
- test_roic_formula
- test_roic_zero_k_avg
- test_roic_high_profit
- test_roic_matches_excel

---

#### TASK-163: Implement 3-tier ROIC gate
**File:** `core/calc/size_allocation.py`

**Function:** `apply_roic_gate()`

**Tiers:**
- ≥20%: ORDER_FULL
- 10-20%: ORDER_WITH_FLAG
- <10%: REVIEW_REQUIRED (qty → 0)

**Tests:** 4 tests
- test_roic_gate_full
- test_roic_gate_flag
- test_roic_gate_review
- test_roic_gate_boundary

---

### Section G: Main Generator

#### TASK-164: Implement generate_po_draft()
**File:** `core/calc/size_allocation.py`

**Function:** `generate_po_draft()`

**Steps:**
1. Get params
2. Calculate size mix with guardrails
3. Calculate per-size metrics (D, SS, ROP, T_post)
4. Calculate per-size status
5. Check if PO needed (trigger logic)
6. Calculate allocations
7. Apply low demand insurance
8. Apply new SKU adjustment
9. Build totals
10. Calculate ROIC
11. Apply ROIC gate
12. Return PODraft

**Copy full implementation from spec Section 3.11**

**Tests:** 8 tests
- test_po_draft_no_order_needed
- test_po_draft_single_size_reorder
- test_po_draft_multiple_size_reorder
- test_po_draft_roic_blocked
- test_po_draft_new_sku_adjusted
- test_po_draft_insurance_applied
- test_po_draft_total_matches_sum
- test_po_draft_example_line52

---

### Section H: Integration

#### TASK-165: Add DB queries for size-level data
**File:** `core/db/queries.py` (new or extend existing)

**Functions:**
- `get_size_sales_history(sku_key, store_code, days=90)` → {size: sales_list}
- `get_size_stock_history(sku_key, store_code, days=90)` → {size: stock_list}
- `get_size_current_stock(sku_key, store_code)` → {size: int}
- `get_size_inbound(sku_key, store_code)` → {size: int}

**Tests:** 4 tests (integration tests with test DB)

---

#### TASK-166: Replace apply_size_splits in po_generator.py
**File:** `core/automation/po_generator.py`

**Changes:**
1. Import `generate_po_draft` from size_allocation
2. Replace `apply_size_splits()` calls with `generate_po_draft()`
3. Update PO draft creation to use new output format
4. Keep backward compatibility for existing draft tables

**Tests:** 3 tests
- test_po_generator_uses_new_allocation
- test_po_generator_backward_compatible
- test_po_generator_output_format

---

#### TASK-167: Update export_po_suggestions.py
**File:** `scripts/export_po_suggestions.py`

**Changes:**
1. Add new columns: `trigger_sizes`, `roic_action`, `demand_confidence`
2. Update size columns to show actual allocation (not just mix %)
3. Add `pre_arrival_stock` per size for debugging

**Tests:** 2 tests
- test_export_new_columns
- test_export_format_unchanged

---

### Section I: Validation

#### TASK-168: Create validation script
**File:** `scripts/validate_size_allocation.py`

**Checks:**
- [ ] D_size sums to D_sku (within 1%)
- [ ] Size mix sums to 1.0
- [ ] SS_total_sku = Σ SS_total_size (within 1%)
- [ ] No size gets 0 if mix > 3% and REORDER
- [ ] Total_qty = Σ size allocations
- [ ] ROIC matches Excel ±2%
- [ ] Compare LINE52, LINE51 to known values

**Output:** Validation report with PASS/FAIL per check

---

#### TASK-169: Create comparison report
**File:** `scripts/compare_old_vs_new_allocation.py`

**Purpose:** Show side-by-side comparison of old static allocation vs new size-aware

**Output:**
```
SKU: LINE52_BLACK
OLD (static mix):  S=28, M=33, L=94, XL=119, 2XL=79, 3XL=50, 4XL=22
NEW (size-aware):  S=0,  M=33, L=0,  XL=150, 2XL=95, 3XL=50, 4XL=22
DIFF:              S=-28, L=-94, XL=+31, 2XL=+16
REASON: L overstocked (pre=180, target=72), XL understocked (pre=15, target=90)
```

---

### Section J: Documentation

#### TASK-170: Update DAILY_SOP.md
**File:** `docs/DAILY_SOP.md`

**Changes:**
- Update PO interpretation section
- Add new columns explanation
- Add size-aware allocation description
- Update troubleshooting for new logic

---

#### TASK-171: Update ARCHITECTURE.md
**File:** `docs/ARCHITECTURE.md`

**Changes:**
- Add size_allocation.py module description
- Add inventory_params.py description
- Update Auto-PO flow diagram
- Add data flow for size-level calculation

---

## Test Summary

| Section | Tasks | Tests |
|---------|-------|-------|
| A: Params | 2 | 8 |
| B: Demand | 2 | 14 |
| C: SS/ROP | 2 | 11 |
| D: Status | 3 | 14 |
| E: Allocation | 3 | 14 |
| F: ROIC | 2 | 8 |
| G: Main | 1 | 8 |
| H: Integration | 3 | 9 |
| I: Validation | 2 | 0 (scripts) |
| J: Docs | 2 | 0 (docs) |
| **TOTAL** | **22** | **86** |

---

## Execution Order

**Day 1 (6 hrs):**
- TASK-150, 151 (params + data structures)
- TASK-152, 153 (demand calculation)
- TASK-154, 155 (safety stock)

**Day 2 (5 hrs):**
- TASK-156, 157, 158 (stock projection + status)
- TASK-159, 160, 161 (allocation + adjustments)
- TASK-162, 163 (ROIC)

**Day 3 (5 hrs):**
- TASK-164 (main generator)
- TASK-165, 166, 167 (integration)
- TASK-168, 169 (validation)
- TASK-170, 171 (docs)

---

## Success Criteria

Phase 9.6 is complete when:

1. **All 86 tests passing**
2. **Validation script passes** all checks for LINE52, LINE51
3. **Comparison report shows** meaningful differences (proves new logic is working)
4. **ROIC matches Excel** within ±2% for test SKUs
5. **No regressions** in existing 201+ tests

---

## Commit Strategy

One commit per task with format:
```
feat(po): TASK-1XX - brief description

- Implementation details
- Tests added: N
```

Final commit:
```
feat(po): Phase 9.6 Size-Aware PO Engine complete

- 22 tasks, 86 new tests
- Replaces static mix with true size-level allocation
- Validation passed for LINE52, LINE51
```

---

*Document created: December 9, 2025*
*For execution by: Opus*
