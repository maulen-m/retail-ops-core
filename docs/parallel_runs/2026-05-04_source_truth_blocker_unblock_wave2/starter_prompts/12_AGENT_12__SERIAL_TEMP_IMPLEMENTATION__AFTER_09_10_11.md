# Agent 12 - Serialized Temp Implementation After Agents 9-11

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_12_serial_temp_implementation_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_source_truth_blocker_unblock_wave2/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_9_lifecycle_residual_source_truth_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_10_po_inbound_line_grain_source_truth_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_11_ads_source_refresh_coverage_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_8.md`
9. this starter prompt

## Mission

Implement the smallest safe source-backed repairs required by Agents 9-11 and prove them on a temp DB or isolated evidence root.

Do not apply production `db/app.db`. Agent 13 owns production apply.

## Write Boundary

Allowed writes:

- repo code/tests required for the repair;
- temp DB and evidence under `/private/tmp/agent12_source_truth_temp.sqlite`;
- validation outputs under `~/Docs/Autonomous_business/exports/validation/source_truth_blocker_wave2_agent12/`;
- your assigned closeout.

Forbidden writes:

- production `~/Docs/Autonomous_business/db/app.db`;
- `.env`;
- workbook/source evidence edits;
- external-system writes;
- ad settings, bids, budgets, campaign state, merchant state, supplier/payment state.

## Required Work Pattern

1. Read Agents 9-11 closeouts.
2. If any required source evidence is missing, stop YELLOW or RED with exact owner/source requirement.
3. Write tests before code changes.
4. Implement only the minimum source-backed materializers/importers needed.
5. Copy production DB to `/private/tmp/agent12_source_truth_temp.sqlite`.
6. Run dry-run first, then apply only to the temp DB with explicit env gates.
7. Rerun validators against the temp DB.

## Expected Repair Surfaces

Possible lifecycle surface:

- `scripts/materialize_order_status_events_from_kaspi_orders.py`
- tests around residual completed lifecycle coverage.

Possible PO/inbound surface:

- `scripts/sync_po_parts_from_inbound_calendar.py`
- new narrow materializer if needed, for example `scripts/materialize_po_inbound_line_grain_c3.py`
- tests for line-grain references and inbound double-count prevention.

Possible ads surface:

- new narrow importer if needed, for example `scripts/import_ads_source_refresh_from_webauto.py`
- tests for store normalization, no fake zero rows, `COVERED` vs `NO_SPEND_VERIFIED`, and mapping through `dim_kaspi_article_map`.

## Required Validators

Run at minimum:

```bash
python3 -m pytest -q tests/test_operational_stock_integration_gates.py
python3 scripts/validate_operational_stock_integration_gates.py --db /private/tmp/agent12_source_truth_temp.sqlite --as-of 2026-05-03 --json
python3 scripts/validate_cashflow_invariants.py --db /private/tmp/agent12_source_truth_temp.sqlite
scripts/lint_docs.sh
scripts/check_no_db_tracked.sh
```

Add focused tests for any new/changed scripts.

## Closeout Requirements

Your closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files changed;
- temp DB path;
- commands run;
- before/after blocker counts on temp DB;
- exact Agent 13 production apply command sequence;
- rollback considerations;
- remaining blockers, if any.

Gate meaning:

- GREEN: temp implementation clears the target source blockers or narrows them to explicitly accepted non-publication blockers, with tests passing.
- YELLOW: implementation is partly complete but source gaps remain.
- RED: implementation is unsafe or validator regression occurs.
