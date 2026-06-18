# Return Comeback Rate Contract

Gate: G-RET-03

Purpose: replace the assumption-only returned-goods comeback band with a measured comeback rate after the return-QC loop has collected enough real staff QC telemetry.

## Formula

`comeback_rate = QC_passed_reentered_orders / eligible_returned_orders`

Definitions:

- `eligible_returned_orders`: distinct returned orders that are confirmed `returned_to_warehouse=1` and whose return date is at least `maturity_days` old.
- `QC_passed_reentered_orders`: distinct eligible returned orders with a return-QC event whose pass status is accepted/sellable and whose accepted active quantity is positive.
- Default maturity and telemetry requirements are both 30 days.

## Status Semantics

- GREEN: G-RET-02 is green, at least one eligible returned order exists, return-QC telemetry covers at least 30 days, and the measured comeback rate is published.
- ARMED: the report exists but QC telemetry, maturity window, eligible denominator, or dependency gate is not ready.
- RED: required source tables are missing or the report detects internally inconsistent measurement.

The report is read-only against production DB and does not infer physical QC outcomes. Staff/owner QC facts must enter through the governed return-QC writer.
