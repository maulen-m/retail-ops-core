Demand Estimator + Size-Mix + Dashboard — ROIC‑First Execution Plan (Opus)

1. TL;DR decision (recommended approach)

Build a single “DemandEstimator” source of truth that outputs per‑SKU:

cutoff_date = yesterday in Asia/Almaty (always, no hardcoding)

Demand_Estimator_Opus_Spec

last_sale_date_raw + planning‑safe last_sale_date_valid (stable in‑stock regime end)

Demand_Estimator_Opus_Spec

D_final = confidence‑weighted blend of D_anchor (from D_size_mix_reference.xlsx) and D_model (OOS‑denoised data estimate)

Demand_Estimator_Opus_Spec

size_share_final = blend of size_share_anchor and size_share_data, with partial‑OOS-aware renormalization

Demand_Estimator_Opus_Spec

Then wire this estimator into both:

the PO generator / size_allocation engine, replacing the current “OOS-filtered average” as the primary D source; and

the dashboard data generator, ensuring it outputs all eligible sku_keys (no silent dropping) and writes a diagnostics CSV.

This is the highest‑ROIC approach because it:

prevents under-ordering during OOS (lost sales) and over-ordering from noisy spikes (capital lock-up),

forces stable, explainable demand numbers (auditable diagnostics),

eliminates today/incomplete data risk by using a fixed “yesterday” cutoff.

2. Spec gaps + fixes (table)
   Item	Spec says	Reality (files)	Fix	Why (1 line)	ROIC impact
   Cutoff date	Always “yesterday Asia/Almaty”

Demand_Estimator_Opus_Spec

```
Dashboard JSON currently uses sales_data_cutoff=2025-12-03 
```

Autonomous_Business_Optimal_14_…

```
Hard‑set cutoff_date = yesterday(Asia/Almaty) everywhere; also emit sales_db_max_date warning if stale	Prevents partial-day distortion + removes brittle hardcodes	High
```

Dashboard SKU coverage	“All active SKUs from DB”

Demand_Estimator_Opus_Spec

```
JSON summary shows total_skus=3 
```

Autonomous_Business_Optimal_14_…

```
Add skipped_skus[] with reason + ensure selection uses dim_sku_size WHERE active_flag=1 (no hidden limits) 
```

Demand_Estimator_Opus_Spec

```
Eliminates silent drop → you can trust the dashboard list	High
```

Inventory column names	Spec stock query uses stock_qty

Demand_Estimator_Opus_Spec

```
Inventory snapshot table uses current_stock / inbound_stock 
```

Autonomous_Business_Optimal_14_…

```
Update estimator queries to use current_stock (and optionally inbound_stock)	Prevents “always zero stock” bugs → false OOS flags	High
```

Missing days behavior	Treat missing days as unknown (not zero)

Demand_Estimator_Opus_Spec

```
Query helpers currently fill missing with 0 (explicit note) 
```

Autonomous_Business_Optimal_14_…

```
Introduce a “calendar/coverage mask”: only treat missing as 0 when the day exists globally; otherwise mark None and exclude from OOS logic	Avoids false OOS + wrong D caused by ingest gaps	High
```

Partial OOS signals	Spec detects partial OOS using anchor share vs sales

Demand_Estimator_Opus_Spec

```
Stock-by-size exists (fact_inventory_snapshot_size) 
```

Autonomous_Business_Optimal_14_…

```
Priority order: use size stock (stock<=0) when available; else fallback to sales-based rules	Stock signal beats inference → fewer false positives	High
```

D spikes / promo days	Spec mentions OOS filtering but not robust anti-spike	Current demand calc can be mean-based (spike-sensitive)	Winsorize or MAD-cap daily sales before averaging for D_data	Prevents over-ordering from 1–2 abnormal days	Med‑High
Estimator integration	Spec: replace demand calc in size_allocation

Demand_Estimator_Opus_Spec

```
size_allocation currently computes OOS-filtered D from size sales/stock history 
```

Autonomous_Business_Optimal_14_…

```
Keep existing calc as fallback, but make DemandEstimator the default D + size shares	Minimizes regressions while improving ROIC stability	High
```

