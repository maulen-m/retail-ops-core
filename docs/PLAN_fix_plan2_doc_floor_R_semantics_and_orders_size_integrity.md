# PLAN — Fix PLAN‑2 DoC floor, plan‑chain R/T_POST semantics, and orders size integrity

**Doc name (copy into repo):** `docs/PLAN_fix_plan2_doc_floor_R_semantics_and_orders_size_integrity.md`

**Owner:** Agent (worktree)  
**Related:** TASK‑308/309 (plan‑2 DoC + size integrity), dashboard correctness hardening  
**Cutoff (current evidence):** stock + sales cutoff **2026‑01‑17**, 90‑day window start **2025‑10‑19** (see artifacts README). 

---

## 0. Why this matters (the “physics”)

We are using a periodic‑review style PO engine:

- Demand rate **D** (units/day) + safety stock **SS_total** (units) define a safety buffer **SS_days = SS_total / D**.
- A plan PO recommends an order quantity that should leave enough inventory **after the PO arrives** to cover the next cycle + safety.
- Multi‑plan chain (PLAN‑1 → PLAN‑2 → …) is meant to answer: **“If I execute PLAN‑1, what will the next plan recommend, given lead times + blackout?”**

If the chain is correct:

- PLAN‑2 pre‑arrival DoC should **not fall below** SS_days (floor). It may be **above** SS_days (e.g., overlapping lead times, low demand, or conservative policy), but it must never be below for the SKUs/scopes we promise.

If the UI and backend disagree on dates/stock math, we lose trust and can over‑order (capital risk) or under‑order (stockout risk).

---

## 0.1 What’s already done vs still open

### Done (from TASK‑308/309 work)
- Backend plan‑chain tracer + evidence exports for key SKUs.
- Backend invariant script enforcing a CL‑only DoC floor (green in CI when run).
- Orders size integrity tooling: audit script + guarded fix script + DB backup script.
- Snapshot test alignment to “morning snapshot” semantics.

### Still open (causing today’s confusion / risk)
- Dashboard UI still recalculates dates/consumption/targets in JS, ignoring blackout + stock‑at‑message; this creates drift between UI numbers and backend/tracer.
- PLAN‑1 “effective_R_sku” override uses **message_date → next arrival** as R, which can massively inflate targets and units (capital risk).
- Size corruption must be fully remediated for all affected windows (11:53 is the main one in evidence), and ingestion must prevent re‑pollution.

---

## 1. What we see (symptoms)

### 1.1 Conflicting PLAN‑2 DoC values
- Debug trace / backend exports show **PLAN‑2 pre‑arrival DoC for LINE52 ≈ 70 days** (well above floor).
- Dashboard UI screenshots show **PLAN‑2 pre‑arrival DoC for LINE52 ≈ 13.9 days** (below floor SS_days ≈ 21 days).

### 1.2 PLAN‑1 ordering blow‑up (capital risk)
- In newer exports, PLAN‑1 recommends ~**11.6k units** total (LINE52 alone ~4.3k), vs earlier runs ~**4.0k units**.
- This jump is large enough that we must treat it as a regression until proven correct.

### 1.3 Orders size integrity corruption
A large set of orders around **2026‑01‑18 ~11:53** have **assigned_size = "L"** even though sales/my_size indicates different sizes.

Evidence already generated:
- `orders_size_mismatch_by_updated_timestamp.csv`
- `orders_size_mismatches_2026-01-18_1153_window.csv`
- `orders_listed_ids_size_comparison.csv`

(Adil downloaded these into `~/Docs/Oracle/Autonomous_business/2026-01-18/plan_2`.)

---

## 2. Root causes (confirmed by reading the exported dashboard HTML)

### RC‑1: UI recomputes core PO math and overrides backend (drift)
The dashboard JS recomputes, per SKU:
- `po_send_date`, `est_arr_date`, `days_until_arrival` using **message_date + prep + L**
- `consumption_until_arrival` using that recomputed lead time
- `target` and `po_qty_total` based on (possibly) recomputed inputs

This recompute:
- **Ignores blackout‑adjusted dates** used by backend.
- **Does not use stock_at_message_date**, so PLAN‑2 projections can drift badly.

Result: UI numbers (13.9 / 22.7) can disagree with backend exports/tracer.

### RC‑2: PLAN‑1 backend target uses an incorrect “R” proxy (over‑ordering)
In `scripts/generate_po_dashboard_data.py` (per oracle pack), PLAN‑1 overrides target as:

