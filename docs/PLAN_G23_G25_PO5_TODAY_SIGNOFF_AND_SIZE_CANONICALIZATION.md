# PLAN: G23–G25 — PO-5 Today Sign-off + LINE52 Size Canonicalization

Date: 2026-01-20
Owner: Agent
Repo (main): ~/Docs/Autonomous_business
Source worktree (historical): ~/Docs/wt_plan2_fix
Priority: NOW (PO-5 must be issued today; CNY shutdown risk)

## Objective
We must be able to create a REAL PO-5 today without introducing ledger drift, cross-size identity drift,
or stale-dashboard mistakes.

This plan is a "verify-what's-done + patch-the-last-blocker" plan. It assumes most of the seasonal-demand
work is already implemented.

## What is already DONE (verify, don't re-implement)
G23:
- Multi-window demand override support (schema + business_params selection + seed script)
- LINE52 demand windows:
  - 2026-01-01 → 2026-03-01: D=40
  - 2026-03-01 → 2026-06-01: D=30
- 100-day demand analysis export exists:
  - exports/demand_analysis_100d_YYYYMMDD.csv
  - includes: eligible_days, good_days (OOS<=30%), days_with_sales, d_dashboard, delta columns

Definition of Verified Done:
- Code references multi-window (sku_key,start,end) uniqueness
- Migration script exists and is idempotent
- Demand analysis CSV regenerates successfully and contains required columns
- Dashboard uses D=40 for LINE52 at cutoff dates inside Jan–Mar window

## Critical Blocker (must fix)
LINE52 has a non-canonical adult size token "42" appearing in planning outputs (size-level and supplier export)
and can receive non-zero order_qty. This is NOT allowed because adult CL MY_SIZE must be canonical.
Per size engine spec: 42 maps to S; 44->M; 46->L; 48/50->XL; 52->2XL; 54->3XL; 56+->4XL.

If we create real PO lines with sku_id *_42, we will create phantom variants and future reconciliation drift.

## Non-negotiable Stop Conditions (NO-GO)
- validate_po_dashboard_invariants fails
- Any PLAN-1 size-level ordered line for a CL SKU uses a non-canonical size token (e.g., "42") with order_qty>0
- Supplier export contains sku_id variants with non-canonical size suffixes for adult CL

## Tasks

### T0 — Safety + context
1) Create DB backup BEFORE any write/migration:
   - python3 scripts/backup_db.py --dest ~/Docs/Oracle/Autonomous_business/YYYY-MM-DD/po5_today --db db/app.db --no-cleanup
2) Confirm branch/HEAD and ensure exports will be regenerated (no stale dashboard).
3) Update tracking:
   - Append to .claude/GOALS.md and .claude/TASKS.md:
     - G23 — Seasonal demand windows + 100d demand report (verify DONE)
     - G24 — Size canonicalization hard gate (LINE52 42->S) (TODO)
     - G25 — PO-5 today sign-off pack + supplier CSV (TODO)

### T1 — Verify seasonal overrides are live
- Verify LINE52 has two windows in DB:
  - query DB or use override dump command (preferred if exists)
- Verify PLAN-1 uses D=40 and PLAN-2 uses D=30 when computed for March dates (if engine supports per-plan effective dates).

### T2 — Generate fresh outputs (authoritative)
- python3 scripts/update_po_dashboard.py
- Ensure exports refreshed:
  - exports/po_dashboard_data.json
  - exports/po_dashboard.html
  - exports/po_supplier_export_YYYY-MM-DD.csv (or latest)
  - exports/po_supplier_summary_YYYY-MM-DD.md

### T3 — Add a hard "invalid size" gate (must)
Implement a guardrail so this cannot happen again.

Requirements:
- Add a canonicalization function for MY_SIZE tokens:
  - Map numeric synonyms >=38 per size spec (42->S, 44->M, ...)
  - Preserve kids numeric sizes like 22/24/26/28/30 if used for kids SKUs
- Enforce canonical tokens in:
  - dim_sku_size generation / seeding
  - supplier export generation
  - dashboard size-level output generation
- Add validation in scripts/validate_po_dashboard_invariants.py:
  - FAIL if any CL SKU size-level order line has non-canonical size with order_qty>0

### T4 — Patch existing data / dim tables (LINE52 focus)
Create an idempotent migration script:
- Find any dim_sku_size rows where sku_key=LINE52 and my_size token is numeric synonym (e.g. 42).
- Map it to canonical (42->S).
- If S already exists, merge/dedupe (do NOT create duplicate keys).
- Re-run dashboard export and confirm "42" no longer appears anywhere in outputs.

### T5 — Final gates for PO-5 today
Run:
- python3 scripts/validate_po_dashboard_invariants.py
- python3 scripts/run_end_of_day.py --verbose   (or equivalent minimum production gate)

### T6 — PO-5 sign-off pack (Oracle)
Create an oracle pack with:
- status log
- commands run
- DB backup path
- fresh exports listed (po_dashboard_data.json/html, supplier export/summary, demand_analysis_100d)
- explicit proof that LINE52 has no "42" size ordering line

## Definition of Done (DoD)
- LINE52 seasonal overrides exist as 2 windows in DB
- demand_analysis_100d export regenerates successfully
- PO-5 outputs are freshly regenerated and NOT stale
- No non-canonical adult CL sizes appear in PLAN-1 ordered size lines (especially no LINE52 "42")
- All gates pass
- Oracle sign-off pack produced