“All sizes OOS now”	Spec: keep anchor D, mark currently_oos

Demand_Estimator_Opus_Spec

```
System currently risks collapsing D to 0 in certain patterns	Explicitly implement “currently_oos” logic + raise anchor weight	Avoids demand permanently dying due to OOS zeros	High
```

3) Final algorithm (steps + formulas)
3.1 Inputs, data required, and assumptions

Inputs (required):

Anchor file: excel/D_size_mix_reference.xlsx with D_active, size shares, and sigma

Demand_Estimator_Opus_Spec

DB tables (minimum viable):

dim_sku_size (to enumerate sizes and active SKUs)

Autonomous_Business_Optimal_14_…

Sales at daily size granularity: fact_sales_daily_size or v2 sales_fact_v2

Autonomous_Business_Optimal_14_…

Inventory snapshots by size: fact_inventory_snapshot_size (preferred), otherwise sales-only inference fallback

Autonomous_Business_Optimal_14_…

Assumptions (explicit):

Sales history exists at sku_key × size × date via fact_sales_daily_size / sales_fact_v2.

Autonomous_Business_Optimal_14_…

Inventory snapshot history may be incomplete; estimator must tolerate missing snapshot dates (treat as unknown, not 0).

Autonomous_Business_Optimal_14_…

If a SKU is not in the anchor file, estimator runs data-only and emits warnings.

Demand_Estimator_Opus_Spec

Definition of “done” (algorithm):
For every sku_key being processed, estimator returns:

D_final > 0 unless truly no evidence and no anchor (then D_final=0 with warning),

sum(size_share_final)=1.0±0.001,

robust last_sale_date_valid and OOS flags,

a diagnostics row capturing all intermediate values.

3.2 Global time boundary

Cutoff date (non-negotiable):
cutoff_date = (now in Asia/Almaty) - 1 day

Demand_Estimator_Opus_Spec

All sales/stock windows end at cutoff_date.

3.3 Core per‑SKU data extraction (bounded windows)

Let:

L_demand = 90 days (default)

L_share = 30 days (default)

L_max = 180 days (cap for any optional deeper scan; keep ROIC high via bounded compute)

For a given sku_key:

Size universe

sizes = SELECT DISTINCT my_size FROM dim_sku_size WHERE sku_key=? ORDER BY size_order

Autonomous_Business_Optimal_14_…

Daily size sales series (preferred source)

Pull units[s][d] for each size s and each day d ∈ [cutoff-L_demand, cutoff] from fact_sales_daily_size or sales_fact_v2.

Autonomous_Business_Optimal_14_…

Daily size stock series (if available)

Pull stock[s][d] from fact_inventory_snapshot_size.current_stock

Autonomous_Business_Optimal_14_…

Build totals:

sales_total[d] = Σ_s units[s][d]

stock_total[d] = Σ_s stock[s][d] (only where stock is known)

Coverage mask (critical)
Because existing query helpers currently “fill missing with 0”

Autonomous_Business_Optimal_14_…

, the estimator must explicitly track:

day_has_sales_data[d] = true if day exists in global sales calendar (any SKU has sales rows that day)

day_has_stock_snapshot[d] = true if fact_inventory_snapshot_size has any rows for that day (global)

Then treat:

If day_has_sales_data[d]==false, sales for all SKUs that day are unknown, not 0.

If day_has_stock_snapshot[d]==false, stock for all SKUs that day is unknown, not 0.

This avoids false OOS patterns.

3.4 last_sale_date: raw vs planning‑safe

A) last_sale_date_raw

last_sale_date_raw = max { d ≤ cutoff | sales_total[d] > 0 }

Demand_Estimator_Opus_Spec

B) last_sale_date_valid (planning-safe)
Goal: the last day of the most recent stable in-stock sales regime.

Demand_Estimator_Opus_Spec

Define a day-level state (total SKU level):

If stock is known on day d:

oos_day_total(d) = (sales_total[d]==0 AND stock_total[d]==0)

stable_day(d) = (sales_total[d]>0) OR (sales_total[d]==0 AND stock_total[d]>0)

