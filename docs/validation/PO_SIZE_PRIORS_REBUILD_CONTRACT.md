# PO Size Priors Rebuild Contract

Gate: G-PO-02

Purpose: make auto-PO restart impossible until size priors and forecast evidence are rebuilt under the accepted EXT-S01/EXT-S02/EXT-S03 rules.

## Seven Checks

The report treats these as the current seven-test proof surface:

1. Dependency stack green: G-COGS-04, G-STOCK-03, and G-RET-02.
2. `dim_size_probability` has the expected prior levels.
3. Size priors are fresh.
4. Forecast accuracy evidence is fresh.
5. Forecast MAPE is below threshold.
6. Demand forecast evidence is fresh.
7. PO dashboard invariants pass.

## Status Semantics

- GREEN: all seven checks pass.
- ARMED: the report exists but one or more checks are not ready.
- RED: required source tables are missing or a check command errors in a way that prevents evaluation.

This report does not restart auto-PO, create PO drafts, create PO executions, purchase stock, or mutate DB/workbook/external systems.
