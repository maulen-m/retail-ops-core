# Execution Plan — Fix Partial OOS Detection (Stock-First) + Snapshot Rebuild From PO History
**Repo:** `~/Docs/Autonomous_business`  
**Today (truth):** 2025-12-17 (Asia/Almaty) → **cutoff_date = 2025-12-16**  
**Source of truth workbook (must win vs DB if mismatch):**  
`~/Docs/Autonomous_business/excel/PO-generator_FILLED_2025-12-15_GPT_1.xlsx`

---

## 0) TL;DR Decision (highest-ROIC approach)
**Do this:**
1) Treat the “truth workbook” as the authoritative event-log for **sales + PO arrivals + current stock + anchors**.  
2) Rebuild **daily size-level stock timeline** (snapshots) from **PO history + sales + current stock** (no need for existing daily snapshots).  
3) Make Partial OOS detection **stock-first** (sales-only fallback only if stock history truly impossible).  
4) Compute demand using **availability-adjusted demand** (virtual backfill) + **anchor blending** with a smarter `w` that understands “suppressed data vs real decline”.  
5) Keep all SKUs in outputs (NO ROIC gating). ROIC is for sorting/flagging only.

**Why this is ROIC-max:**
- Under-ordering from phantom “low demand” is what kills marketplace rank and cashflow.
- The only reliable way to detect partial OOS is to know “was the size actually available?” → that means reconstructing stock timeline from PO receipts + sales.

---

## 1) Spec Gaps + Fixes (what changes vs prior spec)
| Item | Spec says | Reality (your current state) | Fix | ROIC impact |
|---|---|---|---|---|
| Daily stock snapshots exist | Use snapshot table for OOS | Repo may not have daily snapshots; DB may be stale | **Rebuild snapshots from PO history + sales + current stock** using truth workbook | Very high |
| Partial OOS detection | Mostly sales-share drift vs anchor | Sales-share drift misses true OOS and creates false “demand drop” | **Stock-first OOS** by size: if stock=0 historically → partial OOS | Very high |
| “Good days” definition | Count days; if many, trust data | Many “good days” can still be **bad data** if stock unknown or suppressed | Redefine good days: **must have coverage** (stock known OR sales>0), plus availability score | High |
| Anchor blending weight `w` | Mostly based on good_days | Current `w` can undertrust anchor when data is misleading | `w = f(confidence, availability_score, d_data/d_anchor, OOS flags)` | High |
| Anchor source | D_size_mix_reference.xlsx | You update anchors in the truth workbook sheet | Default anchor source = **truth workbook / SizeMix_and_Di_Anchor**, fallback to D_size_mix_reference.xlsx | High |
| New SKU / no history | Use anchors | Some SKUs may have missing shares | Sibling-based share fallback + global size priors | Medium |
| ROIC threshold | Filter below threshold | You explicitly want all SKUs (to catch anomalies) | **Remove filtering**. Only flag. | High |

**If any conflict exists between spec and the truth workbook → follow the workbook, log a warning, proceed.**

---

## 2) Final Algorithm (steps + formulas)

### 2.1 Time boundary (non-negotiable)
- `cutoff_date = yesterday in Asia/Almaty`
- Never use same-day sales.

### 2.2 Canonical keys
- `sku_key` = style identifier
- `sku_id` = size-level identifier (sku_key + size)
- `size` = MY_SIZE (for CL), or a synthetic `"NOSIZE"` for ELS

### 2.3 Build the “Event Log” from truth workbook (authoritative)
From the truth workbook:
- Sales events: `(date, sku_id, qty=-units_sold)` from `Fact_Sales` (Kaspi only)
- PO receipt events: `(arrival_date, sku_id, qty=+units_received)` from `Fact_PO_Lines` joined to `Dim_PO_Header` by PO id/code
- Stock-as-of event: for each sku_id, on `as_of_date=today`, stock_start = `Current_stock` (from DIM_SKU_ID if present; else allocate from sku_key total)

**Critical:** We do NOT need perfect accounting; we need a conservative “was it likely OOS?” timeline.

### 2.4 Rebuild daily stock-by-size timeline (snapshot rebuild)
Goal: `stock_start[sku_id, d]` for `d ∈ [cutoff_date - L_max, cutoff_date]`, where `L_max = 365` (cap compute).

Preferred reconstruction (robust + conservative):
1) Build `arrivals[sku_id, d] = sum(receipts on d)`
2) Build `sales[sku_id, d] = sum(units sold on d)`
3) Set `stock_start[sku_id, cutoff_date+1] = current_stock_as_of_today`  
   - If today is 2025-12-17, this is stock at start of 2025-12-17.
4) For d going backward:
   - `stock_start[sku_id, d] = max(0, stock_start[sku_id, d+1] - arrivals[sku_id, d] + sales[sku_id, d])`

Diagnostics to record per sku_id:
- `rebuild_negative_clamps_count`
- `unexplained_delta_total` (how often we had to clamp)

This produces a “best-effort” size availability history without daily snapshots.