- Derive `ss_total = base_target − (D * R_default)`
- Set `effective_R_sku = (PLAN‑2 arrival − PLAN‑1 message_date)`
- Set `target = (D * effective_R_sku) + ss_total`

This makes **target (and order qty)** scale with *message → next arrival* rather than a periodic‑review cycle. For high‑D SKUs (LINE52), it can explode units and tie up capital.

### RC‑3: Orders table polluted by CRM/waybill testing
Manual testing inserted fake sizes into CRM, then those sizes were ingested into `fact_orders_kaspi` (and possibly other operational tables). This causes day‑complete failures and undermines size‑level demand/ops reporting.

---

## 3. Goals (what “done” means)

### G1 — Single source of truth: backend math
- Dashboard HTML must **render backend fields** for:
  - send/arrival dates
  - days_until_arrival
  - consumption_until_arrival
  - stock_at_message_date (new field)
  - pre_arrival, pre_arr_doc
  - target, po_qty_total
- UI must not silently recompute different values.

### G2 — Correct PLAN‑1 target policy (no capital blow‑up)
- Remove/replace the PLAN‑1 target override that uses `(next_arrival − current_message_date)`.
- Enforce PLAN‑2 DoC floor **without** multiplying PLAN‑1 horizon into 60–90 day targets for high‑D SKUs.

### G3 — Orders size integrity restored (ops safety)
- All orders in the corrupted windows (starting with 2026‑01‑18 11:53) have assigned_size corrected (or explicitly marked UNKNOWN) and day‑complete gates pass without `--skip-day-complete`.

### G4 — Recordkeeping
- Add/update phases + tasks in `.claude/GOALS.md` and `.claude/TASKS.md` (append‑only).

---

## 4. Proposed solution (structured)

### 4.1 Fix the dashboard drift: remove JS recomputation

**Approach (preferred):** backend‑only math.

1. In `scripts/generate_po_dashboard_data.py`, add explicit fields needed for display:
   - `stock_at_msg` (units) — simulated on‑hand at plan message date
   - `ss_total` and `ss_days` (derived)
   - `effective_L` (days) — blackout‑adjusted message→arrival
   - (optional) `arrival_gap_days` between this plan’s arrival and next plan’s arrival

2. In `scripts/generate_po_dashboard_html.py` (or embedded JS):
   - Stop recomputing send/arrival/lead time/consumption/target/order.
   - Treat JS as a renderer only.

**If “interactive multiplier” must remain:**
- Make it *explicitly* a local what‑if mode and label it as such.
- But still compute it using backend’s `stock_at_msg` and blackout‑adjusted `effective_L` to avoid nonsense.

### 4.2 Replace PLAN‑1 target override with a minimal DoC‑floor top‑up

We want PLAN‑2 pre‑arrival stock to be at least `ss_total`.

**Policy:**
- Keep **base target** for PLAN‑1 equal to the standard engine target (from PLAN‑0 params; i.e., `base_target`).
- Compute PLAN‑1 base order qty from that target.
- If PLAN‑2 pre‑arrival stock (assuming PLAN‑1 executed) is < `ss_total`, add **only the extra units required** to meet the floor.

Concretely (high‑level):

1. Compute ss_total from base target:
   - `ss_total = base_target − D * R_default`

2. Compute PLAN‑2 pre‑arrival stock under backend semantics:
   - Use `stock_at_msg_plan2` (already computed in the planner)
   - Use the correct inbound timing buckets
   - Use consumption from msg→arr for PLAN‑2 (blackout‑aware)

3. Derive minimum extra units needed from PLAN‑1 to satisfy floor at PLAN‑2 arrival:
   - `extra_needed = max(0, ss_total − pre_arrival_plan2_base)`

4. Set:
   - `po_qty_total_plan1 = base_po_qty_total_plan1 + extra_needed`

**Critical:** This avoids redefining PLAN‑1 target as 60–90 days for high‑D SKUs.

### 4.3 Tighten invariants + tests

- Update `scripts/validate_po_dashboard_invariants.py`:
  - For CL SKUs in PLAN‑2, assert `pre_arrival >= ss_total`.
  - Add a tolerance (e.g., ±1 unit) to avoid rounding noise.
  - Emit a clear per‑SKU failure line: D, ss_total, stock_at_msg, inbound, consumption, pre_arrival.

- Add/extend unit tests (targeted, deterministic):
  - A test SKU with blackout‑shifted PLAN‑1 lead time and high D (LINE52‑like) where:
    - base target is modest
    - floor top‑up kicks in
    - PLAN‑1 order stays within expected bounds (no blow‑up)

