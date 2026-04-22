# Master Inventory Rules v8.0 (Kaspi-only)

**Effective date:** 2026-01-01
**Last updated:** 2026-01-05
**Scope:** Kaspi (Kazakhstan) inventory + PO decision logic
**Implementation reference:**   Project 3 (Python/DB)

---

## 0. Purpose & “single source of truth” rule

This document is the **authoritative formula + parameter contract** for:
- Demand estimation inputs (D, σ)
- Safety stock (SS), Reorder point (ROP)
- Suggested order quantity & status logic
- Unit economics (COGS, Net revenue, Unit profit)
- Capital deployment gates (ROIC + new-SKU capital cap)
- Kaspi delivery fee lookup rules (effective 2026-01-01)

**Rule:** If any other document, Excel sheet, or code disagrees with this doc, this doc wins.
Exception: if the Excel workbook is treated as validation target, then update Excel + this doc together (never silently diverge).

---

## 1. Key identifiers

| Key | Definition | Example |
|---|---|---|
| `SKU_key` | Style-level product path (no size) | `CL_OC_MEN_LINE51_WHITE` |
| `SKU_ID` | Size-level identifier | `CL_OC_MEN_LINE52_BLACK_XL` |
| `OrderID` | Kaspi order number | `407785789` |
| `Kaspi_Offer_name` | Listing title | `Комплект …` |
| `MY_SIZE` | Normalized size label | `S, M, L, XL, 2XL, 3XL` / kids `22…34` |
| `Product_Type` | Category used for parameter overrides | `CL`, `ELS`, `FUR` |
| `Channel` | Platform | Always `Kaspi` |
| `Delivery_type` | Kaspi delivery program | `city`, `kazakhstan`, `express` |

### 1.1 Product_Type definitions

| Code | Meaning | Status | Notes |
|---|---|---|---|
| `CL` | Clothes | Active | Main business |
| `ELS` | Electronics | Active (risky) | Higher uncertainty; no size-mix logic |
| `FUR` | Furniture | Not active | Placeholder |

---

## 2. Current FX rates & logistics costs

> Stored in `Dim_Params` (DB) and mirrored in Excel parameters. Values are updated manually when FX/cargo changes.

| Parameter | Value | Notes |
|---|---:|---|
| `FX_USD_KZT` | 520 | Cargo payments |
| `FX_CNY_KZT` | 75 | Supplier payments |

### 2.1 Cargo rates (China → Astana)

| Product_Type | Rate (USD/kg) | Notes |
|---|---:|---|
| `CL` | 2.66 | |
| `ELS` | 2.26 | |
| `FUR` | 1.76 | |

---

## 3. Kaspi unit economics (effective 2026-01-01)

### 3.1 Platform parameters

| Parameter | Value | Notes |
|---|---:|---|
| `Commission` | 0.125 | Kaspi commission (12.5%) |
| `VAT_rate` | 0.04 | 4% |

### 3.2 Kaspi delivery fee structure (V16 / 2026 rules)

**Two regimes:**
- **Low-ticket:** `Sell_price_kzt ≤ 10,000` → price-banded fee (weight ignored)
- **High-ticket:** `Sell_price_kzt > 10,000` → weight-banded fee

#### 3.2.1 Matrix view

##### Orders ≤10,000 KZT (Price-based, weight-independent)

| Order Value (KZT) | Fee City | Fee Kazakhstan | Fee Express |
|---|---:|---:|---:|
| 0 – 1,000 | 49.14 | 49.14 | 49.14 |
| 1,001 – 3,000 | 149.14 | 149.14 | 149.14 |
| 3,001 – 5,000 | 199.14 | 199.14 | 199.14 |
| 5,001 – 10,000 | 699.14 | 799.14 | 799.14 |

##### Orders >10,000 KZT (Weight-based)

