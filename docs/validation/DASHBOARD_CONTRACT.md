# Dashboard Contract (Phase 3)

Purpose: single owner of dashboard output schema + invariants, and the gate for dashboard/PO alignment.

Source of truth:
- Inventory formulas: `docs/inventory/Master_Inventory_Rules_v8.md`
- PO contract/tolerances: `docs/validation/PO_CONTRACT.md`

## Deterministic fixture
- Input fixture: `tests/fixtures/po_golden/po_contract_cases.json`
- Gate command (deterministic):
  - `python3 scripts/smoke_test_dashboard.py --fixture tests/fixtures/po_golden/po_contract_cases.json`

## Required output schema (minimal)
Top-level keys:
- `generated_at` (ISO string)
- `cutoff_date` (YYYY-MM-DD string)
- `summary` (object)
- `pos` (object)
- `archived_pos` (list of non-PLAN entries in `pos`, part-grain IDs when `po_part` exists)
- `real_pos` (list; may be empty)

`summary` required fields:
- `total_skus` (int)
- `skus_with_orders` (int)
- `total_units` (int)

`pos` required fields:
- Must include key `PLAN-0` (fixture plan bucket)
- `PLAN-0` must include:
  - `po_name` (string, value "PLAN-0")
  - `po_kind` (string, value `PLAN`)
  - `summary` (object with `total_skus`, `total_units`)
  - `sku_level` (list)
- `PLAN-0` represents the **next planned PO after the latest real PO** (latest real POs appear only in `archived_pos`/`real_pos`)

Each non-PLAN entry in `pos` must include:
- `po_kind` = `REAL_ARCHIVE`
- must be listed in `archived_pos`
- must be recomputed from message-date state (`MAX(snapshot_date <= po_message_date)`), not cloned from PLAN rows
- when source PO has part rows, archive key must be `po_part_id` (for example `PO-5.2`, `ARC-1.0`)

Each `sku_level` entry must include:
- `sku_key` (string)
- `d_sku` (float)
- `po_qty_total` (int)
- `size_orders` (object {size: qty})
- `roic_pct` (float, percentage)
- `stock_at_msg` (numeric; stock baseline at row message date)
- `consumption_until_arrival` (numeric; theoretical `d_sku * effective_L`)
- `consumption_until_arrival_capped` (numeric; `min(consumption_until_arrival, stock_at_msg + active_inbound)`)
- `baseline_snapshot_date` (YYYY-MM-DD; snapshot used for baseline)

`REAL_ARCHIVE` `size_level` ordered rows (`order_qty > 0`):
- should include `po_part_id` when part-tagged source lines exist for that PO (legacy single-part archives without part tags are allowed)

`real_pos` entry minimal fields:
- `po_id` (string)
- `parent_po_id` (string or null)
- `status` (string)
- `message_date` (YYYY-MM-DD or null)
- `units_total` (int)
- `units_received` (int)
- `weight_nom_kg` (number)
- `total_places` (int)

## Invariants vs PO engine (same fixture input)
For each SKU in the fixture:
1) `d_sku` matches PO engine `PODraft.d_sku` within PO_CONTRACT `D_30_pct_points` tolerance.
2) `po_qty_total` == PO engine `PODraft.total_qty` (exact).
3) `size_orders` == PO engine `PODraft.allocations` (exact, per-size quantities).
4) `roic_pct` matches `PODraft.roic_monthly * 100` within PO_CONTRACT `ROIC_pct_points` tolerance.
5) `sum(size_orders) == po_qty_total`.
6) DOC display rounding is half-up to 1 decimal (e.g., `29.95 -> 30.0`, `60.75 -> 60.8`) for both PLAN and REAL_ARCHIVE rows.
7) For positive order quantity and positive demand, `post_arr_doc > pre_arr_doc`.
8) REAL_ARCHIVE per-row `pre_arr_doc` / `post_arr_doc` must match recomputed formula from baseline pre-arrival and actual order quantities.

Summary invariants:
- `summary.total_skus == len(sku_level)`
- `summary.total_units == sum(po_qty_total for sku_level)`
- `summary.skus_with_orders == count(po_qty_total > 0)`

## Coverage requirements (“100% functional”)
The dashboard is only considered functional when coverage is complete:
- **Active SKU coverage:** dashboard must include 100% of active SKUs (no silent drops).
- **Stock coverage:** each active SKU must have a stock snapshot OR explicit `NO_STOCK_SNAPSHOT` note.
- **Demand coverage:** SKUs with recent sales must have demand estimates (no `NO_DEMAND_ESTIMATE` allowed).
- **Size mapping:** any SKU that appears in sales/orders OR in the latest snapshot date (<= cutoff) must have size mapping; missing MY_SIZE is a hard error.
- **Day complete:** if day_complete is red, exports/writes are blocked (see `DAY_COMPLETE_CONTRACT.md`).

## Update protocol
1) Update `docs/inventory/Master_Inventory_Rules_v8.md` first if formulas change.
2) Update `docs/validation/PO_CONTRACT.md` tolerances as needed.
3) Re-run dashboard contract gate on the deterministic fixture.
4) If schema changes, update this doc + the smoke test validator.