Demand_Estimator_Opus_Spec

If stock is unknown on day d:

do not mark OOS; use stable_day(d) = (sales_total[d]>0) only (otherwise unknown)

Then:

Scan backward from cutoff_date to find the most recent block of stable days.

If you detect a gap of >14 consecutive oos_day_total(d) before the current stable block, mark extended_oos.

Demand_Estimator_Opus_Spec

Set last_sale_date_valid:

If extended OOS: end of the stable block before the OOS gap.

Else: last_sale_date_raw.

3.5 OOS flags (extended / intermittent / partial)

You will emit:

oos_flags ⊆ {extended_oos, intermittent_oos, partial_oos, currently_oos}

partial_oos_sizes = [sizes...]

A) Extended OOS (total SKU)
Extended OOS = >14 consecutive days where sales=0 AND stock=0.

Demand_Estimator_Opus_Spec

Only evaluate on days where both sales and stock coverage are known.

B) Intermittent OOS (total SKU)
Count OOS days in last 30 days where sales=0 AND stock=0; if count > 5, flag intermittent_oos.

Demand_Estimator_Opus_Spec

Again: only count where stock coverage exists.

C) Partial OOS (size-level) — Per-Size Relative Drift Detection

Detect sizes that are suppressed by comparing observed share to anchor share.

Formula:
  For each size s:
    relative_drift = (anchor_share[s] - observed_share[s]) / anchor_share[s]
    IF relative_drift ≥ 0.30 (30%) → Size is SUPPRESSED

Why relative drift (not absolute):
- Scale-independent: 5% size dropping to 3.5% (30% drop) treated same as 20% dropping to 14%
- Distinguishes stockout suppression from genuine demand decrease:
  - Stockout: specific sizes drift ≥30% → trust anchor
  - Genuine decrease: all sizes stay proportional → trust d_data

Anchor weight adjustment based on suppression_count:
| Suppressed Sizes | Anchor Weight |
|------------------|---------------|
| 1 size           | w = max(w, 0.5) |
| 2 sizes          | w = max(w, 0.7) |
| 3+ sizes         | w = max(w, 0.8) |

Config param: suppression_relative_threshold = 0.30

If any sizes flagged → set partial_oos in oos_flags and return the list.

D) Currently OOS
If in the most recent N days (e.g., 7) all eligible days are OOS at total level, flag currently_oos and force higher anchor weight. This matches the spec edge case behavior.

Demand_Estimator_Opus_Spec

3.6 Demand estimation: D_data, D_anchor, D_model, w, D_final
3.6.1 D_anchor

If sku_key in anchor file:

D_anchor = anchors[sku_key]["d_active"]

Demand_Estimator_Opus_Spec

Else:

has_anchor=False, D_anchor=0, add warning.

Demand_Estimator_Opus_Spec

3.6.2 D_data (OOS-denoised data demand)

Compute a “good day” set:

Eligible days are those within [cutoff-L_demand, cutoff] with known sales coverage.

If stock coverage exists on a day:

exclude oos_day_total(d) (sales=0 AND stock=0)

include stable days (sales>0 OR stock>0)

If stock coverage doesn’t exist:

include only days with sales_total[d] > 0 (avoid treating zeros as OOS)

Then define raw estimate:

d_raw = mean( winsorize( { sales_total[d] for d in good_days } ) )

Robustness (anti-spike):
Winsorize daily sales on good days:

Cap values above p90 (or median + 3*MAD) before averaging.

Confidence + uplift (aligning to existing “confidence uplift” behavior in size allocation

Autonomous_Business_Optimal_14_…

):

good_days = |good_days|

confidence:

ACTUAL if good_days ≥ 30

MARGINAL if 14 ≤ good_days < 30

FALLBACK if 1 ≤ good_days < 14

NO_DATA if good_days = 0

Autonomous_Business_Optimal_14_…

uplift:

ACTUAL: ×1.0

MARGINAL: ×1.2

FALLBACK: ×1.5

Demand_Estimator_Opus_Spec

So:

D_data = d_raw * uplift(confidence)

3.6.3 Partial OOS correction (optional override of D_data)