| Weight (kg) | Fee City | Fee Kazakhstan | Fee Express |
|---|---:|---:|---:|
| 0 – 5 | 1,099.14 | 1,299.14 | 1,699.14 |
| 5 – 15 | 1,349.14 | 1,699.14 | 1,849.14 |
| 15 – 30 | 2,299.14 | 3,599.14 | 3,149.14 |
| 30 – 60 | 2,899.14 | 5,649.14 | 3,599.14 |
| 60 – 100 | 4,149.14 | 8,549.14 | 5,599.14 |
| >100 | 6,449.14 | 11,999.14 | 8,449.14 |

#### 3.2.2 `Dim_Delivery_Fees` lookup table (for Excel/Python)

Columns: `Order_Value_Min`, `Order_Value_Max`, `Weight_Min_kg`, `Weight_Max_kg`, `Fee_City`, `Fee_Kazakhstan`, `Fee_Express`

| Order_Value_Min | Order_Value_Max | Weight_Min_kg | Weight_Max_kg | Fee_City | Fee_Kazakhstan | Fee_Express |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1000 | 0 | 999 | 49.14 | 49.14 | 49.14 |
| 1000 | 3000 | 0 | 999 | 149.14 | 149.14 | 149.14 |
| 3000 | 5000 | 0 | 999 | 199.14 | 199.14 | 199.14 |
| 5000 | 10000 | 0 | 999 | 699.14 | 799.14 | 799.14 |
| 10000 | 999999 | 0 | 5 | 1099.14 | 1299.14 | 1699.14 |
| 10000 | 999999 | 5 | 15 | 1349.14 | 1699.14 | 1849.14 |
| 10000 | 999999 | 15 | 30 | 2299.14 | 3599.14 | 3149.14 |
| 10000 | 999999 | 30 | 60 | 2899.14 | 5649.14 | 3599.14 |
| 10000 | 999999 | 60 | 100 | 4149.14 | 8549.14 | 5599.14 |
| 10000 | 999999 | 100 | 9999 | 6449.14 | 11999.14 | 8449.14 |

#### 3.2.3 Excel lookup formula

Assuming:
- lookup table is `Dim_Delivery_Fees` with columns A:G (as above)
- `Price` in `B10`
- `Weight_kg` in `C10`

```excel
=SUMPRODUCT(
 (Dim_Delivery_Fees!$A$2:$A$11<=B10)*
 (Dim_Delivery_Fees!$B$2:$B$11>=B10)*
 (Dim_Delivery_Fees!$C$2:$C$11<=C10)*
 (Dim_Delivery_Fees!$D$2:$D$11>=C10)*
 Dim_Delivery_Fees!$E$2:$E$11
)
```

- For Kazakhstan delivery use column **F** instead of E
- For Express delivery use column **G** instead of E

#### 3.2.4 Python function (reference)

```python
def get_kaspi_delivery_fee(price: float, weight_kg: float, delivery_type: str = "city") -> float:
    fee_idx = {"city": 0, "kazakhstan": 1, "express": 2}[delivery_type]

    # Orders ≤10,000 KZT: price-based
    if price <= 1000:
        return [49.14, 49.14, 49.14][fee_idx]
    elif price <= 3000:
        return [149.14, 149.14, 149.14][fee_idx]
    elif price <= 5000:
        return [199.14, 199.14, 199.14][fee_idx]
    elif price <= 10000:
        return [699.14, 799.14, 799.14][fee_idx]

    # Orders >10,000 KZT: weight-based
    if weight_kg <= 5:
        return [1099.14, 1299.14, 1699.14][fee_idx]
    elif weight_kg <= 15:
        return [1349.14, 1699.14, 1849.14][fee_idx]
    elif weight_kg <= 30:
        return [2299.14, 3599.14, 3149.14][fee_idx]
    elif weight_kg <= 60:
        return [2899.14, 5649.14, 3599.14][fee_idx]
    elif weight_kg <= 100:
        return [4149.14, 8549.14, 5599.14][fee_idx]
    else:
        return [6449.14, 11999.14, 8449.14][fee_idx]
```

