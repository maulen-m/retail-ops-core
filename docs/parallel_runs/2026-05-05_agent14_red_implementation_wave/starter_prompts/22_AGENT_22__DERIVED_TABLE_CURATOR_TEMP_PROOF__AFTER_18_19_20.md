# Agent 22 - Derived Table Curator Temp Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_22_derived_table_curator_temp_proof_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_agent14_red_implementation_wave/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENTS_18_20.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_18_derived_table_temp_proof_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/agent_15_derived_table_freshness_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/agent_8_serialized_release_apply_agents4_7_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_8.md`
11. this starter prompt

## Mission

Complete Agent 18's derived-table temp proof with the D1 translator baseline explicitly attributed and accepted for this lane.

Current target as-of: `2026-05-04`.

You are not alone in the codebase. Do not revert edits made by others. Touch only your owned files. If an owned file has unexpected edits other than the already-attributed D1 translator baseline, stop and close out YELLOW/RED with evidence.

## Baseline Decision

Do not stop merely because `scripts/translate_orders_to_cashflow_events.py` is dirty. The large StageCode/D1 diff is attributed to the accepted Agents 4-7 / Agent 8 release lane and may be used as the current baseline.

You must still review it enough to avoid breaking it, and any new changes to it must be narrow, tested first, and documented.

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
- ads materializer files owned by Agent 23;
- C3 policy files owned by Agent 19.

## Required Implementation

Write tests first, then code.

Required behavior:

1. `rebuild_sales_fact_v2_from_kaspi_entries.py`
   - delete scope must be limited to requested `--start-date` and `--as-of`;
   - entry rows remain preferred when available;
   - add `fact_orders_kaspi` header fallback for completed orders with SKU identity when entry rows are absent;
   - strict mode fails if a completed gap-window order lacks required evidence.
2. Add or finish `scripts/materialize_stock_ledger_sales_from_sales_fact_v2.py`
   - dry-run by default;
   - `--apply` requires `ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE=1`;
   - materializes idempotent `SALE` and `RETURN` stock-ledger rows from `sales_fact_v2`;
   - does not update/delete unrelated ledger rows.
3. `rebuild_snapshot.py`
   - add safe `--db` support and compare/dry-run behavior needed for temp proof.
4. `translate_orders_to_cashflow_events.py`
   - add only the narrow output routing needed by Agent 15, such as `--output-path` or equivalent, without regressing StageCode D1 behavior.
5. `rebuild_cashflow_calendar.py`
   - patch only if required so a full-history temp rebuild can reach `2026-05-04` safely.

## Required Temp Proof

Use a copied temp DB, not production:

`/private/tmp/agent22_derived_table_curator_temp_proof_20260504.db`

Prove whether these tables can reach `2026-05-04`:

- `sales_fact_v2`;
- `stock_ledger`;
- `fact_inventory_snapshot_size`;
- `fact_cashflow_events`;
- `fact_cashflow_daily`.

## Required Gates

Run focused tests for your changed files.

Run relevant temp validators:

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
- whether each required table reached `2026-05-04`;
- how the pre-existing D1 translator baseline was handled;
- production apply stoplines.
