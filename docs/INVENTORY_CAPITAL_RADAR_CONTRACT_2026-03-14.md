# Inventory Capital Radar Contract

Date: `2026-03-14`

## Goal

Expose reorder / freeze / no-order / tied-up-capital monitoring in one owner-facing surface without upgrading stale planning into execution-grade truth.

## Source boundary

- `inventory_capital_radar` is a composition layer only.
- It may read only:
  - `exports/daily/<as_of>/owner_truth_summary.json`
  - `exports/diagnostics/<as_of>/system_health.json`
  - `exports/owner/<as_of>/po_sku_daily.json`
  - `exports/owner/<as_of>/owner_profit_daily.json`
- It must not recompute PO math, reorder logic, or margin math.

## Required semantics

- Planning freshness must be copied directly from `po_sku_daily`.
- If `po_sku_daily.planning_snapshot.freshness=STALE_VS_CUTOFF`, that staleness must remain visible.
- Profit decision scope must be copied through from `owner_profit_daily`.
- This surface remains monitoring-only unless both planning freshness and profit semantics are explicitly upgraded elsewhere by contract.

## Required output

- `exports/owner/<as_of>/inventory_capital_radar.json`
- `exports/owner/<as_of>/inventory_capital_radar.md`

## Minimum fields

- `generated_at`
- `as_of`
- `status`
- `trust_banner`
- `planning_snapshot`
- `summary`
- `action_buckets`
- `top_real_pos`
- `profit_scope`
- `sources`

## Stop conditions

- any hidden claim that stale planning is fresh
- any new capital math in the radar layer
- any widening from monitoring to execution without doc-first contract change
