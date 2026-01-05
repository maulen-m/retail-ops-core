# plan.md — Demand & PO System: Reality Check + Fix Plan (as of 2025-12-21)

## 0) Ground Truth (Non‑Negotiable)
**Context:** Today is **2025-12-21**, *day start before today’s Kaspi shipping*.

### Stock snapshot semantics
- **Archive_stock_date:** 2025-12-17 (morning stock **before** 12/17 shipping)
- **Sold_since_archive_date:** sales shipped **2025-12-17 → 2025-12-20**
- **Current_stock_date:** 2025-12-21 (morning stock **before** 12/21 shipping)

**Important invariant (for sanity checks):**  
`Stock_start(2025-12-21) ≈ Stock_start(2025-12-17) - Σsales(12/17..12/20) + Σreceipts(12/17..12/20)`  
(Any big deltas indicate missing receipts, adjustments, or bad mappings.)

### Excel: what is truth vs. not truth
**Single-truth sheets (OK to ingest/use as inputs):**
- `Dim_Params`
- `Dim_Params_PT` *(if conflicts → Master_Inventory_Rules_v8.md wins)*
- `DIM_SKU_ID`
- `Dim_SKU`
- `SizeMix_and_Di_Anchor`
- `Fact_Sales`
- `Fact_PO_Lines`
- `Dim_PO_Header`

**Explicitly NOT truth (ignore results):**
- `PO_calendar`, `PO_Generator` (formatting examples only; values wrong)
- Any “view” or calculated summary tabs unless explicitly listed above.

### Existing PO already placed
- `Line52_PO-9` placed 2025-12-19; supplier sends to China cargo until 2025-12-25  
→ must be treated as **existing pipeline/inbound** in future PO scheduling.

### New business constraint: Supplier shutdown
- **Chinese New Year period:** 2026-02-01 → 2026-02-20
- **Supplier cannot prepare or send POs:** **2026-01-27 → 2026-02-20 (inclusive)**  
→ PO ETA / prep / ship calculations must respect this blackout window.

---

## 1) Quick Reality Check: suspicious or risky recent changes (revert candidates)

### A) `scripts/generate_po_dashboard_data.py` — persist_demand_estimates() mapping bug
**Problem:** when persisting to `fact_demand_estimates`, the script writes:
- `eligible_days = result.good_days` (but `good_days` = *valid days*, not days actually used in estimation)
- It should be `eligible_days = result.eligible_days`.

**Why it matters:** future Auto‑PO integration will incorrectly think there was enough coverage, leading to over-trust or mis-weighting.

**Action:** Performer → patch mapping + add a tiny sanity assertion (eligible_days <= good_days).

### B) `db/schema.sql` — `fact_demand_estimates.partial_oos_days` type mismatch
**Problem:** schema defines `partial_oos_days INTEGER`, but code serializes a dict as `"S:5,M:2"` string.

**Why it matters:** integration will be brittle; downstream SQL may break or silently mis-handle.

**Action:** Captain decides storage format:
- **Option 1 (recommended):** `partial_oos_days_json TEXT` storing JSON
- **Option 2:** `partial_oos_days_text TEXT` storing `"size:days"` pairs
Then Performer updates schema + persist logic + any reads.

### C) Tests claimed in agent summary are not visible in the repo pack
Agent summary references `tests/test_demand_estimator_oos.py` etc, but current repo snapshot contains only ad-hoc test scripts under `scripts/`.

**Action:** Performer → confirm whether tests exist locally; if not, create:
- `tests/test_demand_estimator_stock_timeline.py`
- `tests/test_demand_estimates_persistence.py`
Minimal but critical.

### D) Operating mode ambiguity (end-of-day vs morning)
Stock timeline rebuild is safe **only if the stock anchor date is “morning before shipping” and sales for that same day are not yet in DB**.
If you run at 20:30 *after shipping* with the same-day sales loaded, you must anchor on **tomorrow stock** (simulated or snapped).

**Action:** Captain → define two explicit modes:
- `MODE=morning_pre_ship` (cutoff=yesterday, anchor=today snapshot)
- `MODE=end_of_day` (cutoff=today, anchor=tomorrow simulated from today snapshot + today sales)

---

## 2) What actually works right now (vs paper)

### Working (can be used immediately)
1. **DemandEstimator is integrated into the PO dashboard generator**
   - `scripts/generate_po_dashboard_data.py` runs DemandEstimator, exports:
     - `exports/demand_diagnostics.csv`
     - `exports/po_dashboard_data.json`
   - It also builds a stock timeline (stock-first partial OOS logic is active).

2. **Scheduling scaffold exists**
   - `scripts/run_end_of_day.py` orchestrates steps
   - LaunchAgent plist exists (`config/com.inventory.endofday.plist`)

### “Looks good on paper” but not yet real
1. **Auto‑PO engine still uses legacy demand (m.d30)**
   - `core/automation/po_generator.py` reads `fact_sku_metrics.d30`
   - It does **not** LEFT JOIN `fact_demand_estimates.d_final` yet

2. **Excel “Inventory_Core_V18.xlsx” is not yet the default sync target**
   - `scripts/sync_truth_workbook_to_db.py` is hardcoded to an old workbook path.
   - `scripts/run_end_of_day.py` runs `sync_crm_to_db.py` (CRM), not Inventory_Core.

3. **Chinese New Year blackout not implemented anywhere**
   - ETA & PO scheduling will be wrong for late Jan / Feb 2026 unless patched.

---