### 3.3 Unit economics formulas

**Inputs per SKU:**
- `BaseCost_CNY` (from SKU master)
- `Weight_kg` (from SKU master)
- `Sell_price_kzt` (from sales or planned price)
- `Delivery_fee` (from `Dim_Delivery_Fees` lookup)
- `Ads_cost/day_KZT` (from `Dim_SKU` lookup)
- `Ads_cost/unit`

```text
COGS_unit     = BaseCost_CNY * FX_CNY_KZT + Weight_kg * CargoRate_USDkg(Product_Type) * FX_USD_KZT
Net_rev_unit  = (Sell_price_kzt * (1 - Commission) - Delivery_fee) * (1 - VAT_rate) - Ads_cost/unit
Unit_profit   = Net_rev_unit - COGS_unit
```

**COGS integrity rule (non-negotiable):**
- A sales line is **COGS-valid** only when full landed inputs exist:
  `BaseCost_CNY`, `Weight_kg`, `FX_CNY_KZT`, `FX_USD_KZT`, `CargoRate_USDkg`.
- If any input is missing, mark row as `unresolved` and block profit publication for that row.
- Partial/base-only COGS must not be published as final profit input.

---

## 4. Safety stock policy parameters

### 4.1 Global defaults (master-owned)

| Param | Value | Notes |
|---|---:|---|
| `L_days` | 21 | Base lead time (China → Astana) |
| `R_days` | 10 | Review period |
| `B_days` | 14 | Buffer floor (days) |
| `z_factor` | 1.65 | ~95% service level |
| `TV_mix_floor` | 0.23 | Size-mix volatility floor |
| `σ_factor` | 0.4 | `σ = D_30 × 0.4` |

### 4.2 ROIC gates & capital allocation

#### 4.2.1 Approval thresholds

| Monthly ROIC | Decision | Action |
|---:|---|---|
| **≥ 20%** | `ORDER_FULL` | Auto-approve |
| **10–20%** | `ORDER_WITH_FLAG` | Approve with monitoring flag |
| **< 10%** | `REVIEW_REQUIRED` | Human decision required |

#### 4.2.2 Capital allocation when constrained

When available capital < Σ `K_avg` for all `ORDER_FULL` items:

1. Rank eligible SKUs by ROIC (high → low)
2. Allocate capital in rank order until exhausted
3. Apply tail-smoothing capped at **15%** of total capital to avoid a cliff cutoff.

### 4.3 New item capital limit (capital protection)

| Param | Value | Rule |
|---|---:|---|
| `Max_new_SKU_capital_pct` | 20% | No **new** SKU_key may consume >20% of deployed capital |

### 4.4 Size-mix guardrails (CL only)

| Param | Value | Purpose |
|---|---:|---|
| `Size_mix_floor` | 3% | Minimum allocation per size |
| `Size_mix_cap` | 40% | Maximum allocation per size |

### 4.5 Prep days system (RESTORED)

Prep days represent supplier preparation time before shipping.
**Critical:** prep is calculated **per supplier batch**, not per individual SKU.

#### 4.5.1 Prep formulas

| Product_Type | Prep days | Formula |
|---|---|---|
| `CL` | Shared | `ceil(1.3 × Total_CL_Weight_kg / 100)` |
| `ELS` | Constant | `1` |
| `FUR` | TBD | Not active |

#### 4.5.2 Default model (capacity-capped)

```text
Model_B (worst case):      prep_B = ceil(1.3 × weight_kg / 100)
Model_C (capacity-capped): prep   = min(prep_B, R_days)    ← DEFAULT
```

#### 4.5.3 Effective lead time

```text
Effective_L = L_days + prep_days

CL:  Effective_L = 21 + Prep_CL_batch
ELS: Effective_L = 21 + 1 = 22
```

**Usage requirement:** All SS/ROP/coverage calculations that reference lead time MUST use `Effective_L` (not raw `L_days`).

### 4.6 New SKU risk factors (renumbered)

