# Plan: Fix Size-Constrained Ordering (CL / multi-size apparel)

Date: 2026-01-17  
Owner: Agent  
Priority: NOW (capital + stockout risk)  
Scope: PO engine + dashboard outputs + exports + invariants/tests

## Problem (what we must fix)
For multi-size apparel SKUs (e.g., LINE51), the dashboard/exports sometimes produce **non-zero size orders** even when a size is already **over target / no deficit**.

Example symptom:
- Size rows show `deficit_size == 0` (or `pre_arrival >= target`), but `order_qty > 0`.
- This causes overstock in small sizes (S/M) while larger sizes remain short.

This is a correctness issue. It directly causes wrong purchase decisions (capital risk + stockout risk).

## Root cause (likely)
The engine computes **SKU-level order_qty_total** and then **splits that total across sizes** by demand weights (D_size share) and rounding.
That guarantees every size gets some allocation when the SKU total is >0 — even if a specific size has no deficit.

## Goal / Definition of Done (DoD)
For multi-size apparel (Product_Type=CL or equivalent “multi-size” classification):

### Correctness rules (must hold)
1) **Size-constrained ordering**
   - For each size `i`:
     - `pre_arrival_i = max(0, stock_i + inbound_before_arrival_i - d_size_i * days_until_arrival)`
     - `target_i = d_size_i * t_post_days`
     - `order_i = max(0, round(target_i - pre_arrival_i))`
   - AND: if `pre_arrival_i >= target_i`, then `order_i MUST == 0`.

2) **No cross-size netting**
   - Total SKU order is:
     - `order_total = Σ order_i` (sum across sizes)
   - Do NOT compute `order_total = max(0, target_total - pre_arrival_total)` for CL, because it incorrectly nets S/M overstock against XL/3XL shortages.

3) **Exports/UI truth**
   - The dashboard HTML, JSON, and XLSX exports must display the same size_orders as the backend engine.
   - No UI recomputation of size allocation.

4) **Size normalization**
   - Size codes must be canonical (e.g., `3XL`, not `3xl`, no whitespace variants).
   - Duplicate size keys for the same sku_key must not survive to planning math.

### Acceptance criteria (must pass)
- `python3 scripts/run_end_of_day.py --verbose` passes.
- `python3 scripts/validate_po_dashboard_invariants.py` passes.
- `pytest -q` passes.
- LINE51 S/M in PLAN-1: if `pre_arrival >= target`, then order is exactly **0**.
- Large sizes that are short get the required order (no more “big sizes short while S/M ordered”).

---

## Implementation plan (agent steps)

### Step 0 — Reproduce + capture before-state (evidence)
1) Run EOD/dashboard generation on the current cutoff.
2) In the dashboard JSON output, locate a known offender SKU (LINE51) and record:
   - stock/pre_arrival/target/deficit/order_qty for S and M
3) Save a short “before” snippet in a task note (or in oracle pack).

Goal: ensure we can prove the fix changed behavior intentionally, not accidentally.

---

### Step 1 — Find the actual allocation code path
Search for where `size_orders` is built for planned POs.
Typical grep targets:
- `size_orders`
- `D_size`
- `size_weights`
- `allocate`
- `largest remainder`
- `round` / `ceil` / `floor`
- any place splitting a SKU total into sizes

Key rule:
- Fix the engine where size_orders are created (core/po or allocation module), not only in dashboard rendering.

---

### Step 2 — Implement “deficit-capped size orders” for CL
Add (or refactor) a dedicated function, e.g.:

`compute_size_orders_deficit_capped(size_rows, days_until_arrival, t_post_days) -> Dict[size, int]`

Where each `size_row` contains:
- size_key (canonical)
- stock_now (size-level)
- inbound_before_arrival (size-level)
- d_size (size-level demand rate)

