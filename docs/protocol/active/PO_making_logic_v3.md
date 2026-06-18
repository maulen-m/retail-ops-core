# PO Making Logic v3.0 — Universal Deterministic Purchase-Order Algorithm

**Version:** 3.0
**Status:** replacement for `PO_making_logic_v2.md`
**Must conform to:** `Master_Inventory_Rules_v9.md`
**Scope:** all ACMEWEAR e-commerce projects that generate, review, or consume PO recommendations.

---

## 1. Objective

Generate purchase-order quantities that:

1. prevent profitable stockouts,
2. avoid tying capital in weak inventory,
3. use real inbound truth,
4. account for stock that will sell before the PO arrives,
5. calculate size-level quantities,
6. preserve matched-set feasibility,
7. separate observed demand from scenario demand,
8. expose confidence and override reasons.

The algorithm must be deterministic: same inputs produce same outputs.

---

## 2. Non-negotiable principles

```text
DB / canonical operational truth beats Excel.
Real inbound beats draft PO plans.
Observed/OOS-adjusted demand beats scenario demand unless a documented override exists.
Projected arrival stock beats current stock for PO quantity.
Set feasibility beats total component quantity.
Capital gates beat growth excitement.
```

### 2.1 Governed-off auto-PO state

Auto-PO is deliberately OFF under owner decision OD-009 until restart criteria are
green and the owner gives a new explicit restart approval. The OFF state is a
valid governed state only when all of the following are true:

- production `fact_po_draft`, `fact_po_draft_lines`, and `fact_po_execution`
  contain zero rows;
- no installed LaunchAgent references `run_auto_po.py` or an auto-PO label;
- the stop-buy advisory gates are machine-readable:
  `frozen_cover_gt_180d`, `size_overstock`, `return_qc_telemetry`,
  `ppch_v1_gate`, `cash_truth_gate`, and `ads_crr_gate`;
- restart criteria are machine-readable and include COGS truth for 30 days,
  stock truth for 30 days, cash truth, FX/floor vintage, size-prior seven-test
  proof, forecast backtest threshold set at acceptance, and explicit owner
  approval;
- proposal and capital-protection artifacts may be generated for audit, but
  they remain advisory-only and must not create PO drafts.

The machine-readable gate config is
`config/validation/po_governed_off_gates.json`. The validation/report surface is
`scripts/report_po_governed_off.py`.

---

## 3. Required input tables / structures

### 3.1 SKU / product master

Minimum fields:

```text
sku_key
sku_id
product_family_id
product_profile
component_type
set_id
size_code
color_id
product_type
channel
supplier_code
base_cost
base_cost_currency
weight_kg
active_status
new_test_status
```

### 3.2 Current stock snapshot

Minimum grain: `sku_id` or `component_id × size`.

```text
snapshot_at
sku_key
sku_id
component_id
size_code
on_hand_sellable
on_hand_reserved
on_hand_quarantine
on_hand_damaged
source_system
```

### 3.3 Inbound truth

Minimum grain: PO × SKU/component × size.

```text
po_id
po_part_id
supplier_id
sku_key
sku_id
component_id
size_code
qty
status
eta_date
is_paid
trusted_for_po_calc
source_system
```

Count as trusted inbound only if it is real, confirmed, not arrived, and not disputed.

### 3.4 Sales / demand history

Minimum grain: date × SKU/size/channel.

```text
date
sku_key
sku_id
size_code
channel
units_sold
stock_start_qty
stock_end_qty
ads_spend_associated
is_oos_day
is_contaminated_day
```

### 3.5 Channel economics

```text
channel
sell_price
commission_rate
tax_rate
delivery_fee
ads_cost_per_unit
return_rate_assumption
net_revenue_formula_version
```

### 3.6 Parameters

```text
Effective_L
R_eff
Buffer_Days
z_factor
TV_mix
min_size_share
max_size_share
new_test_cap_pct
combined_new_test_cap_pct
new_test_capital_cap_pct
paid_fraction_in_pipeline
```

---

## 4. Output contract

Every PO recommendation must output:

```text
inventory_rules_version
po_logic_version
calculated_at
source_data_timestamp
sku_key
sku_id
color_id
size_code
D_observed
D_oos_adjusted
D_scenario
D_eff
D_eff_source
demand_confidence
current_sellable
trusted_inbound
projected_arrival_stock
SS_size
ROP_size
target_after_arrival
raw_order_qty
final_order_qty
status
capital_status
ROIC_status
override_flag
override_reason
validation_status
```

For matched sets, also output:

```text
set_id
component_quantities_by_size
sellable_set_qty_by_size
blocked_by_component
strict_same_size_rule_applied
```

---

