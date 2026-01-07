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

`summary` required fields:
- `total_skus` (int)
- `skus_with_orders` (int)
- `total_units` (int)

`pos` required fields:
- Must include key `PO-4` (fixture PO bucket)
- `PO-4` must include:
  - `po_name` (string, value "PO-4")
  - `summary` (object with `total_skus`, `total_units`)
  - `sku_level` (list)

Each `sku_level` entry must include:
- `sku_key` (string)
- `d_sku` (float)
- `po_qty_total` (int)
- `size_orders` (object {size: qty})
- `roic_pct` (float, percentage)

## Invariants vs PO engine (same fixture input)
For each SKU in the fixture:
1) `d_sku` matches PO engine `PODraft.d_sku` within PO_CONTRACT `D_30_pct` tolerance.
2) `po_qty_total` == PO engine `PODraft.total_qty` (exact).
3) `size_orders` == PO engine `PODraft.allocations` (exact, per-size quantities).
4) `roic_pct` matches `PODraft.roic_monthly * 100` within PO_CONTRACT `ROIC_pct` tolerance.
5) `sum(size_orders) == po_qty_total`.

Summary invariants:
- `summary.total_skus == len(sku_level)`
- `summary.total_units == sum(po_qty_total for sku_level)`
- `summary.skus_with_orders == count(po_qty_total > 0)`

## Update protocol
1) Update `docs/inventory/Master_Inventory_Rules_v8.md` first if formulas change.
2) Update `docs/validation/PO_CONTRACT.md` tolerances as needed.
3) Re-run dashboard contract gate on the deterministic fixture.
4) If schema changes, update this doc + the smoke test validator.
