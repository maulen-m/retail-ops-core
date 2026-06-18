# Temporary OCR Stock Override for Marketplace Activation

This document is the current handoff for archive-to-active or inactive-to-active
offer agents while the main stock-truth refactor is running in parallel.

## Read This Report First

Stable report:

`exports/current/temporary_ocr_stock_override/temporary_stock_decision_latest.csv`

Companion files:

- `exports/current/temporary_ocr_stock_override/temporary_stock_decision_latest.json`
- `exports/current/temporary_ocr_stock_override/summary_latest.json`
- `exports/current/temporary_ocr_stock_override/README.md`

## Decision Rule

Use `activation_recommendation`:

- `ACTIVATE_OK_POSITIVE_TEMP_STOCK`: eligible to activate from temporary OCR stock.
- `ACTIVATE_OK_POSITIVE_PRIOR_FRESHEST_STOCK`: eligible only because the covered
  family had no direct newer OCR cell for that size and the prior freshest ledger
  value remains positive.
- `DO_NOT_ACTIVATE_*`: do not activate.
- `PARKED_MAPPING_PENDING_DO_NOT_ACTIVATE_FROM_THIS_REPORT`: do not activate from
  this report.

## Temporary Nature

This report is a temporary owner-approved operational layer. It is allowed to be
overridden by the main orchestrator/refactor output once that work returns a
conflict-free, up-to-date single source of truth.

## Safety Notes

- Missing OCR/manual sizes are not zero.
- Shared pools, such as Rombik men/kids `S`, must use the `stock_pool_id` and
  `alias_group` fields to avoid double counting.
- Mapping-flagged rows from the June 11 OCR batch are parked until exact product
  identity is proven.
- This report does not perform merchant writes. It only supplies stock decisions
  for the activation agent.
