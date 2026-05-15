# Plan - Order Entry API Archive 28 Fetch

Timestamp: `2026-05-14T20:00:26+0500`

## Objective

Fetch real item-entry evidence for the current `28` quarantined order-entry rows using the existing Kaspi API archive method, then rerun the order-entry recovery dry-run on the current boundary.

## Execution Agent

- Agent806: API archive fetch plus read-only recovery dry-run.

## Scope

Allowed:

- Read current repo docs/scripts/evidence.
- Read `.env` only for existing API credentials needed by `scripts/export_kaspi_archive_history.py`.
- Perform read-only Kaspi API archive fetches for `STOREB`, `ACMEWEAR`, and `UNIVERSAL`.
- Write new evidence under `exports/validation/order_entry_owner_phrase_review/20260514_200026_agent806_api_archive_refetch/`.
- Write the assigned closeout under `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_order-entry-owner-phrase-review/`.

Not allowed:

- No production DB apply.
- No `--apply`.
- No workbook mutation.
- No scheduler mutation.
- No Google/Telegram/Kaspi write action.
- No ads, cash, stock, PO, price, owner-publication, or owner-approval action.
- No secrets in closeout or evidence.

## Success Gate

`GREEN` if the new API archive evidence makes the strict dry-run pass with:

- `strict.passed=true`
- `quarantine.target_rows=0`
- `source_hierarchy=["API_RAW_ORDER_ENTRIES"]`
- no production mutation

`YELLOW` if some rows are recovered but quarantine remains.

`RED` if API archive fetch cannot run safely, credentials/API access fail completely, or any protected surface is mutated.
