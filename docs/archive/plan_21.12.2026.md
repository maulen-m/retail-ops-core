# plan_21.12.2026.md — Demand Fix Hardening + CNY-2026 PO Recalc (as of 2025-12-21)

## 0) Why this plan exists
The PO dashboard automation *looked* complete, but was generating **~50% under-orders** due to bad demand (D) estimates and coverage logic.
We are now in a “stabilize + validate” phase: **make demand + blackout timing audit-grade**, then (optionally) re-enable auto-PO.

This plan assumes:
- The canonical Excel UI is: `~/Docs/Autonomous_business/excel/Inventory_Core_V18.xlsx`
- We must ignore computed tabs like `PO_calendar` and `PO_Generator` (formatting only).
- Supplier shutdown: **2026-01-27 → 2026-02-20 (inclusive)** (no prep / no sending).
- Today context: **2025-12-21 morning (before shipping)**.

---

## 1) Executive state (what Opus claims is already implemented)
From Opus’ report (commit `9dcdb40`, branch `tender-carson`):

### Implemented ✅
1) **Workbook → DB sync script**
- `scripts/sync_truth_workbook_to_db.py` parses `Inventory_Core_V18.xlsx` truth sheets and writes DB tables.

2) **DemandEstimator metadata upgrades**
- `eligible_days`, `availability_score`, `d_model` fields added (intended to reduce under-order bias and improve auditability).

3) **Persisted demand estimates**
- `scripts/generate_po_dashboard_data.py` writes estimator outputs into `fact_demand_estimates`.
- Dashboard JSON includes estimator metadata fields (d_final, weights, coverage diagnostics).

4) **CNY blackout adjustment**
- A blackout module exists and dashboard generation “adjusts” the timeline for blackout.

5) **Smoke test script**
- `scripts/smoke_test_dashboard.py` validates that the generator output is structurally sane.

### Still NOT done (explicitly listed as remaining steps) ❌
- **Auto-PO generator is not yet consuming `fact_demand_estimates.d_final`.**
  It still uses legacy `m.d30` (or equivalent), so automation is still unsafe even if the dashboard is correct.

---

## 2) Immediate red flags / “revert candidates” to verify
These are *high-risk* because they can silently produce wrong PO quantities.

### RF1 — Blackout applied to the wrong date (ETA vs ship/prep)
**Risk:** If blackout logic triggers when *arrival ETA* falls into blackout, that is likely incorrect.

**Correct mental model:** blackout blocks **supplier work + sending**, not cargo transit.
So the blackout should shift **prep_end / ship_date_cargo**, then recompute ETA as `ship_date_cargo + L`.

**Action:** Verify blackout code acts on supplier-side dates, not arrival dates.

### RF2 — Migration file exists but schema/bootstrap ignores it
If your repo doesn’t have a migration runner, a file like `db/migrations/014_...sql` may not be applied on fresh DB builds.
**Action:** ensure `schema.sql` (or bootstrap flow) is updated OR add a migration runner.

### RF3 — “order_date” vs “sale/shipping date” semantics drift
Demand + stock simulation must use the date when stock is decremented (shipping/handover).
If code switched to “order created date”, you can shift demand and break OOS detection.

**Action:** enforce a single canonical date for inventory consumption and document it in DECISIONS.md.

### RF4 — Size totals mismatch (historic bug)
Previously we saw `sum(d_size) != d_sku` (~82–83% for LINE52/LINE51).  
If still present, it breaks allocations and guarantees wrong PO splits.

**Action:** add an invariant test and block export if violated.

---

## 3) Highest-ROI goals (ranked)
These are ranked by business ROI = **stockout prevention + capital efficiency + hours saved** per unit of effort.

### Goal A (P0) — Make demand estimates trustworthy for top SKUs
**Why ROI is huge:** fixes under-orders → prevents stockouts and lost sales.

Acceptance criteria:
- For top SKUs (LINE52/LINE51 + top 10 revenue SKUs):
  - `eligible_days >= 14` OR estimator clearly flags “ANCHOR_ONLY/LOW_COVERAGE”
  - `d_final` is within a reasonable band vs. observed sales when in stock (e.g. 0.7×–1.3× of in-stock average).
  - `sum(d_size)` equals `d_sku` within rounding tolerance.

### Goal B (P0) — Blackout-aware PO timing that matches reality
**Why ROI is huge:** CNY can delay shipments by ~25 days; missing this = guaranteed stockouts.

Acceptance criteria:
- Any PO whose supplier prep/sending overlaps **2026-01-27..2026-02-20** is delayed to start/resume **2026-02-21**.
- Cargo transit (L) is not artificially delayed unless ship_date shifts.

