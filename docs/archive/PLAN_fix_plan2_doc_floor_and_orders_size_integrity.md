# PLAN: Fix PLAN-2 DoC floor + Orders size data integrity

**Date:** 2026-01-18  
**Owner:** Agent (Codex/Claude)  
**Scope:** Kaspi-only PO engine + PO dashboard + Kaspi orders sizing data quality  
**Priority:** P0 (capital protection + data integrity)

## Context
Two correctness issues are blocking trust in the PO/dashboard outputs:

1) **PLAN-2 coverage math drift**: In PO dashboard, PLAN-2 shows **pre-arrival DoC** below the theoretical safety floor `SS_total / D` for key SKUs (notably `LINE52` and `CL_NEW-CLO_MEN_T-SHIRT_White`) even when PLAN-2 is interpreted as “PLAN-1 executed and becomes inbound”. This indicates a broken logical chain (wrong horizon, wrong inbound inclusion, or a DoC metric computed off mismatched D/SS inputs).

2) **Orders size contamination**: `fact_orders_kaspi` contains **mass-overwritten sizes** caused by prior testing (waybill/orders assembly). Evidence shows a concentrated update window on **2026-01-18 ~11:53** where many historical orders were set to `L` with `size_source=CRM_MANUAL`. This is a data integrity breach that can leak into downstream automation.

### Evidence already generated
You can find the evidence CSVs here (already downloaded by Adil):

`~/Docs/Oracle/Autonomous_business/2026-01-18/plan_2/`
- `orders_size_mismatch_by_updated_timestamp.csv`
- `orders_size_mismatches_2026-01-18_1153_window.csv`
- `orders_listed_ids_size_comparison.csv`

**Cutoff date:** latest DB snapshot = **2026-01-17**  
**90-day window start:** **2025-10-19**

---

## Hard constraints (do not violate)
- **Formulas/params source of truth:** `docs/inventory/Master_Inventory_Rules_v8.md`.
- **No “vibes math”:** every numeric claim must be reproducible (exact command/SQL + exported CSV/JSON in `exports/`).
- **Capital safety:** do not change ordering math without a failing test/invariant that proves the bug.
- **Idempotency:** any DB write script must support `--dry-run` and be safe to re-run.
- **Stop at first failing gate** and log per protocol.

---

## Definitions (must be written down in code/docs)
Before changing logic, lock the meaning of these dashboard fields:

- **PLAN-1:** recommended PO if placed “now”.
- **PLAN-2:** projection of the *next* cycle **assuming PLAN-1 is executed** (i.e., treated as future inbound) OR explicitly document if it is *not*.
- **pre_arrival_stock (plan N):** projected on-hand stock *right before* plan N arrival (after expected consumption, plus any inbound arriving earlier).
- **pre_arrival_doc (plan N):** `pre_arrival_stock / D` using the **same D** that generated `SS_total`.

If the current dashboard definition differs, fix the naming/labeling and add a disclaimer. Don’t keep ambiguous fields.

---

## Goal / Definition of Done

### DoD-A (PLAN-2 math correctness)
For SKUs with `D > 0`:
- When PLAN-(N+1) is computed under the assumption “PLAN-N executed”, the dashboard must satisfy:
  - `pre_arrival_doc_(N+1) >= (SS_total / D) - tolerance`
  - tolerance default: **0.25 days** (rounding + integer qty)
- Verified on:
  - `LINE52`
  - `CL_NEW-CLO_MEN_T-SHIRT_White`
  - +20 random SKUs with non-zero demand
- Add an invariant so this never regresses.

### DoD-B (Orders size integrity)
- Identify the full **corruption window(s)** (by `updated_at`) and impacted order_ids.
- Restore `fact_orders_kaspi.assigned_size` for impacted orders from a trustworthy source:
  - Primary: CRM canonical sheet (e.g., `SALES_KSP_CRM_V3.xlsx`) if available.
  - Fallback: `sales_fact_v2.my_size` for orders already shipped/delivered (historical correction).
- Add an automated audit + gate:
  - Detect mass size overwrites (many rows updated in a short interval).
  - Detect suspicious “all same size” days.
  - Produce `exports/orders_size_audit_<date>.csv` and fail the pipeline when severe.

---

## Execution plan

### Phase G18.1 — Reproduce PLAN-2 bug with a deterministic tracer
**Objective:** eliminate guesswork by dumping intermediate variables for a SKU across plan steps.

1) Add a debug utility (prefer script, not notebook):
   - `scripts/debug_po_plan_chain.py --sku-key LINE52 --plan PLAN-2 --as-of 2026-01-17`
   - Output: `exports/plan_chain_debug_<sku_key>_<as_of>.json` (+ CSV if useful)