## 5. Core algorithm overview

```text
1. Load canonical inputs.
2. Validate source timestamps and required fields.
3. Compute clean observed demand.
4. Compute OOS-adjusted demand.
5. Classify demand confidence.
6. Select D_eff.
7. Compute current stock and trusted inbound.
8. Project stock to arrival date.
9. Compute size mix and safety stock.
10. Compute ROP and target after arrival.
11. Compute raw order quantity.
12. Apply supplier, MOQ, pack, capital, new/test, and override constraints.
13. Apply matched-set feasibility where relevant.
14. Produce final PO recommendation and validation report.
```

---

## 6. Demand calculation

### 6.1 OOS-aware observed demand

```python
def calc_observed_d(daily_rows, min_clean_days=14):
    clean_units = 0
    clean_days = 0

    for row in daily_rows:
        if row.is_contaminated_day:
            continue
        if row.units_sold == 0 and row.stock_start_qty == 0:
            continue
        clean_units += row.units_sold
        clean_days += 1

    if clean_days == 0:
        return 0.0, "NO_CLEAN_DAYS"

    d = clean_units / clean_days
    if clean_days < min_clean_days:
        return d, "LOW_DATA"
    return d, "OBSERVED"
```

### 6.2 OOS-adjusted demand

Use OOS-adjusted demand when stockouts or suppressed sizes caused measured demand to be lower than real demand.

```python
def calc_oos_adjusted_d(observed_d, anchor_d=None, stockout_ratio=0.0, suppression_flag=False):
    if anchor_d is None:
        return observed_d

    if suppression_flag:
        return max(observed_d, anchor_d)

    if stockout_ratio > 0:
        # Conservative adjustment: do not explode demand blindly.
        adjustment = min(1.0 / max(0.25, 1.0 - stockout_ratio), 2.0)
        return max(observed_d, min(observed_d * adjustment, anchor_d))

    return observed_d
```

### 6.3 Demand confidence

```python
def classify_demand_confidence(clean_days, units_sold, stockout_ratio, is_new_test, is_promo_distorted):
    if is_new_test:
        return "NEW_TEST"
    if is_promo_distorted:
        return "PROMO_DISTORTED"
    if clean_days >= 30 and units_sold >= 30 and stockout_ratio < 0.10:
        return "HIGH_CONFIDENCE"
    if stockout_ratio >= 0.10:
        return "CENSORED"
    if clean_days < 14 or units_sold < 10:
        return "LOW_DATA"
    return "MEDIUM_CONFIDENCE"
```

### 6.4 Effective demand selection

```python
def choose_d_eff(observed_d, oos_adjusted_d, scenario_d, confidence, manual_override=None, scenario_cap=None):
    if manual_override and manual_override.is_active:
        return manual_override.value, "MANUAL_OVERRIDE"

    if confidence == "HIGH_CONFIDENCE":
        return observed_d, "OBSERVED"

    if confidence == "CENSORED":
        return max(observed_d, oos_adjusted_d), "OOS_ADJUSTED"

    if confidence == "MEDIUM_CONFIDENCE":
        return max(observed_d, min(oos_adjusted_d, observed_d * 1.5)), "MEDIUM_CONFIDENCE_ADJUSTED"

    if confidence == "LOW_DATA" and scenario_d is not None:
        capped = min(scenario_d, scenario_cap) if scenario_cap is not None else scenario_d
        return capped, "SCENARIO_CAPPED"

    if confidence == "NEW_TEST":
        return 0.0, "TEST_ALLOCATION_ONLY"

    if confidence == "PROMO_DISTORTED":
        return min(observed_d, scenario_d) if scenario_d is not None else observed_d, "PROMO_NORMALIZED"

    return observed_d, "DEFAULT_OBSERVED"
```

---

## 7. Size mix

### 7.1 Guardrail normalization

```python
def apply_mix_guardrails(raw_mix, min_share=0.03, max_share=0.40):
    clipped = {s: min(max(v, min_share), max_share) for s, v in raw_mix.items()}
    total = sum(clipped.values())
    if total <= 0:
        n = len(raw_mix)
        return {s: 1.0 / n for s in raw_mix}
    return {s: v / total for s, v in clipped.items()}
```

### 7.2 Suppression-aware blend

```python
def calc_anchor_weight(num_suppressed_sizes):
    if num_suppressed_sizes >= 3:
        return 0.8
    if num_suppressed_sizes == 2:
        return 0.7
    if num_suppressed_sizes == 1:
        return 0.5
    return 0.2


def blend_size_mix(observed_mix, anchor_mix, anchor_weight):
    sizes = sorted(set(observed_mix) | set(anchor_mix))
    mixed = {}
    for s in sizes:
        mixed[s] = observed_mix.get(s, 0) * (1 - anchor_weight) + anchor_mix.get(s, 0) * anchor_weight
    total = sum(mixed.values())
    return {s: v / total for s, v in mixed.items()}
```