### 2.5 Detect OOS patterns (stock-first)
Define for each day `d`:
- `in_stock_size(s, d) = (stock_start[sku_id(s), d] > stock_threshold)` where `stock_threshold = 0` (or 1 for safety)
- `in_stock_any(d) = any_s in_stock_size(s,d)`

#### Extended OOS (SKU-level)
- `extended_oos = exists run length ≥ 14 days where in_stock_any(d)==False`
- record `extended_oos_gap_start/end`

#### Partial OOS (size-level, the main fix)
For each size `s` in last `W=30` days:
- `oos_days_s = count(d where in_stock_size(s,d)==False AND in_stock_any(d)==True)`  
  (SKU had stock in other sizes, but this size was out)
- `oos_rate_s = oos_days_s / days_with_stock_coverage`

Flag size `s` as partial OOS if:
- `anchor_share_s >= 0.10` (configurable; use 0.15 for stricter)
- `oos_days_s >= 4` (or consecutive run ≥ 3)
- and at least one sibling size has `sales > 0` in same window

Sales-only fallback (only if stock timeline unavailable):
- Use the two rules from spec:
  - Rule 1: anchor_share ≥ 0.15 AND 0 sales for >3 consecutive days while siblings sell
  - Rule 2: observed_share ≤ anchor_share / 5 for >3 consecutive days

#### Intermittent OOS
- In last 30 days: `oos_days_total >= 6` OR `oos_rate_total >= 0.2`

### 2.6 Planning-safe last sale date
Compute:
- `last_sale_date_raw = max(d ≤ cutoff_date where total_sales(d) > 0)`
- `last_sale_date_valid`:
  - Scan backward from cutoff_date to find the most recent “stable in-stock regime”
  - Stable day definition:
    - if stock known: stable if `(sales>0) OR (sales=0 AND in_stock_any=True)`
    - if stock unknown: stable if `sales>0` only
  - If we detect an extended OOS gap before the current regime, set valid date to the end of the pre-gap stable regime; else raw.

### 2.7 Demand estimation (availability-adjusted + anchor blend)
Let `anchor shares p_s` exist if anchored.

Per day (eligible window last `L_demand=90` days):
- `obs_sales_instock(d) = Σ_{s where in_stock_size(s,d)} sales_s(d)`
- `available_share(d) = Σ_{s where in_stock_size(s,d)} p_s`  (if anchor exists)
  - If no anchor: `available_share(d) = (#sizes_in_stock)/(#sizes_total)` (rough)
- Daily total-demand estimate:
  - `D_hat(d) = obs_sales_instock(d) / max(available_share(d), 0.30)`
- Eligible day rule:
  - require `available_share(d) >= 0.50` (else too suppressed → skip)
  - require stock coverage OR sales>0 (avoid treating “unknown” as zero)

Compute:
- `D_data = robust_mean({D_hat(d)})`  (winsorize 10/90 or median+MAD clip)
- Optional `D_peak` (recommended):
  - Find “stable high-availability days” in last 365 days where `available_share(d) ≥ 0.90`
  - Take `D_peak = median(top 20% of D_hat(d) but excluding 1-day spikes via MAD)`
- Combine model demand:
  - `D_model = 0.7*D_data + 0.3*D_peak` (clip to sane bounds)

Anchors:
- `D_anchor` from truth workbook `SizeMix_and_Di_Anchor.D_active` (fallback to D_size_mix_reference.xlsx)

#### Anchor blending weight `w` (this is the key behavior change)
Base from data volume:
- if `good_days ≥ 60` → base `w=0.20` (NOT 0.10)
- `30–59` → `w=0.40`
- `14–29` → `w=0.60`
- `<14` → `w=0.80`

Adjustments:
- If `extended_oos` → `w = max(w, 0.80)`
- If `intermittent_oos` → `w = max(w, 0.60)`
- If partial_oos_sizes non-empty → `w = max(w, 0.60)`
- If has_anchor and `availability_score < 0.85` → `w = max(w, 0.70)`  (data likely suppressed)
- If has_anchor and `D_model / D_anchor < 0.60` AND availability_score < 0.90 → `w = max(w, 0.70)`
- If has_anchor and `D_model / D_anchor < 0.60` BUT availability_score ≥ 0.95 → do **NOT** force anchor (likely real decline/seasonality); keep w as base.

Final:
- `D_final = w*D_anchor + (1-w)*D_model`
- Safety clip:
  - `D_final ∈ [0.5*min(D_anchor,D_model), 1.5*max(D_anchor,D_model)]` unless one is 0.

### 2.8 Size share estimation (Bayesian smoothing, stock-aware)
Goal: avoid overfitting + handle missing sizes.

If anchor exists:
- Prior strength: `prior = prior_days * D_anchor` where `prior_days=30` (tunable)
- For each size:
  - `count_prior_s = prior * p_s`
  - `count_data_s = Σ sales_s(d)` over eligible days where `in_stock_size(s,d)=True`
  - `count_post_s = count_prior_s + count_data_s`
- `share_final_s = count_post_s / Σ count_post_s`
- If a size is flagged partial OOS:
  - do NOT let it collapse to 0 just because recent sales were impossible
  - the Bayesian prior keeps it alive

