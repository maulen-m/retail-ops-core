# Portfolio Completeness Contract

## Purpose
Define when portfolio health is decision-grade. Prevent false-green status when active SKUs are missing required operational truth.

## Active Portfolio Scope
- Source: `dim_sku.active_flag = 1`
- Key: `sku_key`
- All checks are evaluated on active `sku_key` only.

## Required Coverage Signals
For each active SKU, the following must be present:
- Stock coverage: SKU appears in latest `fact_inventory_snapshot_size.snapshot_date <= as_of`.
- Demand coverage: required only for operational-demand SKUs:
  - `current_stock > 0` in latest inventory snapshot, or
  - `fact_sales.quantity > 0` within the last 60 days up to `as_of`.
  For these SKUs, row must exist in latest `fact_demand_estimates.cutoff_date <= as_of`.
  SKUs with `inbound_stock > 0` but no current stock/sales are labeled `pending_launch` and reported explicitly.
- Unit economics coverage: either:
  - `dim_sku.cogs_kzt > 0`, or
  - `dim_sku.base_cost_cny > 0` and `dim_sku.weight_kg > 0`.

## Artifact Contract
Builder:
- `scripts/build_portfolio_completeness_report.py`

Outputs:
- `exports/daily/<YYYY-MM-DD>/portfolio_completeness_report.json`
- `exports/daily/<YYYY-MM-DD>/portfolio_completeness_report.md`

Required JSON fields:
- `as_of`
- `status` (`GREEN` or `RED`)
- `ok`
- `active_skus`
- `latest_snapshot_date`
- `latest_demand_cutoff`
- `stock_covered`
- `demand_covered`
- `demand_required_skus`
- `pending_launch_count`
- `unit_econ_covered`
- `coverage_pct`
- `missing_stock_count`
- `missing_demand_count`
- `missing_unit_econ_count`
- `missing_stock`
- `missing_demand`
- `missing_unit_econ`
- `pending_launch`

## Fail-Closed Rule
- Strict mode (`--strict`) must exit non-zero when any missing count is non-zero.
- Missing required input tables must be hard failures.

## Integration Rule
- Domain scorecard build and System Doctor strict checks must fail if this contract is red.
