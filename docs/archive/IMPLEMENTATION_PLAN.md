# IMPLEMENTATION_PLAN.md
# Demand Estimation Fix Plan (Stop 50% Under-Orders)

## Context / Why this exists
The PO dashboard automation failed because **demand (D) is severely underestimated**, producing ~50% under-orders and stockouts. We attempted ingesting new demand data, partial-OOS detection, and anchor blending — but the estimator still suppresses demand.

**Decision:** Pause dashboard automation; continue manual PO computation until demand is fixed.

This plan is focused on **fixing demand estimation** so that automated POs become safe again.

---

## Objectives (Business KPIs)
1. **Stockout prevention:** D must not be systematically suppressed for multi-store SKUs.
2. **Capital efficiency:** D should not be inflated by noisy data; confidence must track data quality.
3. **Operational trust:** outputs must be explainable (diagnostics per SKU), and deterministic with tests.

---

## Scope
### In-scope (must fix)
- Demand estimator logic (D_data, D_anchor, blending, confidence/coverage)
- Sales aggregation across stores/channels
- Partial-OOS filtering behavior under sparse/unknown stock history
- Query correctness (date fields, table choice)
- Diagnostics + tests that prove we stopped the under-order failure mode

### Out-of-scope (do later)
- Model C PO splitting / prep capacity scheduling
- Size allocation reconciliation (Fix Package A) — separate track
- Pricing / unit economics truth (separate track)

---

## Root Causes to Fix (Observed Failure Modes)
1. **Multi-store suppression:** demand computed for only one store_code (e.g., `UNIVERSAL`) rather than aggregating all relevant stores.
2. **Anchor blending bug:** when sales data is missing/zero, the blend returns `D_anchor * w` (scales anchors down) instead of falling back to anchor.
3. **Unknown-stock days treated like valid “0 demand” days:** sparse inventory snapshot history makes “0 sales” look like “0 demand,” diluting D and inflating confidence.
4. **Query drift / incorrect date field usage:** some v2 queries use a date column that may not exist or isn’t the intended one, leading to silent zero-sales reads.
5. **Split sources for SKU demand vs size mix:** different tables/queries used for SKU-level demand and size-level shares create inconsistencies and drift.

---

## Deliverables
1. **Correct demand estimator**:
   - Aggregates across stores (default)
   - Correct anchor fallback
   - Coverage logic that excludes unknown-stock days from denominators
2. **Demand diagnostics export** (CSV/JSON) showing explainability per SKU
3. **Regression tests** preventing reintroduction of under-order failure modes
4. **Operator toggle / config**:
   - store aggregation mode
   - conservative handling when stock history is sparse

---

## Workstreams (Phased Execution)

### Phase 0 — Baseline + Guardrails (0.5 day)
**Goal:** make the bug measurable and stop regressions.

**Tasks**
- Add/confirm an “audit harness” script (or extend existing diagnostics) that outputs, per SKU:
  - `d_data`, `d_anchor`, `w`, `d_final`
  - sales coverage days, unknown-stock days, oos days (if detectable)
  - stores included + store-level sales totals
  - flags: `sparse_stock_history`, `missing_sales_data`, `anchor_only_mode`
- Pick a small **golden SKU set** for regression:
  - 5 SKUs known to sell across multiple stores
  - 5 SKUs that are anchor-driven (newish, low sales)
  - 5 SKUs that are frequently OOS historically

**Acceptance**
- Running diagnostics is deterministic and produces a single file artifact under `exports/` (or similar).
- For each SKU, you can answer “why is D what it is?” from the file.

---

### Phase 1 — Fix Multi-Store Aggregation (0.5–1.5 days) **BLOCKER**
**Goal:** eliminate systematic underestimation caused by using only one store_code.

**Tasks**
- Update estimator entrypoint(s) so demand is computed using:
  - **Default: ALL stores** (or ALL Kaspi stores) aggregated
  - Optional: a store filter list (for debugging)
- Update queries to support aggregation:
  - `GROUP BY sku_key, sale_date` across all store_code
  - or union/store-level totals then sum
- Ensure the dashboard generator calls the estimator in the new default mode.

**Acceptance**
- For multi-store SKUs, `D_final(all_stores) >= D_final(UNIVERSAL)` by meaningful margins.
- Store-level totals appear in diagnostics (`store_sales_90d` or similar).

---

### Phase 2 — Fix Anchor Blending Fallback (1–3 hours) **BLOCKER**
**Goal:** anchors should not be scaled down when sales data is missing.

**Current bad behavior**
When `d_data <= 0` (or sales missing), blend returns `d_anchor * w` ⇒ anchor suppressed.