### Goal C (P0) — Wire demand estimates into the real PO generator (or explicitly keep automation off)
**Why ROI is huge:** prevents “looks good on dashboard, wrong in automation.”

Acceptance criteria:
- `core/automation/po_generator.py` (or equivalent) LEFT JOINs latest `fact_demand_estimates` and uses `d_final`.
- Fallback to `m.d30` only when no estimate exists, with a clear flag in output.

### Goal D (P1) — One-click end-of-day run at 20:30 (after files closed)
**Why ROI is big:** saves daily manual steps and reduces operator mistakes.

Acceptance criteria:
- LaunchAgent runs at 20:30, logs to file, and is idempotent.
- If workbook is open/locked → script exits gracefully and alerts.

---

## 4) P0 Task List (what Opus should do next)

### P0-1 — “Reality check” verification (fast, mandatory)
**Owner:** Opus (Performer) + Adil (Human)

1) Confirm files exist on branch and match Opus summary
- `git show 9dcdb40 --name-status`
- Confirm paths match the report.

2) Confirm DB schema actually contains the new table
- `sqlite3 db/app.db ".schema fact_demand_estimates"`
- If missing: patch `db/schema.sql` or add migration runner.

3) Run the pipeline exactly as intended
```bash
python3 scripts/sync_truth_workbook_to_db.py --workbook ~/Docs/Autonomous_business/excel/Inventory_Core_V18.xlsx
python3 scripts/generate_po_dashboard_data.py
python3 scripts/smoke_test_dashboard.py
```

### P0-2 — Fix blackout semantics (if RF1 is true)
**Owner:** Captain (design decision) → Opus (implementation)

Implementation guidance:
- Introduce `add_working_days(start_date, n_work_days, blackout_ranges)`
- Compute:
  - `prep_end = add_working_days(message_date, prep_days)`
  - `ship_date_cargo = prep_end + cargo_handling_days` (usually 0–1; clarify)
  - `eta = ship_date_cargo + L` (L not blackout-affected)

Add deterministic tests for:
- message_date 2026-01-25, prep_days 10 → ship_date_cargo >= 2026-02-21

### P0-3 — Demand estimator regression harness (stop under-orders)
**Owner:** Opus

Deliver a script:
- `scripts/report_demand_top_skus.py`
Outputs CSV with for each SKU:
- d_anchor, d_data, d_model, d_final
- good_days, eligible_days, unknown_days, oos_days, availability_score, confidence
- sum(d_size), d_sku, delta_pct

Must include:
- LINE52 and LINE51 always.
- Any SKU with `d_final < 0.7*d_anchor` OR `eligible_days == 0` flagged.

### P0-4 — Size reconciliation invariant (block bad exports)
**Owner:** Opus

In dashboard generation:
- enforce:
  - `abs(sum(d_size) - d_sku) <= 0.01` (or <= 1 unit after scaling)
  - `sum(order_qty_size) == sku_order_qty_total`
If violated:
- emit `skipped_skus` entry with reason `SIZE_INVARIANT_FAIL`
- also fail smoke test.

### P0-5 — Auto-PO integration (unblocks future automation)
**Owner:** Opus

Change the auto PO query to:
- join the *latest cutoff_date* in `fact_demand_estimates`
- use `COALESCE(de.d_final, m.d30)`
- persist the cutoff_date used into the draft header for auditability.

---

## 5) P1 Task List (after P0 passes)

### P1-1 — Scheduled run at 20:30 (operational leverage)
**Owner:** Captain (safety design) → Opus (implementation) → Adil (install)

- Ensure `run_end_of_day.py` calls:
  1) workbook sync
  2) dashboard generation
  3) smoke test
  4) export artifacts
- Add locking to prevent concurrent runs.
- Add “workbook locked” detection (catch exceptions, exit with a clear message).

### P1-2 — PO-4/PO-5/PO-6 scenario export
**Owner:** Opus

Produce:
- `exports/po_4_5_6_recalc.csv` (or xlsx)
Each PO should show:
- message_date, prep_days, ship_date_cargo, ETA
- total qty, total weight, key SKUs and size splits
- blackout warnings where applied

---

## 6) Definition of Done (DoD)
We can re-enable automation only when all are true:
- Demand harness shows no material under-estimation for the top SKUs **without an explicit coverage reason**.
- Blackout semantics validated with tests.
- Auto-PO uses `d_final` (or automation remains explicitly disabled).
- Smoke test fails fast on any invariant breach.

---

## 7) Docs to update after implementation
- `.claude/DECISIONS.md`: blackout semantics + date semantics + demand estimate persistence contract
- `docs/DAILY_SOP.md`: daily run instructions (20:30), what outputs to inspect
- `docs/ARCHITECTURE.md`: add `fact_demand_estimates` and blackout module map