Reduce order quantities for SKUs with limited sales history.

| History | Factor | Effective order |
|---|---:|---|
| **0 days** (never sold) | **0.50** | 50% of calculated qty |
| < 30 days | 0.75 | 75% |
| 30–60 days | 0.85 | 85% |
| 60–90 days | 0.95 | 95% |
| ≥ 90 days | 1.00 | Full |

---

## 5. Core formulas

### 5.1 Demand & volatility (per SKU_key)

```text
D_30 = SUM(units_sold_last_30d) / 30
σ    = D_30 × σ_factor
```

### 5.1.1 Status flag logic (order matters)

```text
IF Total_stock < ROP            → "⚠️ REORDER"
ELSE IF Current_stock < ROP     → "📦 WAIT (inbound)"
ELSE                            → "✅ OK"
```

### 5.1.2 Partial OOS detection (size-level suppression) (RESTORED)

Goal: detect “hidden stockouts” where one or more sizes were out of stock, causing observed size shares to drift below anchor shares.

Per `SKU_key`, per size `s`:

```text
relative_drift_s = (anchor_share_s - observed_share_s) / anchor_share_s
IF relative_drift_s ≥ 0.30 → size is SUPPRESSED
```

If suppressed sizes exist, **boost `anchor_weight`** (used in demand blending logic) to counter demand underestimation:

| # suppressed sizes | anchor_weight floor |
|---:|---:|
| 1 | `max(anchor_weight, 0.5)` |
| 2 | `max(anchor_weight, 0.7)` |
| ≥3 | `max(anchor_weight, 0.8)` |

### 5.2 Safety stock components (use `Effective_L`)

```text
SS_demand = z_factor × σ × √Effective_L
SS_floor  = D_30 × B_days
SS_mix    = TV_mix_floor × D_30 × Effective_L     (CL only; 0 for ELS/FUR)
SS_total  = SS_demand + SS_floor + SS_mix
```

### 5.3 Reorder point & target coverage

```text
ROP              = D_30 × Effective_L + SS_total
T_post           = R_days + (SS_total / D_30)
Suggested_Q_base = MAX(0, T_post × D_30 - Total_stock)
Suggested_Q      = Suggested_Q_base × New_SKU_factor(history_days)
```

### 5.4 Capital & ROIC

```text
K_avg          = D_30 × (Effective_L + R_days/2) × COGS_unit + SS_total × COGS_unit
Monthly_Profit = Unit_profit × D_30 × 30
Monthly_ROIC   = Monthly_Profit / K_avg
```

---

## 6. Unit economics impact (2026 rules)

The **delivery fee matrix + VAT 4%** materially changes unit profit,
especially around the 10,000 KZT threshold. Use the V8 matrix and VAT
in all profitability checks. Historical comparisons belong in archived docs.

---

## 7. Excel workbook contract (V16)

**V16 adds:** `Dim_Delivery_Fees` sheet (delivery lookup table).
**Sheet count:** 14.

### 7.1 Table map (V16)

| Sheet | Purpose |
|---|---|
| `Dim_Params` | Global defaults |
| `Dim_Params_PT` | Product_Type overrides |
| `Dim_SKU` | SKU master |
| `Dim_Delivery_Fees` | NEW: Kaspi fee lookup |
| `Fact_Sales` | Sales transactions |
| `Fact_Sales_Daily` | Daily aggregates (derived) |
| `ABC_View` | Per-SKU operational dashboard |
| `Size_Mix_Anchor` | Anchor size shares |
| `Size_Mix_Observed` | Observed size shares |
| `Size_Allocation` | Final size-level split output |
| `PO_Dashboard` | Executive PO summary |
| `Data_Validation` | Checks / reconciliation |
| `Archive_sales` | Legacy import |
| `Notes` | Documentation |

### 7.2 Fact_Sales column structure (V16)

