# ORDER_ENTRY_NO_REAL_ENTRY_QUARANTINE_COPIED_TEMP_V1

Status: active copied-temp contract draft.

Accepted at: `2026-05-22T00:00:00+05:00`

Accepted by: owner-approved non-production MVOS blocker-closure envelope; requires CodeCaptain review before any production preflight/apply discussion.

## Purpose

This contract allows strict order-entry recovery to pass in copied-temp proof only when every remaining unrecovered target row is explicitly retained as `RETAINED_ORDER_ENTRY_QUARANTINE`.

It does not create item-entry product truth. It exists to prevent fake recovery for rows where local sources have header/order context but no real Kaspi item-entry evidence.

## Scope

Allowed scope:

- copied validation DB only;
- target source `fact_orders_kaspi`;
- stores `STOREB`, `ACMEWEAR`, and `UNIVERSAL`;
- as-of date `2026-05-18`;
- entry-required order rows only;
- accepted no-entry quarantine CSV with `copied_temp_only=true` and `production_write_authorized=false`.

Forbidden scope:

- production `db/app.db`;
- production preflight or production apply;
- workbook mutation;
- scheduler, LaunchAgent, or cron mutation;
- source-pointer writes;
- external writes;
- owner publication;
- synthetic item-entry insertion;
- treating header-only SKU context as product truth.

## Accepted Quarantine Rows

The copied-temp strict pass is allowed only when these exact rows are the full remaining unrecovered target set:

| order_id | store_code | retained context | required treatment |
| --- | --- | --- | --- |
| `922898360` | `UNIVERSAL` | candidate header context: `CL_OC_MEN_LINE52_BLACK_2XL` | retain; do not insert into `fact_order_entries_kaspi` |
| `923528055` | `UNIVERSAL` | candidate header context: `CL_NEW-CLO_MEN_NIKE-SHIRT_WHITE_54` | retain; do not insert into `fact_order_entries_kaspi` |

If any other unrecovered target row appears, strict recovery must fail closed.

If either accepted row receives real item-entry evidence later, the real evidence path must supersede this quarantine contract for that row.

## Required Validation

The proof lane must run:

```bash
python3 scripts/recover_order_entries_from_evidence.py \
  --db <copied-db> \
  --target-source fact_orders_kaspi \
  --start-date 2026-05-05 \
  --as-of 2026-05-18 \
  --stores STOREB,ACMEWEAR,UNIVERSAL \
  --entry-required-only \
  --accepted-no-entry-quarantine-csv <accepted-csv> \
  --recovery-ts 2026-05-18T23:59:59+05:00 \
  --apply \
  --strict
```

Expected behavior:

- `strict.passed=true`;
- `strict.passed_by_accepted_no_entry_quarantine=true`;
- `quarantine.target_rows=2`;
- `accepted_no_entry_quarantine.accepted_target_rows=2`;
- `apply.inserted_entry_rows=0`;
- no row is inserted into `fact_order_entries_kaspi` for `922898360` or `923528055`.

## Stoplines

- Do not insert fake item-entry rows.
- Do not use SKU, size, offer text, or header context as a substitute for real item-entry evidence.
- Do not apply this contract to production `db/app.db`.
- Do not claim source truth green for owner publication from this contract alone.
- Keep the retained rows visible in blocker and closeout surfaces.
