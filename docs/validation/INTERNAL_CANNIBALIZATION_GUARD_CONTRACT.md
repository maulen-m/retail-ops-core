# Internal Cannibalization Guard Contract

Scope: `G-WA-01` standing guard for liquidation markdown work across Repricer-managed Kaspi stores.

## Purpose

Liquidation markdowns must not make our own storefronts compete against each other, and they must not expose the same shared physical stock pool as a full markdown in multiple storefronts at once.

This contract is local and read-only. It does not authorize Repricer writes, Kaspi merchant uploads, price changes, stock changes, Telegram messages, Google Sheet writes, workbook writes, or production DB writes.

## Authority

- Gate: `G-WA-01`
- Owner decision: `OD-011`
- Green-path evidence reference: `EXT-L04`
- Dependencies already required by the gate: `G-STOCK-03` and `G-PRICE-04`

## Required Inputs

- Repricer current item export SQLite opened in read-only mode:
  - `~/Docs/Web_automation/data/repricer_items.sqlite`
- Lead-store map:
  - `config/validation/liquidation_lead_store_map.csv`
- Guard config:
  - `config/validation/internal_cannibalization_guard.json`

The lead-store map is mandatory before the first liquidation tranche upload. A header-only map keeps the gate `ARMED`, not `GREEN`.

## Lead-Store Map Schema

Required columns:

| column | meaning |
|---|---|
| `tranche_id` | liquidation tranche identifier |
| `sku_key` | canonical SKU key or family key |
| `size` | canonical size, or `ALL` only when a tranche is intentionally family-wide |
| `lead_store` | the single active markdown storefront for this tranche row |
| `allowed_follower_stores` | optional semicolon-separated follower stores allowed to remain visible for this row |
| `effective_from` | effective timestamp/date for the lead-store contract |
| `source_artifact` | source evidence path for the tranche row |
| `status` | `ACTIVE`, `PLANNED`, or `OFF` |
| `owner_decision_id` | must be the applicable owner decision, normally `OD-011` |
| `notes` | non-PII operator note |

## Guard Rules

1. The Repricer SQLite source must be present, readable in `mode=ro`, and fresh within the configured 7-day SLA.
2. For every active/available Repricer row, own-store competitor mids must already be present in `not_competitors`.
3. A missing own-store `not_competitors` entry is a hard failure.
4. Any missing own-store `not_competitors` entry where the own competitor price is lower than the current row price is an own-store undercut failure.
5. The lead-store map must have the exact required columns.
6. Active map rows must not duplicate `(sku_key, size)`.
7. Every active map row must name exactly one known lead store.
8. For active mapped liquidation rows, any visible non-lead store for the same row is a hard failure unless explicitly listed in `allowed_follower_stores`.

## Gate Semantics

- `GREEN`: source is fresh, own-store competitor exclusions are clean, and at least one active lead-store map row is present with zero exposure failures.
- `ARMED`: source is fresh and own-store competitor exclusions are clean, but no active liquidation lead-store map rows exist yet.
- `RED`: source/config/schema is invalid, source is stale, own-store competitor exclusions are missing, or mapped liquidation exposure violates the lead-store contract.

Visible price spread between own stores is reported as warning evidence. It is not a hard failure unless the row is in the active liquidation lead-store map or the own-store competitor is not excluded from Repricer matching.
