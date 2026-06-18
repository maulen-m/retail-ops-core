# Liquidation Register Contract

## Purpose
`G-LIQ-01` prevents liquidation sizing from using the stale 2026-05-31 frozen
book. Before any tranche rows are priced or uploaded, the system must rebuild a
fresh register from current inventory truth and re-bucket stock families into
the EXT-L01 A-E liquidation segments.

## Authority
- Gate: `G-LIQ-01`
- Owner decisions: `OD-005`, `OD-011`, `OD-018`
- Reconciliation references: `EXT-L01`, `CN-029`, `CN-032`, `CN-035`
- Reporter: `scripts/report_liquidation_register.py`
- Config: `config/validation/liquidation_register.json`

## Inputs
- Production SQLite DB opened in read-only mode: `db/app.db`
- Inventory truth: `fact_inventory_snapshot_size`
- Sales movement truth: `sales_fact_v2`
- COGS metadata: `dim_sku`
- Optional downstream guard input produced by this lane:
  `liquidation_segment_map.csv`

## Segment Definitions
- `A_COUNT_GATED`: stock family is blocked from markdown until a count-specific
  gate is satisfied. LINE51_WHITE belongs here until its physical-count
  extension closes.
- `B_ZERO_VELOCITY`: family has positive current stock and zero delivered units
  in the configured 30-day movement window.
- `C_SLOW_HIGH_COVER`: family has positive movement but days of cover is above
  the configured slow-cover threshold.
- `D_SIZE_MISALLOCATED`: family has movement in some sizes, while at least one
  positive-stock size has zero recent size-level movement.
- `E_STRATEGIC_NO_ACTION`: family is active enough that it is not a liquidation
  candidate under this register pass.

## Gate Rules
- `GREEN`: DB opens in read-only mode; latest inventory snapshot exists; basis
  age is at most the configured maximum; at least one positive-stock family is
  registered; every registered family has exactly one A-E segment; and no hard
  checks fail.
- `RED`: DB/config/schema is invalid, latest snapshot is stale or absent, no
  positive-stock family can be registered, or any registered family lacks a
  valid segment.

## Safety
This reporter is read-only against production truth. It must not write the
database, workbooks, Google Sheets, Telegram, Kaspi merchant surfaces, Repricer,
prices, stock, LaunchAgents, customer/operator messages, or any external
system. It may write local evidence artifacts only.
