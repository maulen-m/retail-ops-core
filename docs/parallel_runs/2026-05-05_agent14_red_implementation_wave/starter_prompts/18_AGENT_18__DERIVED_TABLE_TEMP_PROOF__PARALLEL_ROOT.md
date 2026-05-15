# Agent 18 - Derived Table Temp Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_18_derived_table_temp_proof_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_agent14_red_implementation_wave/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/agent_15_derived_table_freshness_closeout.md`
7. this starter prompt

## Mission

Implement the derived-table replay temp-proof lane from Agent 15.

Current target as-of: `2026-05-04`.

You are not alone in the codebase. Do not revert edits made by others. Touch only your owned files. If an owned file has unexpected concurrent edits, stop and close out YELLOW/RED with evidence.

## Owned Write Set

Primary:

- `~/Docs/Autonomous_business/scripts/rebuild_sales_fact_v2_from_kaspi_entries.py`
- `~/Docs/Autonomous_business/scripts/materialize_stock_ledger_sales_from_sales_fact_v2.py`
- `~/Docs/Autonomous_business/scripts/rebuild_snapshot.py`
- `~/Docs/Autonomous_business/scripts/translate_orders_to_cashflow_events.py`

Optional only if needed:

- `~/Docs/Autonomous_business/scripts/rebuild_cashflow_calendar.py`
- focused tests under `~/Docs/Autonomous_business/tests/` for the scripts above.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- external-system writes;
- policy/C3 files owned by Agent 19;
- ads materializer files owned by Agent 20.

## Required Implementation

Write tests first, then code.

Required behavior:

1. `rebuild_sales_fact_v2_from_kaspi_entries.py`
   - delete scope must be limited to the requested `--start-date` and `--as-of` window;
   - entry rows remain preferred when available;
   - add `fact_orders_kaspi` header fallback for completed orders with SKU identity when entry rows are absent;
   - strict mode must fail if a completed gap-window order lacks required evidence.
2. Add `scripts/materialize_stock_ledger_sales_from_sales_fact_v2.py`
   - dry-run by default;
   - `--apply` requires `ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE=1`;
   - materializes idempotent `SALE` and `RETURN` stock-ledger rows from `sales_fact_v2`;
   - does not update/delete unrelated ledger rows.
3. `rebuild_snapshot.py`
   - add safe `--db` support and compare/dry-run behavior needed for temp proof.
4. `translate_orders_to_cashflow_events.py`
   - add `--output-path` or equivalent output routing so dry-runs do not write fixed repo exports.
5. `rebuild_cashflow_calendar.py`
   - patch only if needed so temp proof can rebuild full-history daily state safely from the correct event/sales source.

## Required Temp Proof

Use a copied temp DB, not production:

`/private/tmp/agent18_derived_table_temp_proof_20260504.db`

Prove as much of Agent 15's command sequence as your implementation safely supports. Do not production-apply.

## Required Gates

Run focused tests for your changed files.

Run relevant validators against the temp DB where supported:

- `python3 scripts/validate_operational_stock_schema.py --db <temp_db>`
- `python3 scripts/validate_order_cashflow_coverage.py --db <temp_db> --as-of 2026-05-04 --strict --json`
- `python3 scripts/validate_operational_stock_integration_gates.py --db <temp_db> --as-of 2026-05-04 --json`
- `sqlite3 <temp_db> 'PRAGMA integrity_check;'`

If a validator cannot target the temp DB yet, either patch it only if inside your owned scope or record it as a stopline.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files changed;
- tests written first;
- commands run and key outputs;
- temp DB path;
- whether `sales_fact_v2`, `stock_ledger`, `fact_inventory_snapshot_size`, `fact_cashflow_events`, and `fact_cashflow_daily` reach `2026-05-04` in temp proof;
- production apply stoplines.