If partial_oos is flagged and has_anchor is true:

Compute observed_sales_by_size[s] = average units/day for size s over eligible non-OOS days.

Estimate total demand using anchor shares by scaling up from in-stock sizes:

Demand_Estimator_Opus_Spec

in_stock_share = Σ_{s ∉ partial_oos_sizes} anchor_share[s]

in_stock_sales = Σ_{s ∉ partial_oos_sizes} observed_sales_by_size[s]

If in_stock_share ≥ 0.10: D_partial = in_stock_sales / in_stock_share

else: D_partial = Σ_s observed_sales_by_size[s]

Set D_model = max(D_data, D_partial) (conservative: don’t reduce demand because of the correction).

Else:

D_model = D_data

3.6.4 Blend weight w and D_final

Use spec’s weight rules as the baseline (simple and explainable):

Demand_Estimator_Opus_Spec

w_base from good_days:

≥60 → 0.1

≥30 → 0.3

≥14 → 0.5

<14 → 0.8

Additive OOS adjustments (cap at 0.9), per spec.

Add “deviation penalty” when |D_model - D_anchor| / D_anchor is large (per spec logic).

Additional ROIC-first improvement:
If sales DB is stale (e.g., max(sale_date) < cutoff_date - 1), increase w (trust anchors more) and emit warning. This prevents “bad data day” from driving orders.

Final:

If has_anchor:

D_final = w * D_anchor + (1 - w) * D_model

Else:

w=0, D_final = D_model and warning emitted

Demand_Estimator_Opus_Spec

Safety clip (from spec validation):

ensure: 0.5×min(D_model, D_anchor) ≤ D_final ≤ 1.5×max(D_model, D_anchor) when both exist

Demand_Estimator_Opus_Spec

3.7 Size mix: size_share_data, size_share_anchor, size_share_final
3.7.1 size_share_anchor

If anchored:

size_share_anchor[s] = anchors[sku_key]["size_share"][s]

Demand_Estimator_Opus_Spec

Else: empty dict.

3.7.2 size_share_data (OOS-aware)

Compute from last L_share days:

Let eligible share days be those with known sales coverage and where SKU is not total-OOS.

For each size s:

units_30[s] = Σ_{d in eligible_share_days} units[s][d]

share_data[s] = units_30[s] / Σ_k units_30[k] if denominator > 0; else empty.

3.7.3 size_share_final (blend + renorm)

Baseline blend:

For each size s in the union of anchor and data sizes:

share_blend[s] = w * share_anchor[s] + (1 - w) * share_data[s]

Partial OOS protection (spec idea):

For sizes in partial_oos_sizes, temporarily increase anchor weight (e.g., w_local = min(0.95, w + 0.3))

Demand_Estimator_Opus_Spec

Then renormalize:

size_share_final[s] = share_blend[s] / Σ_k share_blend[k]

Acceptance: abs(Σ size_share_final - 1.0) < 0.001

Demand_Estimator_Opus_Spec

3.8 Diagnostics output (must be emitted)

Emit one diagnostics row per sku_key (see schema below) aligned to the spec’s DemandDiagnostics concept

Demand_Estimator_Opus_Spec

and include:

intermediate values (D_data, D_anchor, w, flags),

size share strings and share error (MAE vs anchor when available),

warnings (no anchor, stale DB, no stock coverage, skipped, etc.).

4. Validation + metrics (acceptance tests)
   4.1 Acceptance tests (pass/fail)

Use this as the “go/no-go” list (expanded from spec checklist)

Demand_Estimator_Opus_Spec

:

Cutoff correctness

Pass if JSON cutoff_date == yesterday Asia/Almaty every run.

Demand_Estimator_Opus_Spec

No stale hardcodes

Pass if there is no literal 2025-12-03 cutoff logic and no literal STOCK_DATE = "YYYY-MM-DD" in generator.

All active SKUs are considered

Pass if:

generator queries SELECT COUNT(DISTINCT sku_key) FROM dim_sku_size WHERE active_flag=1

Demand_Estimator_Opus_Spec

output includes either:

that sku_key in results, or

