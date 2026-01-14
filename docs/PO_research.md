# PO Research (Jan 2026)

**As-of date:** 2026-01-13 (Asia/Almaty cutoff)  
**Scope:** PO engine + PO dashboard data correctness, size-level ordering, and data lineage.

## 1) End-to-end data flow (source → outputs)

### A) Sales inputs (source of truth)
1. **CRM Excel** (`excel_ui/SALES_KSP_CRM_V3.xlsx`, sheet `SALES_KSP_CRM_1`)
   - Ingested by `scripts/sync_crm_to_db.py` → `sales_fact_v2` + `fact_sales`.
   - Aggregates rebuilt into `fact_sales_daily` + `fact_sales_daily_size`.
   - This is the canonical order-line source for historical sales in the DB.

2. **Kaspi API orders** (`scripts/sync_kaspi_orders.py`)
   - Updates `fact_orders_kaspi` (status reconciliation).

### B) Stock inputs
1. **Stock ledger + snapshot**
   - `scripts/rebuild_snapshot.py` creates `fact_inventory_snapshot_size` for the cutoff date.
   - Uses **stock ledger events** + **pending PO inbound** to build stock + inbound at size level.

2. **Inbound PO lines**
   - `po_header` + `po_line` are the live PO tracking tables.
   - `fact_po_lines` contains imported inbound; for POs not in `po_line`, inbound is included in snapshot.

### C) Demand estimation
- Implemented by `core/calc/demand_estimator.py` and invoked in `scripts/generate_po_dashboard_data.py`.
- Blends:
  - **D_anchor** from `dim_anchor` (DB-first, Excel fallback if missing)
  - **D_data** from sales (OOS-aware)
- Result = **D_final** (per SKU) + **D_size** per size.

### D) PO engine (size-aware)
- `scripts/generate_po_dashboard_data.py` builds PO-4 (base) and projects PO-5..PO-10.
- For each SKU size:
  - Pre-arrival = stock_at_msg + active_inbound − consumption
  - Target = D_size × T_post (from v8 rules)
  - Order qty = max(0, target − pre_arrival)
- Size allocations for future POs **use D_size weights** (not prior PO orders) to avoid zeroing sizes like 3XL.

### E) Dashboard
1. `scripts/update_po_dashboard.py` writes:
   - `exports/po_dashboard_data.json`
   - `exports/po_dashboard.html`
2. UI recalculations (multipliers / approvals) must stay consistent with backend size orders.

## 2) Known drift issues (root causes)

### Issue A — Size-level orders mismatch vs size-horizontal
**Symptom:** Size sheet exported from dashboard did not match size-horizontal (e.g., 3XL = 0 in table but >0 in export).  
**Root cause:** Frontend recalculated size-level orders from its own formula, not from backend size orders.  
**Fix:** Recalc now **uses parent SKU size_orders** for size order qty; size-level and size-horizontal stay aligned.

### Issue B — Size allocation zero for 3XL in PO-5
**Symptom:** 3XL order_qty = 0 even with known shortage.  
**Root cause:** Allocation weights used **prior PO-4 order mix**, which had 0 units for 3XL.  
**Fix:** Allocation weights now prefer **D_size weights** (demand-based); 3XL receives order when D_size > 0.

### Issue C — Duplicate snapshot rows causing inbound/stock drift
**Symptom:** size-level inbound/stock mismatch due to duplicate rows per size in snapshot.  
**Fix:** Snapshot reads now **sum by size** to avoid overwriting duplicate rows.

### Issue D — Negative stock in dashboard (ledger mode)
**Symptom:** Negative stock values appeared for some SKUs in the PO dashboard.  
**Root cause:** Ledger rebuild can yield negative balances when sales/inbound history is incomplete; auto mode detects this and falls back to **simulation** to avoid negative snapshots.  
**Fix:** Run snapshot rebuild in auto mode (simulation fallback), then regenerate PO dashboard. Latest run shows zero negative snapshot rows for 2026-01-13.

## 3) Current data accuracy checks

### A) Line52 (PO-5) size orders
- D_size is now used for allocation.
- 3XL receives non-zero order when D_size > 0.

### B) Inbound classification
- **Snap_Inb** = snapshot inbound (future arrivals already in snapshot)
- **Act_Inb** = arrivals after msg_date but before arr_date (active during lead time)
- **Inb_Tot** = snapshot inbound + active inbound (no double count)

## 4) Recent DB updates
- **Orders DB reconciliation (Y/Z merge)** was applied to produce a cleaner `db/app.db`.
- Demand estimates and PO outputs now derive from the reconciled DB.

## 5) How to verify correctness

1) Rebuild snapshot (as-of cutoff):
```bash
python3 scripts/rebuild_snapshot.py --date 2026-01-13 --mode auto
```

2) Generate PO data + HTML:
```bash
python3 scripts/update_po_dashboard.py
```

3) Check key outputs:
- `exports/po_dashboard_data.json` (size_level vs size_horizontal totals)
- `exports/demand_diagnostics.csv`
- `exports/stock_rebuild_diagnostics.csv`

## 6) Data artifacts (for oracle pack)
- `exports/po_dashboard_data.json`
- `exports/demand_diagnostics.csv`
- `exports/stock_rebuild_diagnostics.csv`
- `exports/po_supplier_export_2026-01-13.csv`
- `exports/po_supplier_summary_2026-01-13.md`
- `exports/shadow_scorecard_2026-01-14.csv`
- `exports/research_dim_anchor_2026-01-13.csv`
- `exports/research_fact_sales_daily_size_2026-01-13.csv`
- `exports/research_sales_fact_v2_2026-01-13.csv`
- `exports/research_stock_snapshot_2026-01-13.csv`
- `exports/research_po_inbound_open_2026-01-13.csv`

---

## Rollback plan
1) Revert commits for PO allocation + dashboard recalc if needed:
```bash
git revert <commit_sha>
```
2) Regenerate outputs:
```bash
python3 scripts/update_po_dashboard.py
```