If no anchor:
- If siblings exist (same family), use sibling averaged share
- Else use product_type default share vector (global prior by CL vs ELS)

Always:
- renormalize so Σ share_final = 1.0

Per-size demand:
- `D_size_final[s] = D_final * share_final_s`

---

## 3) Validation + Metrics (acceptance tests)
### 3.1 “Must pass” acceptance checks
1) **Cutoff correctness**
   - cutoff_date printed and equals yesterday Asia/Almaty.
2) **All SKUs included**
   - dashboard/export includes all sku_keys from truth workbook’s SKU universe (no top-N).
3) **Stock-aware partial OOS**
   - a known partial-OOS SKU shows partial_oos_sizes non-empty.
4) **No “missing stock treated as 0 demand”**
   - if stock coverage missing, zero-sales days are excluded from good_days (not counted as demand=0).
5) **Excel match (baseline sanity)**
   - LINE52_BLACK and LINE51_WHITE:
     - D_final close to Excel expectation OR explainable by availability_score logic.
6) **Size share sanity**
   - Σ share_final = 1.0 ± 0.001
   - share_final does not zero out meaningful anchor sizes just because they were OOS.

### 3.2 Diagnostics outputs (required)
Write:
- `exports/demand_diagnostics.csv` (1 row per sku_key)
- `exports/stock_rebuild_diagnostics.csv` (1 row per sku_id)
- Include reasons/warnings if:
  - anchor missing
  - PO header missing arrival dates (fallback used)
  - rebuild had frequent clamps/unexplained deltas

---

## 4) Implementation Roadmap (phases, owners, I/O)

### Phase 0 — Reality check (Owner: Opus)
**Input:** truth workbook path  
**Tasks:**
- Confirm sheets exist:
  - Fact_Sales
  - SizeMix_and_Di_Anchor
  - DIM_SKU_ID (or alternative size stock)
  - Dim_SKU (sku_key totals)
  - Fact_PO_Lines
  - Dim_PO_Header (must include Actual_arrival_date)
- If Fact_PO_Lines / Dim_PO_Header missing:
  - fallback to `Inventory_Core_V17.1_PO.xlsx` for PO lines AND approximate arrival_date = ship_date + L_days (log warning)

**Done when:** Opus writes a short mapping table: sheet → columns used.

### Phase 1 — Truth workbook ingestion (Owner: Opus)
**Create:** `scripts/sync_truth_workbook_to_db.py` (even if DB is stale)  
**Goal:** DB becomes reproducible from workbook.

**Outputs to DB (minimum):**
- sales_daily_size (or sales_fact_v2) from Fact_Sales
- dim_sku_id size stock from DIM_SKU_ID
- anchors table (or in-memory) from SizeMix_and_Di_Anchor
- po_receipts events from Fact_PO_Lines + Dim_PO_Header

**Done when:** running the script produces a “sync summary” with row counts and max dates.

### Phase 2 — Stock timeline rebuild (Owner: Opus)
**Create:** `core/calc/stock_timeline.py`
- `rebuild_stock_timeline(sku_ids, start, end, as_of_date, current_stock, sales, arrivals) -> stock_start_by_day`

Cache result:
- Option A (fastest): in-memory cache during a run
- Option B (better): write a DB table `fact_inventory_rebuilt_daily_size(snapshot_date, sku_id, stock_start)`

**Done when:** you can query stock_start for any sku_id in last 365 days.

### Phase 3 — DemandEstimator changes (Owner: Opus)
**Modify:** `core/calc/demand_estimator.py`
- Replace partial OOS detection with stock-first rules
- Redefine good_days to exclude “unknown stock + zero sales”
- Implement availability-adjusted D_hat(d) + D_data + D_peak
- Implement updated w logic (availability-aware, not just good_days)
- Implement Bayesian size-share smoothing

**Done when:** `exports/demand_diagnostics.csv` shows:
- availability_score, good_days, oos_flags, partial_oos_sizes, w, D_final, shares

### Phase 4 — Wire into PO generator + dashboard (Owner: Opus)
**Modify:** `scripts/generate_po_dashboard_data.py`
- Ensure SKU enumeration comes from truth universe (or dim tables) with no hidden limits
- Ensure NO ROIC gating (only flag/sort)
- Use D_final + share_final from estimator

**Done when:** dashboard json lists all SKUs; demand_diagnostics generated.

### Phase 5 — Regression tests (Owner: Opus)
**Add:** `tests/test_demand_estimator_oos.py`
Cases:
- partial OOS (size unavailable but siblings sell)
- extended OOS (14+ day gap)
- intermittent OOS
- new SKU (<14 days)
- no anchor (warning path)

**Done when:** tests pass and match sanity ranges.

---

## 5) Definition of DONE (project-level)
- Running:
  - `python scripts/sync_truth_workbook_to_db.py`
  - `python scripts/generate_po_dashboard_data.py`
produces:
- `exports/po_dashboard_data.json`
- `exports/demand_diagnostics.csv`
- `exports/stock_rebuild_diagnostics.csv`
…and partial OOS behavior is stock-first + explainable, with no SKU silently dropped.
