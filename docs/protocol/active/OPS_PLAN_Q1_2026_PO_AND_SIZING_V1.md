Made the remaining pipeline fixes and pushed EOD through Step 5; it now blocks at the audit gate (LINE52/LINE51 expected D_SKU mismatch). I did not weaken any gates.

**What changed**
- `dim_sku` migration + validate hook + regression test; EOD now survives schema drift.
- Truth workbook sync now handles `Current_stock_Stock_date` and coerces anchor sheets to numeric, avoiding hard crashes.
- Demand estimates are persisted into a new `fact_demand_estimates` table; dashboard output now includes `summary` + `priority_skus` so `update_po_dashboard.py` works again.

**Current status**
- `run_end_of_day.py --verbose` now passes Steps 0–5.
- It **fails at Step 6 (Audit Dashboard Output)** with: `Exit code 2: LINE52 d_sku=34.943, expected=50` (and LINE51 expected 12).

**Commands run (key outputs)**
- `python3 -m pytest -q`  
  - `21 failed, 968 passed, 4 skipped, 2 warnings`  
  - Failures include blackout, FX calc, demand estimator, po_dashboard_overrides, queries_v2, po_generator import (pre‑existing).
- `python3 scripts/run_end_of_day.py --verbose`  
  - Steps 0–5 OK  
  - Step 6 failed: `Audit Dashboard Output` → `Exit code 2: LINE52 d_sku=34.943, expected=50`

**Commits**
- `9247623` fix: add dim_sku migration and workbook sync guards
- `b6a841d` fix: persist demand estimates for dashboard pipeline
- `839112b` docs: log TASK-271 status and session

**Oracle pack**
- `~/Docs/Oracle/Autonomous_business/2026-01-03/113906_TASK-271.md`

**Working tree**
- `db/app.db` modified from running EOD (not committed).

**Next steps to clear the audit gate (recommend)**
1) Inspect demand overrides for LINE52/LINE51 (likely expected values come from overrides) and wire them into `generate_po_dashboard_data.py` so `d_final_with_override` and `notes` match audit expectations.  
2) If overrides are in DB or config, apply them at generation time and persist into `fact_demand_estimates`.  
3) Re‑run `python3 scripts/run_end_of_day.py --verbose` to verify Audit passes.

If you want me to proceed with the override wiring, say the expected source of truth for overrides (DB table or config file) and I’ll implement it.