**Fix**
Implement blending as:
- If `d_data` is missing/invalid: `d_final = d_anchor` (anchor-only)
- If `d_anchor` is missing: `d_final = d_data`
- Else: `d_final = (1-w)*d_data + w*d_anchor`

Also ensure `w` is bounded and meaningful:
- `w=1` when `coverage_low` or `unknown_stock_high`
- `w` decreases as data becomes reliable

**Acceptance**
- When there is no valid sales signal, `d_final == d_anchor` (within float tolerance), not smaller.

---

### Phase 3 — Fix Coverage + Unknown Stock Handling (0.5–2 days) **BLOCKER**
**Goal:** prevent demand dilution by excluding days where stock status is unknown.

**Principle**
Demand is only learnable on days where the SKU was likely available.
- If stock is known `>0`: day is valid
- If stock is known `=0`: day is OOS (exclude from demand denominator)
- If stock is unknown: **do NOT** treat as valid “0 demand”; mark as unknown and reduce confidence

**Implementation Options**
Start with the simplest robust version:

**A) Conservative availability mask**
- `valid_day = (sales>0) OR (stock_snapshot_exists AND stock_qty>0)`
- `oos_day = (stock_snapshot_exists AND stock_qty==0)`
- `unknown_day = (sales==0 AND no_stock_snapshot)`
- Demand rate computed over `valid_day` only.

**B) Optional enhancement (later)**
- Short “stock carry-forward” window using last known stock snapshot (e.g., 3–7 days) only if there is no contradictory evidence.

**Acceptance**
- If stock snapshots are sparse, diagnostics shows:
  - `unknown_day_count` high
  - confidence reduced (w shifts toward anchors)
  - D_data does NOT collapse purely because unknown days exist

---

### Phase 4 — Fix Query Correctness + Single Source for Sales (2–6 hours)
**Goal:** stop silent “zero rows” problems and drift between v1/v2.

**Tasks**
- Verify the real schema fields used by `sales_fact_v2` and align queries to the correct date column.
- Standardize on one source for:
  - SKU-level daily sales over lookback
  - size-level sales mix over lookback
- If you must keep two sources, implement a reconciliation check:
  - `abs(sum(size_sales) - sku_sales) / sku_sales < tolerance` for SKUs with size data

**Acceptance**
- A known selling SKU never returns “0 rows” due to query field mismatch.
- Size mix totals reconcile to SKU totals in diagnostics.

---

### Phase 5 — Integration into Dashboard Pipeline (0.5–1 day)
**Goal:** ensure dashboard uses fixed estimator and exposes debugging.

**Tasks**
- Ensure dashboard generator uses the corrected estimator mode (all stores, fixed blending, new coverage).
- Add debug metadata to dashboard JSON:
  - estimator version/hash
  - store aggregation mode
  - coverage stats
  - `d_data`, `d_anchor`, `w`, `d_final`
- Add “Show diagnostics” toggle in UI later (optional); for now just ensure data exists in JSON.

**Acceptance**
- Dashboard JSON shows the demand decomposition columns; no silent defaulting.

---

## Testing Plan (Must-have)
### Unit tests
- `test_blend_anchor_fallback_when_no_sales()`
- `test_all_store_aggregation_increases_or_equals_single_store()`
- `test_unknown_stock_days_excluded_from_valid_denominator()`

### Integration tests (golden SKUs)
- For each golden multi-store SKU:
  - `D_allstores >= 1.3 * D_universal` (threshold set from observed gap; tune as needed)
- For anchor-only SKUs:
  - `D_final == D_anchor` when coverage low
- For sparse stock history SKUs:
  - confidence shifts toward anchor (w high) and D does not collapse to near zero.

---

## Rollout / Safety
- Keep manual PO generation as the operational fallback until:
  1) All tests pass
  2) Diagnostics show sane D for top 20 revenue SKUs
  3) A/B compare one cycle of manual vs dashboard D for a sample set
- Add a “hard stop” guardrail in automation:
  - If `D_final < 0.6 * D_anchor` for a SKU with a trusted anchor and low coverage → flag for review (do not auto-order)

---

## Owners (Multi-agent)
- **Claude Captain (architecture/design):**
  - Confirm store aggregation policy + availability mask definition
  - Approve blending rules + confidence design
- **Claude Code Performer (implementation):**
  - Implement code changes + tests + diagnostics
- **Human (approvals/ops):**
  - Confirm list of store_codes to include
  - Ensure daily stock snapshot ingestion is running reliably (or approve backfill approach)

---

## Definition of Done
- Demand estimates no longer show systematic ~50% under-orders for multi-store SKUs.
- Anchor-only SKUs do not get anchors scaled down.
- Unknown stock days do not dilute demand.
- Diagnostics make the demand number explainable.
- Tests enforce these behaviors.
