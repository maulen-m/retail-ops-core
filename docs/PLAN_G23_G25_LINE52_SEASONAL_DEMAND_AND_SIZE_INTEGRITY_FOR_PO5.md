# PLAN G23–G25 — LINE52 seasonal demand + demand audit + supplier-size integrity gate (PO-5 safe)

## Phase
PO-5 readiness hardening (demand + size integrity) before spending capital.

## Context (physics of the problem)
A PO engine is only as correct as:
1) Demand (D) estimate per SKU and season window, and
2) Size identity (MY_SIZE) integrity.

If either is wrong:
- Wrong D → over-ordering or stockouts (capital loss or profit loss).
- Wrong sizes → dead stock (capital loss is often near 100% of COGS).

We previously had time-boxed demand overrides (e.g., LINE52=50, LINE51=12) and enforced end-date behavior (override inactive on end-date boundary).
We also saw size contamination from CRM/waybill tests that created invalid MEN sizes (numeric sizes like 42, 26/28/30), which must never reach supplier exports.

## Goals
### G23 — LINE52 seasonal demand overrides (2 windows)
Implement LINE52 overrides:
- 2026-01-01 → 2026-03-01 : D = 40
- 2026-03-01 → 2026-06-01 : D = 30

Important: end_date is exclusive per existing behavior; confirm with tests.
If end_date is exclusive, window (2026-01-01 → 2026-03-01) means active on dates < 2026-03-01.

### G24 — Demand history audit report (last 100 days)
Generate a CSV report for all sku_key sold in last 100 days:
- Robust/denoised daily demand estimate (exclude spikes)
- OOS / partial-OOS detection
- Reconstructed “full demand” using size share anchors when partial-OOS occurs
- Columns:
  - sku_key
  - date range (min/max)
  - total_units_sold
  - days_with_sales
  - total_calendar_days
  - good_days_count (availability >= ~70% or OOS<=30%)
  - oos_days_total, partial_oos_days_total
  - d_raw (units / good_days)
  - d_denoised (trimmed mean or MAD-filtered)
  - d_reconstructed (scaled by in-stock share; capped)
  - current_d_anchor (if exists)
  - current_d_sku (as used in dashboard)
  - current_override (if active)
  - delta_d_sku_vs_d_denoised
  - confidence flags / warnings

Output:
- exports/demand_history_last100d.csv
- exports/demand_history_last100d_README.md (method + definitions)

### G25 — Supplier export size integrity gate
Add a hard validation that prevents PO creation/export if:
- adult MEN CL SKUs produce numeric sizes (e.g., 42, 26/28/30)
- size mix includes unknown/non-canonical sizes for that SKU/product_type

This must fail gates BEFORE PO-5 is made.

## Non-goals
- No redesign of the whole demand model.
- No UI multiplier reintroduction as JS-only behavior.

## Working directory & branching
Repo: ~/Docs/Autonomous_business
Base branch: integration/plan2-doc-floor-po5 (or latest main if already merged)
Worktree: create a dedicated worktree for this task (no shared working dir).

## Preconditions / Safety
- Take DB backup before any script with writes:
  python3 scripts/backup_db.py --dest ~/Docs/Oracle/Autonomous_business/YYYY-MM-DD/po5_demand_v2 --db db/app.db --no-cleanup

## Step-by-step tasks

### Task A — Implement LINE52 two-window overrides
1) Update default seed logic (single source) so seed includes two windows for LINE52.
   - Prefer: define DEFAULT_DEMAND_OVERRIDES constant used by both seed + tests.
2) Update/extend tests to validate:
   - override application works
   - end_date boundary behavior
   - correct override chosen when windows overlap/abut (no overlap expected)
3) Run:
   python3 scripts/validate_params.py --strict
   pytest -q

Evidence:
- exports/validate_params_strict.txt (or oracle note with stdout)

### Task B — Build 100-day demand history audit CSV
1) Implement new script:
   scripts/export_demand_history_last100d.py
   Inputs:
   - sales_fact_v2 (authoritative normalized sales)
   - stock availability series (ledger/snapshot) for OOS tagging
   - size mix anchors (from dim_sku_size or existing anchor tables)

2) Methods (minimum acceptable):
   - Spike filtering: MAD or percentile trim
   - OOS classification: total_stock==0 => OOS
   - partial-OOS: missing sizes relative to anchor set; compute availability score
   - Reconstruction: demand_est = observed_sales / in_stock_share (cap scaling factor)

3) Produce exports:
   - exports/demand_history_last100d.csv
   - exports/demand_history_last100d_README.md

### Task C — Supplier export size gate (PO-5 blocker)
1) Add script:
   scripts/validate_supplier_export_sizes.py
   - Loads the generated supplier export dataframe before writing CSV
   - For each sku_key in CL_MEN:
     - Fail if my_size is numeric (regex ^\\d+$) OR not in allowed set
   - Allow numeric sizes only for KID SKUs/categories

2) Wire into pipeline:
   - called by scripts/run_end_of_day.py (after PO calc, before export)
   OR
   - called by scripts/export_supplier_po.py and treated as gate failure.

3) Add unit tests:
   - A synthetic export row with MEN sku_key + my_size=42 must fail.

### Task D — Regenerate dashboard + supplier export + evidence
Run:
- python3 scripts/run_end_of_day.py --verbose
- python3 scripts/update_po_dashboard.py
- python3 scripts/validate_po_dashboard_invariants.py
- pytest -q
- scripts/lint_docs.sh
- scripts/check_no_db_tracked.sh

Outputs to capture:
- exports/po_dashboard.html
- exports/po_dashboard_data.json
- exports/po_supplier_export_<date>.csv
- exports/po_supplier_summary_<date>.md
- exports/demand_history_last100d.csv
- exports/demand_diagnostics.csv

### Task E — Oracle pack + tracking
1) Create oracle pack in:
   ~/Docs/Oracle/Autonomous_business/YYYY-MM-DD/<timestamp>_TASK-XXX_po5_demand_v2.md
2) Copy key exports into the same Oracle folder (not into git).
3) Update .claude/GOALS.md and .claude/TASKS.md:
   - Add G23/G24/G25 with status and links to oracle pack paths.
   - Preserve history (append-only).

## Definition of Done
- LINE52 overrides are active as specified (2 windows) and proven by an evidence snippet in the oracle pack.
- demand_history_last100d.csv exists and clearly shows D deltas vs current anchors.
- Supplier export gate fails on MEN numeric sizes; after fixes, export contains only canonical sizes.
- All gates green.
- No oracle artifacts / generated exports committed to git.

