# Forecast Accuracy Bias Loop Contract

Gate: G-PO-03

Purpose: keep auto-PO restart blocked until the monthly forecast review publishes fresh MAPE, WAPE/WMAPE, and signed-bias evidence that the restart gate can consume.

## Checks

The report treats these as the current proof surface:

1. Dependency stack green: G-PO-02.
2. A monthly forecast accuracy CSV report exists.
3. The monthly report is fresh enough for the 30-day cadence.
4. MAPE is published and below the configured threshold.
5. WAPE/WMAPE is published and below the configured threshold.
6. Signed bias is published and within the configured absolute threshold.
7. The auto-PO consumer still reads `fact_forecast_accuracy`.

## Status Semantics

- GREEN: all checks pass.
- ARMED: the report exists but one or more checks are not ready.
- RED: required source tables or report artifacts are missing in a way that prevents evaluation.

This report does not restart auto-PO, create PO drafts, create PO executions, purchase stock, mutate DB/workbook/external systems, or send alerts.