sku_key in skipped_skus with a reason.

Anchor load

Pass if len(anchors)=43 (or =26 if filtering to CL_ only)


Demand_Estimator_Opus_Spec

If anchor file changes, pass if anchors load without errors and counts are logged.

No-anchor behavior

Pass if every SKU without anchor has has_anchor=False, w=0, warning emitted

Demand_Estimator_Opus_Spec

OOS detection

Pass if unit tests cover:

extended OOS (15+ day gap)

Demand_Estimator_Opus_Spec

partial OOS Rule 1 and Rule 2

Demand_Estimator_Opus_Spec

intermittent OOS (>5 OOS days in 30)

Demand_Estimator_Opus_Spec

Demand stability bounds

Pass if D_final obeys the clip rule when anchor and data exist

Demand_Estimator_Opus_Spec

Size shares sum to 1

Pass if for every SKU with non-empty shares: |Σ share_final - 1| < 0.001

Demand_Estimator_Opus_Spec

Dashboard row visibility

Pass if dashboard displays all rows in JSON (no implicit top‑N cap).

Demand_Estimator_Opus_Spec

ROIC is display-only (no filtering)

Pass if output includes all processed SKUs regardless of ROIC (including negative ROIC values), and there is no ROIC-based exclusion in SQL/Python.

Demand_Estimator_Opus_Spec

4.2 Metrics to compute & monitor in diagnostics

Per run, compute and log:

active_skus_count

processed_skus_count

skipped_skus_count + breakdown by reason (no sizes, invalid sizes, no stock snapshot, etc.)

skus_without_anchor_count

mean_w, median_w (if too high → data issues; if too low → ignoring anchors)

For anchored SKUs: share_mae distribution (size share fit)

5. Implementation roadmap (phases, owners, inputs/outputs)

Owner: Opus performer for all phases unless otherwise noted.
No external web. Use only repo + provided files.

Phase 0 — Reality check & constraints lock

Inputs

docs/Demand_Estimator_Opus_Spec.md

Demand_Estimator_Opus_Spec

DB: db/app.db

Anchor: excel/D_size_mix_reference.xlsx

Demand_Estimator_Opus_Spec

Current dashboard export: exports/po_dashboard_data.json (currently shows cutoff 2025‑12‑03 and 3 SKUs)

Autonomous_Business_Optimal_14_…

Tasks

Confirm anchor file columns match expectations (SKU_key, D_active, *_share, sigma)

Demand_Estimator_Opus_Spec

Confirm sales source table(s) exist: fact_sales_daily_size and/or sales_fact_v2

Autonomous_Business_Optimal_14_…

Confirm inventory snapshot table exists and columns (current_stock, inbound_stock)

Autonomous_Business_Optimal_14_…

Confirm current bug symptoms (cutoff, SKU count) match the provided JSON

Autonomous_Business_Optimal_14_…

Outputs

Short note in commit / PR description: what tables exist and any schema deviations from spec.

Phase 1 — Data boundary fixes (cutoff + coverage mask)

Files to change

core/calc/demand_estimator.py (new)

Demand_Estimator_Opus_Spec

core/db/queries.py

Demand_Estimator_Opus_Spec

scripts/generate_po_dashboard_data.py (existing in repo; refactor, don’t duplicate)

Tasks

Implement get_cutoff_date() exactly per spec (Asia/Almaty yesterday).

Demand_Estimator_Opus_Spec

Add query helpers that accept start_date/end_date or cutoff_date instead of using date.today() (many functions currently use date.today() internally)

Autonomous_Business_Optimal_14_…

Add “global sales calendar” and “global stock snapshot calendar” helpers, so missing days can be treated as unknown (not forced 0). This fixes the existing “fill missing with 0” behavior.

Autonomous_Business_Optimal_14_…

Outputs

New helper(s): get_sales_calendar(start,end), get_stock_calendar(start,end)

Unit test(s) proving missing days are handled as unknown.

Phase 2 — DemandEstimator implementation (anchors + OOS + blending + size shares)

Files

Create: core/calc/demand_estimator.py

Demand_Estimator_Opus_Spec

Tasks

