# Dark Family Relist State Contract

Gate: G-DARK-01

Purpose: prove OD-033 dark-family relists are live only for verified on-hand sizes, after a fresh offer-state readback.

## Inputs

- Production DB opened read-only for current stock snapshot.
- Local Repricer offer-state SQLite as the live offer-state readback.
- Green-path scoreboard/dashboard gate states.
- OD-033 relist scope.

## Checks

1. Dependency stack green: G-STOCK-03.
2. Current stock snapshot exists.
3. Repricer offer-state source is fresh.
4. Every in-scope positive-stock size is buyable.
5. Every excluded or zero-stock size is not buyable.
6. No relist execution is claimed without live offer-state evidence.

## Status Semantics

- GREEN: fresh offer-state readback exists, stock truth is green, all required positive-stock sizes are buyable, and no excluded or zero-stock sizes are buyable.
- ARMED: source evidence exists but relist execution evidence is incomplete without a live mismatch.
- RED: source evidence is missing/stale or live offer state conflicts with OD-033 stock/exclusion scope.

This report is read-only. It does not upload pricelists, change prices, write stock, write DB/workbooks, send messages, or mutate external systems.