---

## 8. Stock and inbound

### 8.1 Trusted inbound filter

```python
def is_trusted_inbound(row):
    return (
        row.status in {"CONFIRMED", "PAID_NOT_SHIPPED", "SHIPPED", "IN_TRANSIT"}
        and row.trusted_for_po_calc is True
        and row.qty > 0
        and not row.is_disputed
        and not row.is_received_accepted
    )
```

### 8.2 Projected arrival stock

```python
def calc_projected_arrival_stock(current_sellable, trusted_inbound_before_arrival, d_eff, days_until_arrival):
    return max(0, current_sellable + trusted_inbound_before_arrival - d_eff * days_until_arrival)
```

Rules:

- Do not calculate PO using current stock alone.
- Do not count draft POs as inbound.
- Do not count already-received inbound as inbound; it must be in stock ledger.

---

## 9. Safety stock

```python
import math


def calc_safety_stock_size(d_size, sigma_size, effective_l, buffer_days, z_factor, tv_mix, mix_risk_multiplier):
    ss_demand = z_factor * sigma_size * math.sqrt(effective_l)
    ss_floor = d_size * buffer_days
    ss_mix = tv_mix * d_size * effective_l * mix_risk_multiplier
    return max(ss_demand, ss_floor) + ss_mix
```

Default `sigma_size` fallback:

```python
sigma_size = d_size * sigma_factor
```

But once enough data exists, compute sigma from daily sales variance.

---

## 10. ROP, target, and raw order quantity

```python
def calc_rop(d_size, effective_l, ss_size):
    return d_size * effective_l + ss_size


def calc_target_after_arrival(d_size, r_eff, ss_size):
    # Lead-time demand is already handled by projected arrival stock.
    return d_size * r_eff + ss_size


def calc_raw_order_qty(target_after_arrival, projected_arrival_stock):
    return max(0, math.ceil(target_after_arrival - projected_arrival_stock))
```

---

## 11. Status logic

```python
def calc_status(current_sellable, inventory_position, rop):
    if inventory_position < rop:
        return "REORDER"
    if current_sellable < rop and inventory_position >= rop:
        return "WAIT_INBOUND"
    return "OK"
```

At SKU/color level:

```python
def aggregate_status(size_statuses, core_sizes=None):
    statuses = [size_statuses[s] for s in (core_sizes or size_statuses.keys())]
    if "REORDER" in statuses:
        return "REORDER"
    if "WAIT_INBOUND" in statuses:
        return "WAIT_INBOUND"
    return "OK"
```

---

## 12. New/test allocation

New/test variants do not use formula replenishment until they have proof.

```python
def cap_new_test_qty(requested_qty, total_po_qty, per_variant_cap_pct=0.05):
    cap = math.floor(total_po_qty * per_variant_cap_pct)
    return min(requested_qty, cap)
```

Combined cap:

```python
def validate_combined_new_test_cap(new_test_qty_total, total_po_qty, combined_cap_pct=0.15):
    return new_test_qty_total <= total_po_qty * combined_cap_pct
```

Capital cap:

```python
def validate_new_test_capital(new_test_capital, deployed_po_capital, cap_pct=0.20):
    return new_test_capital <= deployed_po_capital * cap_pct
```

---

## 13. Capital and ROIC

```python
def calc_capital_views(d_eff, r_eff, effective_l, ss_total, cogs_unit, paid_fraction_in_pipeline=1.0):
    min_onhand = ss_total * cogs_unit
    avg_onhand = (ss_total + d_eff * r_eff / 2) * cogs_unit
    peak_onhand = (ss_total + d_eff * r_eff) * cogs_unit
    avg_pipeline = d_eff * effective_l * paid_fraction_in_pipeline * cogs_unit
    avg_paid_inventory = avg_onhand + avg_pipeline
    peak_paid_inventory = peak_onhand + avg_pipeline
    return {
        "min_onhand_capital": min_onhand,
        "avg_onhand_capital": avg_onhand,
        "peak_onhand_capital": peak_onhand,
        "avg_pipeline_capital": avg_pipeline,
        "avg_paid_inventory_capital": avg_paid_inventory,
        "peak_paid_inventory_capital": peak_paid_inventory,
    }


def calc_monthly_roic(unit_profit_after_ads, d_eff, avg_paid_inventory_capital):
    monthly_profit = unit_profit_after_ads * d_eff * 30
    if avg_paid_inventory_capital <= 0:
        return None
    return monthly_profit / avg_paid_inventory_capital


def apply_roic_gate(monthly_roic):
    if monthly_roic is None:
        return "BLOCK_AUTO_ORDER"
    if monthly_roic >= 0.20:
        return "ORDER_FULL"
    if monthly_roic >= 0.10:
        return "ORDER_WITH_FLAG"
    return "REVIEW_REQUIRED"
```

