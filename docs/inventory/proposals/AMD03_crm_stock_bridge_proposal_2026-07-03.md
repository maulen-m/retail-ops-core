# AMD-03 CRM Stock Bridge Proposal

Date: 2026-07-03
Status: design only; not implemented

## Goal

Bridge confirmed direct-CRM buyouts from CRM Postgres into `db/app.db`
`stock_ledger` so owner-approved off-platform sales decrement sellable stock.

## Source

- CRM Postgres buyout records with stable CRM order id, SKU identity, size, store,
  quantity, confirmation timestamp, and owner/ops approval status.
- Only finalized buyouts enter the bridge; drafts, quotes, returns, and cancelled
  records remain out of scope.

## Target

- Append-only `stock_ledger` rows.
- `event_type`: `ADJUSTMENT`.
- `reference_type`: `AMD03_CRM_BRIDGE`.
- `input_source`: `CRM_POSTGRES`.
- `idempotency_key`: deterministic from CRM order id, SKU id, store, and quantity.

## Cadence

- Run after CRM closeout sync and before daily inventory dashboards.
- Default cadence: hourly during ops hours, plus one end-of-day replay.
- Every run starts read-only, prints candidate rows, then applies only behind the
  repo write gate and `--apply`.

## Governed Writer

- Reuse the existing stock-ledger writer path rather than direct ad hoc SQL.
- Writer must reject unknown SKU ids, ambiguous store codes, duplicate
  idempotency keys, and negative quantities that are not explicit reversals.
- DB backup is mandatory before apply.

## Validation

- Before apply: candidate count, duplicate-key check, SKU/store resolution report.
- After apply: inserted ledger ids, per-SKU balance delta, `PRAGMA integrity_check`,
  and the inventory/dashboard validators that consume `stock_ledger`.
- Replay over the same source window must be no-op by idempotency.

## Owner Visibility

- Produce a compact daily owner report: CRM order id, SKU, size, store, quantity,
  ledger id, and before/after balance.
- Exceptions go to an owner-review queue rather than silent skips.

## Rollback

- Restore the pre-apply DB backup for full rollback.
- For scoped rollback, delete only bridge rows by the recorded idempotency keys
  and rerun the same validators.