Anchor loading:

_load_anchors() → {sku_key: {d_active, sigma, size_share{...}}}

Demand_Estimator_Opus_Spec

Data retrieval methods:

daily sales total, daily stock total, size daily sales, size daily stock (using correct columns current_stock)

Autonomous_Business_Optimal_14_…

OOS detection:

extended/intermittent using sales+stock where coverage exists

Demand_Estimator_Opus_Spec

partial OOS using stock‑first else sales+anchor rules

Demand_Estimator_Opus_Spec

last_sale_date_raw / last_sale_date_valid

Demand_Estimator_Opus_Spec

Demand computation:

D_data with OOS filtering + confidence uplift

Demand_Estimator_Opus_Spec

partial‑OOS scaling using in-stock share math

Demand_Estimator_Opus_Spec

w and D_final blending per spec

Demand_Estimator_Opus_Spec

Size share blending + renorm

Demand_Estimator_Opus_Spec

Diagnostics row generation matching the spec schema idea

Demand_Estimator_Opus_Spec

Outputs

Working DemandEstimator.get_demand(sku_key, cutoff=...) -> DemandResult

Unit tests for scenarios: clean, extended OOS, partial OOS, intermittent, new SKU, no anchor

Demand_Estimator_Opus_Spec

Phase 3 — Integrate estimator into PO generator / size allocation

Files

Modify: core/calc/size_allocation.py

Demand_Estimator_Opus_Spec

Tasks

Add use_estimator=True path that:

calls DemandEstimator.get_demand(sku_key) to get D_final and size_share_final

sets d_sku = D_final

sets per-size demand as d_size[s] = D_final * size_share_final[s]

retains old calc_d_sku_with_oos_filter() as fallback for no anchor + low data scenarios

Autonomous_Business_Optimal_14_…

Outputs

Integration test: generates PO draft for an anchored SKU and verifies non-zero demand and confidence.

Demand_Estimator_Opus_Spec

Phase 4 — Refactor dashboard data generator to use estimator + output diagnostics

Files

Modify (existing): scripts/generate_po_dashboard_data.py

Ensure outputs:

exports/po_dashboard_data.json

exports/demand_diagnostics.csv

Demand_Estimator_Opus_Spec

Tasks

Enumerate all active SKUs from DB:

Demand_Estimator_Opus_Spec

SELECT DISTINCT sku_key FROM dim_sku_size WHERE active_flag=1

For each SKU:

compute demand via estimator

compute PO metrics (existing logic) using D_final and size_share_final

Do NOT apply any ROIC filter (ROIC is display/sort only; include negative ROIC).

Demand_Estimator_Opus_Spec

Add skipped_skus list with reason codes (e.g., NO_SIZES, NO_STOCK_SNAPSHOT, INVALID_SIZE_CODES, NO_SALES_COVERAGE, etc.)

Write diagnostics CSV (one row per SKU) with intermediate fields.

Outputs

JSON has correct cutoff_date (yesterday) and SKU counts increase beyond the current 3-SKU artifact

Autonomous_Business_Optimal_14_…

Diagnostics CSV present and populated.

Phase 5 — Dashboard UI: remove any implicit top‑N cap and show freshness

Files

PO_Dashboard.html (or po_dashboard.html depending on repo usage)

Demand_Estimator_Opus_Spec

Tasks

Ensure UI renders all rows in sku_level (no .slice(0,8) or similar).

Display cutoff_date prominently (“Data through YYYY‑MM‑DD”).

If skipped_skus_count > 0, show a small warning badge and link to diagnostics CSV path.

Outputs

Manual check: open HTML, confirm row count equals JSON sku_level.length and no missing SKUs due to UI.

Phase 6 — End-to-end validation and signoff

Inputs

Fresh run outputs: JSON + CSV

Tasks

Run acceptance checklist in Section 4

Spot-check 3–5 anchored SKUs:

D_final close to anchor when OOS flagged

size_share_final matches anchor intuition

Spot-check 3–5 non-anchored SKUs:

warnings present

estimator behaves data-only

Outputs

Final report in PR/commit message: pass/fail list + key metrics.
