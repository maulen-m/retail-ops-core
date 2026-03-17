# Dashboard Contract (Phase 3)

Purpose: single owner of dashboard output schema + invariants, and the gate for dashboard/PO alignment.

Source of truth:
- Inventory formulas: `docs/inventory/Master_Inventory_Rules_v8.md`
- PO contract/tolerances: `docs/validation/PO_CONTRACT.md`

## Deterministic fixture
- Input fixture: `tests/fixtures/po_golden/po_contract_cases.json`
- Gate command (deterministic):
  - `python3 scripts/smoke_test_dashboard.py --fixture tests/fixtures/po_golden/po_contract_cases.json`
  - `python3 scripts/validate_dashboard_plan_real_contract.py --strict`

## Required output schema (minimal)
Top-level keys:
- `generated_at` (ISO string)
- `production_scope` (string; `OWNER_MONITORING_ONLY` when the payload is being consumed as a monitoring/planning surface rather than a PO-execution release)
- `po_execution_ready` (boolean; `false` when stale planning inputs are explicitly trust-labeled and must not be interpreted as execution-ready)
- `cutoff_date` (YYYY-MM-DD string)
- `summary` (object)
- `pos` (object)
- `archived_pos` (list of non-PLAN entries in `pos`, part-grain IDs when `po_part` exists)
  - ordering contract: chronological by cargo send date ascending (oldest first)
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
- PLAN message schedule is config-driven from `config/po_schedule.yaml`:
  - `plan0_anchor_message_date`
  - `reorder_cycle_days`

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
- `prep_lane` (string; `CORE_PRINT_SUIT` / `GENERAL_CL` / `ELS`)
- `prep_days_lane` (int; lane-level prep days used for this row)

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

PLAN vs REAL labeling rules:
- Keys starting with `PLAN-` must always have `po_kind=PLAN`.
- Non-PLAN keys in `pos` must always have `po_kind=REAL_ARCHIVE`.
- Non-PLAN keys must be listed in `archived_pos`.
- `real_pos.po_id` entries must refer to materialized real PO identities (or documented legacy archive keys where applicable).

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

## Owner monitoring scope
- When `production_scope=OWNER_MONITORING_ONLY` and `po_execution_ready=false`, stale stock snapshot vs cutoff remains visible in the payload, but it is not treated as a hard execution blocker by `validate_po_dashboard_invariants.py`.
- This scope does **not** upgrade the PO dashboard to execution-ready status; it only allows owner-facing monitoring surfaces to consume explicitly stale planning inputs with trust labels.
- Any owner-facing consumer built on top of PO dashboard output must preserve:
  - `planning_snapshot.freshness`
  - stale trust labeling in its own trust banner or brief text
  - clear separation between monitoring-only planning advice and execution-ready PO action

## Dim SKU Weight Truth
- Canonical weight source: `Dim sku light v5.xlsx` (see `scripts/sync_dim_sku_from_dim_sku_light.py`).
- Strict gate: `scripts/validate_dim_sku_light_alignment.py` (weight mismatches are hard failures; base-cost mismatches are warnings by default).
- Inbound sync (`scripts/sync_po_parts_from_inbound_calendar.py`) must not overwrite existing `dim_sku.weight_kg` unless explicitly enabled by CLI flag.

## Update protocol
1) Update `docs/inventory/Master_Inventory_Rules_v8.md` first if formulas change.
2) Update `docs/validation/PO_CONTRACT.md` tolerances as needed.
3) Re-run dashboard contract gate on the deterministic fixture.
4) If schema changes, update this doc + the smoke test validator.