2) The tracer must include at minimum (per plan):
   - `D`, `SS_total`, `Effective_L`, `R_days`
   - plan send date, plan arrival date, `days_until_arrival`
   - `current_stock`, `inbound_real_qty`, `inbound_plan_qty`
   - `consumption_until_arrival`, `pre_arrival_stock`, `pre_arrival_doc`
   - `t_post`, `target_stock`, `order_qty`

3) Reproduce for:
   - `LINE52`
   - `CL_NEW-CLO_MEN_T-SHIRT_White`

**Deliverable:** tracer outputs in `exports/` + one short oracle-pack note explaining how to run it.

---

### Phase G18.2 — Fix PLAN-2 pre-arrival DoC floor mismatch
**Primary suspected failure modes (test each, don’t guess):**

- **Inbound inclusion bug:** PLAN-1 quantities are treated as inbound for PLAN-2 in some fields but not in the stock projection.
- **Horizon bug:** `days_until_arrival` uses the wrong date (send vs arrival, or PLAN-2 uses PLAN-1 arrival instead of its own).
- **Double-consumption bug:** consumption is subtracted twice (once in pre-arrival stock and again in DoC).
- **Mismatch of D inputs:** DoC uses `D_forecast` while SS_total uses `D_30`, or mixes SKU-level vs size-level.

**Work area (likely files):**
- `scripts/generate_po_dashboard_data.py`
- any plan-chain builder/helpers
- `core/calc/inventory.py` or `core/calc/size_allocation.py` (if plan math lives there)

**Implementation requirement:**
- Make PLAN-2 computations an explicit step-by-step simulation:
  - Build a timeline of inbound events (REAL POs + optional PLAN POs), each with arrival date.
  - Project stock at each plan arrival via: `stock_at_arrival = max(0, stock_now + inbound_arriving_before - D * days_until_arrival)`.
  - Compute DoC from the projected stock using the same D.

**Add/extend invariant:**
- Update `scripts/validate_po_dashboard_invariants.py` to include the DoC floor check (DoD-A).

---

### Phase G19.1 — Audit orders sizes corruption (expand from existing evidence)

1) Create/extend a script:
   - `scripts/audit_orders_size_integrity.py --since 2025-10-19 --until 2026-01-17`

2) Output tables in `exports/`:
   - `orders_size_mismatch_by_updated_at.csv` (counts grouped by updated timestamp)
   - `orders_size_mismatch_by_day.csv` (top-size share per day per store)
   - `orders_size_mismatch_samples.csv` (example order_ids + before/after)

3) Use `sales_fact_v2` as the comparison truth for size (it is what PO engine uses). Document this explicitly.

**Deliverable:** audit outputs + updated oracle pack note.

---

### Phase G19.2 — Remediate corrupted sizes safely

**Rule:** remediation must be reversible.

1) Add a fix script with dry-run first:
   - `scripts/fix_orders_assigned_sizes.py --window "2026-01-18 11:53:00" "2026-01-18 11:54:00" --dry-run`

2) Fix strategy (choose safest available):

- **Preferred (CRM overwrite):** if Adil provides canonical CRM file, update from that.
- **Fallback (sales_fact_v2 backfill):** for orders with `kaspi_status in {DELIVERY, COMPLETED, ARCHIVE}` (or equivalent) set:
  - `assigned_size = sales_fact_v2.my_size`
  - `size_source = FIXED_FROM_SALES_V2`
  - `size_confidence = HIGH`
  - only for rows in the corruption window(s)

3) Add a write guard:
- Any script that writes to `fact_orders_kaspi` must require BOTH:
  - `--apply` flag
  - env var `ENABLE_ORDER_WRITE=1`

---

## Verification gates (must all pass)
Run in this order; stop at first failure:

1) `python3 scripts/run_end_of_day.py --verbose`
2) `python3 scripts/validate_po_dashboard_invariants.py` (must include new PLAN-2 invariant)
3) `pytest -q`
4) `scripts/lint_docs.sh` (if docs changed)
5) `scripts/check_no_db_tracked.sh`

**Evidence required:** copy gate logs + the generated `exports/*` artifacts into the Oracle subfolder for this task.

---

## Recordkeeping requirements (.claude)
Agent must append (not replace) and keep history:

- `.claude/GOALS.md`
  - Add **G18**: PLAN-2 DoC floor + plan-chain tracer + invariant
  - Add **G19**: Orders sizes integrity audit + remediation + write guard

- `.claude/TASKS.md`
  - Create two tasks (use next available IDs):
    - `TASK-308` (or next): plan-chain tracer + PLAN-2 invariant
    - `TASK-309` (or next): orders size audit + remediation + pipeline gate

- `.claude/SESSION_LOG.md` and/or `.claude/PROGRESS.md`
  - Log what was run, what failed, what evidence was produced.

---

## Rollback plan
- Before applying any DB changes: take a DB backup (`scripts/backup_db.py` or equivalent) and store it in the Oracle folder.
- Fix scripts should support `--replace` or produce a reverse patch (CSV of prior values) so rollback is deterministic.