## 3) Implementation Plan (agent-executable)

### Phase 1 — Make Inventory_Core the canonical sync source (unblocks everything)
**Owner:** Claude Captain (design) → Claude Code Performer (implementation) → Human (approval)

**Goal:** one command ingests the 8 “truth sheets” and updates DB deterministically.

**Tasks (Performer)**
1. Update `scripts/sync_truth_workbook_to_db.py`
   - Accept `--workbook /path/to/Inventory_Core_V18.xlsx` (default to your known path)
   - Remove hardcoded `PO-generator_FILLED_...xlsx` references
   - Ensure sheet mapping uses only the approved truth sheets.
2. Stock snapshots:
   - Ingest **Current_stock** from `DIM_SKU_ID` as `fact_inventory_snapshot_size`
   - Snapshot date should be a single date (use the unique `Stock_date` in sheet; if missing, allow `--snapshot-date` override)
3. Ingest PO history:
   - `Fact_PO_Lines` + `Dim_PO_Header` → `fact_po_lines` with status + arrival dates
4. Ingest anchors:
   - `SizeMix_and_Di_Anchor` → `dim_anchor` (already exists; just verify)

**Acceptance checks (Human runs)**
- SQL: max sales date exists and is recent
- SQL: snapshot_date equals expected (Current_stock_date)
- Re-run dashboard generator; confirm `demand_diagnostics.csv` exports cleanly

---

### Phase 2 — Fix demand persistence correctness (small, high ROIC)
**Owner:** Performer

**Tasks**
1. Fix `persist_demand_estimates()` mapping:
   - `eligible_days = result.eligible_days`
   - `oos_days = result.oos_days_total` (confirm semantics)
2. Fix schema mismatch:
   - Change `partial_oos_days` column to TEXT (or add `partial_oos_days_json`)
   - Write a migration strategy (SQLite): create new column + backfill + keep old column for 1 version.
3. Add a “persistence round-trip” smoke test script:
   - generate → persist → SELECT back → validate row counts and key fields

**Acceptance**
- `SELECT COUNT(*) FROM fact_demand_estimates WHERE cutoff_date = ?` matches estimated SKUs
- eligible_days <= good_days for all rows

---

### Phase 3 — Demand correctness audit on real SKUs (stop 50% under-orders)
**Owner:** Captain (audit design) + Performer (scripts)

**Tasks**
1. Add a report: `scripts/report_demand_regressions.py`
   - For each SKU: compare `{d_anchor, d_data, d_model, d_final}`
   - Flag suspicious underestimates: `d_final < 0.7 * d_anchor` when availability_score < 0.9
2. Add “top offenders” table export (CSV) for manual review.
3. For the top 10 offenders, print:
   - eligible_days, stock_known_days, unknown_days, oos_days, partial_oos_sizes
   - last 14 days of stock timeline per size (sample)

**Acceptance**
- You can explain (with printed evidence) why each offender is low (real decline) or fix logic if suppression.

---

### Phase 4 — Chinese New Year blackout support (PO-4/5/6 must be recalculated)
**Owner:** Captain (design) → Performer (implementation)

**Tasks (Captain)**
1. Decide representation:
   - Hardcode one blackout range in config for now (fastest), or
   - Add `dim_blackout_calendar` table for future holiday windows.

**Tasks (Performer)**
1. Implement blackout-aware date arithmetic in `core/po/eta.py` (or a new helper module):
   - `add_working_days(date, work_days, blackout_ranges)`
   - If prep overlaps blackout, push ship date forward.
2. Update PO scheduling logic in dashboard generator (where it builds PO-4/5/6 timelines):
   - When computing prep days + ship/arrival dates, apply blackout
3. Add a small deterministic test:
   - A PO with message_date 2026-01-25 and prep_days 10 should ship **after 2026-02-21**.

**Acceptance**
- PO-4/PO-5/PO-6 outputs show shifted ship/arrival dates that skip 2026-01-27..2026-02-20.
- No negative/overlapping windows.

---

### Phase 5 — Wire Demand into Auto‑PO (optional, but required to unpause automation)
**Owner:** Performer (implementation) + Human (approval)

**Tasks**
1. Update `core/automation/po_generator.py`:
   - LEFT JOIN latest `fact_demand_estimates` on (sku_key, cutoff_date)
   - Prefer `d_final` over `m.d30`
   - If no estimate: fallback to `m.d30` and flag
2. Keep ROIC as a flag only (no silent filtering), unless Human approves gating.

**Acceptance**
- Running Auto‑PO produces same SKU set as dashboard (no silent skips)
- For SKUs with demand estimate, quantities match dashboard totals within rounding.

---

## 4) Scheduling: what to run at 20:30+ (viable path)

### Option A (safe, recommended): End-of-day sync only
At 20:30:
1. Sync sales + PO updates + anchors
2. (Optional) forward-simulate to create **tomorrow snapshot** and store it in DB  
Then next morning demand/PO uses cutoff=yesterday and snapshot=today cleanly.

### Option B (aggressive): End-of-day sync + demand/PO generation
Requires defining `MODE=end_of_day` and using cutoff=today, and anchor snapshot=tomorrow (simulated).
Do this only after Phase 1–2 are stable.

---

## 5) Deliverables (definition of done)
- Inventory_Core is the default sync source (one command)
- Demand diagnostics explain and prevent under-orders
- `fact_demand_estimates` is correct and usable by Auto‑PO
- PO schedule accounts for Chinese New Year blackout (PO‑4/5/6 recalculated)