Algorithm:
1) Canonicalize size_key (uppercase, normalize whitespace, apply synonyms).
2) If `d_size <= 0` and there is no explicit override policy → order 0 (and log once).
3) `consumption = d_size * days_until_arrival`
4) `pre_arrival = max(0, stock_now + inbound_before_arrival - consumption)`
5) `target = d_size * t_post_days`
6) `deficit = max(0, target - pre_arrival)`
7) `order_qty = int(ceil(deficit - eps))` with a tiny eps (e.g., 1e-9) so deficit==0 never becomes 1.
8) Return per-size order dict.

Then define:
- `sku.order_qty_total = sum(order_qty_by_size.values())`

Important:
- Remove/disable any logic that “forces” at least 1 unit per size when SKU order > 0.
- If you must preserve “mix smoothing,” it must only operate **within each size’s cap**:
  - `order_qty_i <= ceil(deficit_i)` always.

---

### Step 3 — Guard rails for edge cases
Handle these explicitly:

1) **Missing size rows**
   - If a sku has CL type but only one size: treat it as ONE_SIZE (or as single-size CL).
   - If a size exists in demand weights but not in snapshot/stock tables: treat stock=0 and inbound=0, but log as completeness issue.

2) **Missing demand**
   - If `d_size` is missing for a size but the SKU is portfolio_active: this should be a completeness gate failure (not silent behavior).

3) **Inbound without size breakdown**
   - For CL SKUs: do not invent inbound per size from totals unless there is an explicit, tested rule.
   - Prefer: require inbound at size granularity for CL (or fail readiness).

4) **Rounding**
   - Default: ceil deficits to protect against stockouts.
   - If you later introduce supplier MOQ/multiples, implement them after deficit-capping.

---

### Step 4 — Update invariants + tests (this is what makes it “fully fixed”)
#### 4.1 Invariants script
Extend `scripts/validate_po_dashboard_invariants.py` with a rule:

For each CL sku_key and size row:
- If `pre_arrival >= target` OR `deficit_size == 0` → `order_qty MUST == 0`

Also enforce:
- No duplicate size keys per sku_key
- `sum(size.order_qty) == sku.po_qty_total`

#### 4.2 Unit tests
Add a deterministic test case (no DB needed) for the allocator:
- Input: LINE51-like sizes
  - S and M: pre_arrival above target
  - XL/2XL: pre_arrival below target
- Assert S/M order 0, large sizes >0, and totals match sum.

If you have golden fixtures for PO contract:
- Add a boundary fixture for a multi-size SKU where small sizes are overstock and large sizes are short.

---

### Step 5 — Re-run gates + produce evidence pack
Required commands:
- `python3 scripts/run_end_of_day.py --verbose`
- `python3 scripts/validate_po_dashboard_invariants.py`
- `pytest -q`
- `scripts/lint_docs.sh` (if docs touched)
- `scripts/check_no_db_tracked.sh`

Create an offline oracle pack that includes:
- changed source files
- before/after JSON snippets for LINE51 S/M
- test outputs + gate logs
- the dashboard artifacts (HTML + JSON) for review

---

## Files likely involved (non-exhaustive)
- core PO sizing/allocation module that builds `size_orders`
- scripts/generate_po_dashboard_data.py (should only render backend `size_orders`, not compute them)
- scripts/generate_po_dashboard_html.py (render-only)
- scripts/validate_po_dashboard_invariants.py
- tests for sizing / allocation / dashboard contract

---

## Rollback plan
If the change materially increases order quantities:
- Validate that this is expected due to removing cross-size netting.
- Use capital safety preflight limits to prevent overbuy.
- If it explodes due to missing inbound/stock rows: fix completeness gates, do not “paper over” with heuristics.

---

## Success checklist (human review)
Open the dashboard and check:
- LINE51 PLAN-1: S/M order = 0 when overstocked
- XL/2XL/3XL orders are non-zero when short
- LINE52 large sizes behave sensibly
- Totals in HTML = totals in exports
- No phantom size keys (3xl vs 3XL, whitespace variants)

End.