---

## 14. Matched-set logic

For a 3-piece set:

```python
def calc_sellable_set_qty(component_qty_by_type):
    return min(component_qty_by_type.values())
```

For LINE31:

```python
required_components = ["JACKET", "BRA", "LEGGINGS"]
matching_key = ["set_id", "color_mapping", "size_code"]
```

Validation:

```python
def validate_same_size_set(parts):
    sizes = {p.size_code for p in parts}
    return len(sizes) == 1
```

PO construction must not count a set unless all required components exist in the same size.

---

## 15. Supplier stock constraint

When buying in-stock goods from a supplier, final PO quantity is constrained by supplier stock.

```python
def apply_supplier_stock_cap(requested_qty, supplier_confirmed_qty):
    return min(requested_qty, supplier_confirmed_qty)
```

For matched sets:

```python
supplier_set_qty = min(
    supplier_jacket_qty_size,
    supplier_bra_qty_size,
    supplier_leggings_qty_size,
)
```

---

## 16. Rounding and pack multiples

Default rounding:

```python
final_qty = ceil(raw_qty)
```

If supplier requires pack multiple:

```python
final_qty = ceil(raw_qty / pack_multiple) * pack_multiple
```

But pack rounding must not violate:

- capital cap,
- new/test cap,
- set feasibility,
- size discontinuation flags.

---

## 17. Future PO calendar

Future POs are review checkpoints.

```python
future_po_qty = None
recalc_required = True
auto_issue = False
```

A future PO quantity becomes valid only after the full algorithm reruns with fresh:

- sales,
- stock,
- inbound,
- supplier stock,
- channel economics,
- capital state.

---

## 18. Packaging / labels as PO modifiers

If packaging is neutral stock packaging:

```text
no change to garment unit price unless supplier quotes packaging cost
```

If custom packaging, wash label, or hang tag is requested:

```text
reclassify from stock order to custom/production-impact order unless supplier confirms no MOQ/lead-time/cost impact
```

Required output fields:

```text
packaging_type
packaging_cost_per_unit
packaging_moq
packaging_lead_time_days
label_change_required
label_change_cost
label_change_lead_time_days
```

---

## 19. Validation gates

An implementation is not complete unless these pass.

### 19.1 Data gates

```text
[ ] stock snapshot exists and has timestamp
[ ] inbound source exists and marks trusted vs draft
[ ] sales history exists or demand override is documented
[ ] channel economics are valid
[ ] COGS inputs are complete
```

### 19.2 Calculation gates

```text
[ ] Observed_D, OOS_Adjusted_D, Scenario_D, D_eff are visible separately
[ ] D_eff_source is visible
[ ] projected arrival stock is used
[ ] SS is calculated at size grain where size matters
[ ] ROP and status are calculated per size
[ ] future PO rows are review checkpoints only
```

### 19.3 Capital gates

```text
[ ] Avg_OnHand_Capital is visible
[ ] Avg_Paid_Inventory_Capital is visible
[ ] ROIC gate uses paid inventory capital when inventory is prepaid
[ ] new/test capital cap is checked
```

### 19.4 Set gates

```text
[ ] set component quantities are validated
[ ] strict same-size rule is applied for matched-size sets
[ ] final set quantity is capped by weakest component
```

### 19.5 Supplier gates

```text
[ ] supplier stock by size is confirmed before payment
[ ] packaging photos / label state are confirmed when relevant
[ ] dispatch timing is confirmed
[ ] payment route is confirmed
```

---

## 20. Workbook-specific minimum implementation

Any Excel workbook implementing v3 must include or emulate these surfaces:

```text
Inputs
Demand_Model
Stock_Projection
Inbound_Truth
Size_Safety_Stock
PO_Calc
Capital_Model
Set_Feasibility
Validation
Rule_Efficiency_Review
```

If workbook limitations prevent full formula implementation, the workbook must still display:

```text
what is calculated
what is manual
what is scenario
what is missing
what blocks decision-grade use
```

---

## 21. Done criteria

A PO output is decision-grade only if:

```text
validation_status = PASS
inventory_rules_version = 9.0
po_logic_version = 3.0
D_eff_source is visible
Projected_Arrival_Stock is used
Trusted_Inbound is included
Set feasibility passes
Capital gate passes or human override exists
Supplier stock confirmation is attached for in-stock buys
```