### 4.4 Remediate orders size integrity (and prevent recurrence)

1. **Audit:** run the size integrity audit script (or reproduce if missing) for the last 90 days.
2. **Fix windows:**
   - Start with **2026‑01‑18 11:53** window.
   - Backup DB before writes.
   - Overwrite `assigned_size` only when:
     - we have a trustworthy size (sales_fact_v2.my_size, or CRM workbook), and
     - the current assigned_size is clearly corrupted (e.g., bulk identical value pattern).
3. **Evidence:** export a CSV of (order_id, old_size, new_size, source) for each window.
4. **Prevention:** ensure the waybill/testing tooling cannot mass‑overwrite operational sizes without:
   - a feature flag,
   - a log artifact,
   - and (ideally) writing into a sandbox table.

---

## 5. Step‑by‑step execution checklist (agent)

### 5.1 Worktree + branch
- Create a dedicated git worktree (mandatory parallel policy).
- Branch suggestion: `fix/plan2-doc-floor-ui-drift`.

### 5.2 Reproduce baseline + capture evidence
1. Run EOD:
   - `python3 scripts/run_end_of_day.py --verbose`
2. Export dashboard:
   - `python3 scripts/update_po_dashboard.py` (or whatever wrapper generates `exports/po_dashboard_*`)
3. For SKUs:
   - LINE52 (`CL_OC_MEN_LINE52_BLACK`)
   - `CL_NEW-CLO_MEN_T-SHIRT_White`

Capture:
- `exports/po_dashboard_data.json`
- `exports/po_dashboard.html`
- If present: `exports/plan_chain_debug_*.{csv,json}`

### 5.3 Implement backend/UI alignment (RC‑1)
- Remove the JS recomputation path and render backend values.
- Add `stock_at_msg`, `ss_total`, `ss_days`, `effective_L` to backend output.

### 5.4 Implement PLAN‑1 DoC floor top‑up (RC‑2)
- Replace PLAN‑1 target override with minimal top‑up.
- Ensure totals (units/cogs) drop back toward sane levels.

### 5.5 Fix orders sizes (RC‑3)
- Run audit, identify windows, backup DB, run fix for 11:53 window.
- Rerun EOD and confirm day‑complete passes.

### 5.6 Gates (stop at first failure)
- `python3 scripts/run_end_of_day.py --verbose`
- `python3 scripts/validate_po_dashboard_invariants.py`
- `pytest -q`
- `scripts/lint_docs.sh`
- `scripts/check_no_db_tracked.sh`

### 5.7 Recordkeeping
- Append new phase section + tasks to:
  - `.claude/GOALS.md`
  - `.claude/TASKS.md`
- Update `.claude/PROGRESS.md` + `.claude/SESSION_LOG.md` with:
  - what changed
  - what commands ran
  - where evidence is stored

### 5.8 Oracle pack
Create a new oracle pack in:
- `~/Docs/Oracle/Autonomous_business/2026-01-18/plan_2/` (Adil already prepared this folder)

Include:
- diff summary
- commands run
- key exports + audit/fix CSVs
- cutoff date

---

## 6. Acceptance criteria

- **Dashboard UI == backend exports** for LINE52 and `CL_NEW-CLO_MEN_T-SHIRT_White` across PLAN‑1/PLAN‑2.
- PLAN‑1 does **not** inflate to 60–90 day targets for high‑D SKUs.
- PLAN‑2 pre‑arrival DoC for CL SKUs is **>= SS_days** (validated by invariant script).
- Orders size mismatches for the 11:53 window are fixed (or explicitly marked) and day‑complete passes.

---

## 7. Open decision (if needed)

If the business *explicitly wants* to treat stockouts as backorders and “catch up” demand after restock, we should encode that as a **separate, capped recovery component**, not by redefining PLAN‑1’s R horizon.


---

# Readme.md
# Full‑scope artifacts (2026‑01‑18)

Cutoff date (latest snapshot in DB): **2026-01-17**
Window start (90 days): **2025-10-19**

## Orders tables
- fact_orders_kaspi: raw order rows (order‑focused, may include pre‑size assignment)
- sales_fact_v2: post‑ingest sales rows used by PO engine + ledger (sizes normalized)
- fact_sales: legacy sales table (reference)

## Inventory snapshots
- fact_inventory_snapshot_size: current_stock + inbound_stock per sku_id per day

## PO snapshots
- po_header / po_line: lifecycle + sizes for real POs
- fact_po_lines: imported PO lines with ETA/arrivals