| Col | Header | Type | Formula notes |
|---:|---|---|---|
| A | Date | Data | order date |
| B | OrderID | Data | |
| C | Kaspi_Offer_name | Data | |
| D | SKU_key | Data | |
| E | SKU_ID | Data | |
| F | Quantity | Data | |
| G | Sell_price_kzt | Data | |
| H | Product_Type | Data | |
| I | Channel | Data | Always `Kaspi` |
| J | Delivery_fee | Calc | from `Dim_Delivery_Fees` |
| K | Net_rev_unit | Calc | `(G*(1-0.125)-J)*(1-0.04)` |
| L | Line_NetRev | Calc | `K*F` |
| M | COGS_unit | Calc | FX + cargo + cost |
| N | COGS_line | Calc | `M*F` |
| O | Profit_unit | Calc | `K-M` |
| P | Profit_line | Calc | `O*F` |

### 7.3 Fact_Sales_Daily column structure (V16)

| Col | Header | Type | Notes |
|---:|---|---|---|
| A | Date | Key | |
| B | SKU_key | Key | |
| C | Product_Type | Data | |
| D | Channel | Data | Always `Kaspi` |
| E | Units | Calc | Σ Quantity |
| F | Orders | Calc | Count of OrderID |
| G | ASP_kzt | Calc | Revenue / Units |
| H | Delivery_kzt | Calc | Σ Delivery_fee |
| I | Revenue_kzt | Calc | Σ Line_NetRev |
| J | COGS_kzt | Calc | Σ COGS_line |
| K | Profit_kzt | Calc | Σ Profit_line |

---

## 8. Validation checklist (before any freeze)

- [ ] Delivery_fee uses delivery matrix lookup (not old 3-tier IF formula)
- [ ] VAT_rate = 0.04 in all Net_rev calculations
- [ ] Sheet count = 14 (includes `Dim_Delivery_Fees`)
- [ ] Fact_Sales_Daily formulas reference correct columns
- [ ] ABC_View.Status uses 3-state logic (Total first, then Current)
- [ ] Effective_L is used anywhere lead time is referenced (SS/ROP/coverage)

---

## 9. Quick reference card (v8)

```text
Constants:
  L=21, R=10, B=14, z=1.65, TV=0.23, σ_factor=0.4
  Commission=0.125, VAT_rate=0.04

Demand:
  D = units_30d / 30
  σ = D * 0.4

Prep:
  prep_CL = min( ceil(1.3 * Total_CL_Weight_kg / 100), R )
  prep_ELS = 1
  Effective_L = L + prep_days

Safety stock (use Effective_L):
  SS_demand = z * σ * sqrt(Effective_L)
  SS_floor  = D * B
  SS_mix    = TV * D * Effective_L   (CL only)
  SS_total  = SS_demand + SS_floor + SS_mix

ROP / Order qty:
  ROP    = D * Effective_L + SS_total
  T_post = R + SS_total / D
  Q_base = max(0, T_post*D - Total_stock)
  Q      = Q_base * new_sku_factor(days_history)

Status:
  if Total_stock < ROP: REORDER
  elif Current_stock < ROP: WAIT(inbound)
  else: OK

Partial OOS (size suppression):
  drift = (anchor_share - observed_share) / anchor_share
  if drift >= 0.30 → suppressed
  if 1 suppressed: anchor_weight >= 0.5
  if 2 suppressed: anchor_weight >= 0.7
  if 3+ suppressed: anchor_weight >= 0.8

Economics:
  COGS_unit = BaseCost_CNY*FX_CNY_KZT + Weight_kg*CargoRate_USDkg*FX_USD_KZT
  Net_rev   = (Price*(1-Commission) - Delivery_fee) * (1 - VAT_rate)
  Profit    = Net_rev - COGS_unit

ROIC:
  K_avg = D*(Effective_L + R/2)*COGS + SS_total*COGS
  Monthly_ROIC = (Profit*D*30) / K_avg
```

---

## 10. Deprecations

After v8 adoption:
- Any doc still referencing legacy VAT or delivery tiers must be updated to v8.
