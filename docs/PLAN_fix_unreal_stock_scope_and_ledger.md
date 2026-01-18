# PLAN: Fix Unreal Stock Values (Ledger/Scope/Canonicalization)

Date: 2026-01-17
Priority: NOW (capital-risk correctness)
Owner: Agent

## Problem
Dashboard/PO engine sometimes shows unreal stock (e.g., LINE52 stock 6000–7000+) that contradicts the trusted Excel reference Snapshot_Z.
This implies double counting (store_code aggregation, SKU_ID aliasing, PO arrival duplication) or wrong inventory scope.

## Sources of truth (must match)
1) Excel reference: `excel/Inventory_Core_V18.1_V2.xlsx` → sheet `DIM_SKU_ID`:
   - `Snapshot_Z_date` and `Snapshot_Z` columns.
   - Canary SKUs: LINE52 + LINE51 must match within tight tolerance.
2) Real inbound: PO-4 and Line52_PO-9 arrived on 2026-01-14 (quantities known).
3) Sales: canonical sales table (`sales_fact_v2`) for consumption.

## Goal / Definition of Done
1) Stock snapshot rebuild in LEDGER mode passes (no negative balances).
2) DB snapshot for `snapshot_date=2026-01-14` (pre-arrival or defined convention) matches Snapshot_Z for canary SKUs:
   - LINE52 total = 1393 (by size)
   - LINE51 total = 457 (by size)
   (Exact per-size match preferred; if rounding exists, max abs diff <= 1 per size.)
3) After applying 2026-01-14 arrivals (PO-4 + PO-9) and sales, stock evolves correctly and PLAN-1 orders become plausible.
4) No “phantom size keys” (e.g., 26/28/30/0) appear under LINE52.
5) Add a gate so this cannot regress.

## Step 1 — Diagnose double counting (no guessing)
Run these SQL diagnostics and save outputs to `exports/debug_stock_scope_*.csv`:

A) For a SKU_key (LINE52, LINE51), show snapshot rows by store_code (if present):
- Expectation: exactly one inventory pool is used for PO planning (e.g., ASTANA or UNIVERSAL).
- If multiple store_code rows exist and are being summed, quantify duplication.

B) Show ledger balances by store_code for the same SKU_ID sizes as of 2026-01-13:
- If balances exist in multiple store_codes for the same physical pool -> duplication.

C) Show SKU_ID variants for LINE52 and LINE51 (leading/trailing whitespace, casing):
- Count distinct sku_id strings that normalize to the same canonical form.

D) Check arrivals sources:
- Compare inbound contributions from:
  - fact_po_lines (if used)
  - po_header/po_line derived receipts (if used)
- Ensure a given real PO line contributes inbound exactly once.

## Step 2 — Enforce canonical identity (SKU_ID + size)
Implement/confirm:
1) `core/utils/sku_normalize.py` normalizes:
   - all unicode whitespace
   - uppercase size tokens
   - trims SKU_ID suffixes safely
2) Add a DB cleanup script (idempotent):
   - merge SKU_ID aliases that normalize to same canonical SKU_ID
   - update referencing tables (sales, ledger, snapshot) to canonical ids
3) Add a validation script:
   - fails if multiple raw SKU_IDs normalize to same canonical SKU_ID (unless explicitly allowed with synonym table)

## Step 3 — Fix inventory scope semantics (store_code)
Decide and implement ONE policy for PO planning:
Option A (recommended): PO planning uses ONE physical pool (Astana warehouse).
- All sales (all channels/stores) subtract from that pool.
- Do NOT sum balances across store_code pools.
- store_code is reporting-only, not inventory pools (unless explicitly modelled).

Implementation:
- Snapshot rebuild queries must use the chosen store_code pool only.
- Sales consumption is aggregated across all store_codes but applied to the chosen pool.
- UNIVERSAL handling must not cause duplicate summation.

Add a guard:
- If snapshot rebuild sees multiple pools for a portfolio SKU, fail with a report.

## Step 4 — Rebuild from anchor + reconcile to Snapshot_Z
1) Identify last real anchor snapshot date (2025-12-26).
2) Rebuild ledger snapshot forward using:
   - anchor stock
   - arrivals (receipts)
   - sales consumption
   - adjustments (explicit, auditable)
3) Import Snapshot_Z (2026-01-14) as a reconciliation checkpoint:
   - Either (preferred) treat Snapshot_Z as a “truth checkpoint” and compute a single adjustment event to reconcile.
   - Or treat Snapshot_Z as baseline for post-2026-01-14 rebuilds (but do not double-add it).

Output:
- `exports/reconcile_snapshot_z_report.csv` showing per-size diffs before/after.

## Step 5 — Add a regression gate
Add `scripts/validate_snapshot_vs_snapshot_z.py`:
- Reads `Inventory_Core_V18.1_V2.xlsx` (DIM_SKU_ID Snapshot_Z)
- Queries DB snapshot for the same date
- Validates per-size diffs within tolerance for:
  - LINE52
  - LINE51
  - (optionally) other high-volume SKUs
Fail hard if mismatch.

Wire into:
- `scripts/run_end_of_day.py` before exports/writes.

## Step 6 — Rerun full gates + evidence pack
Run:
- python3 scripts/run_end_of_day.py --verbose
- python3 scripts/validate_po_dashboard_invariants.py
- python3 scripts/validate_snapshot_vs_snapshot_z.py
- pytest -q
- scripts/lint_docs.sh (if docs touched)
- scripts/check_no_db_tracked.sh

Create offline oracle pack including:
- all changed files
- debug CSVs from Step 1
- snapshot_z reconcile report
- relevant DB extracts (fact_orders_kaspi, sales_fact_v2, ledger, po lines)
- dashboard json/html outputs

## Stop conditions
- If any “fix” increases stock by summing across pools: STOP.
- If Snapshot_Z is being applied twice (baseline + adjustment): STOP and correct.
- If arrivals contribute inbound from multiple sources: STOP and dedupe source-of-truth.
