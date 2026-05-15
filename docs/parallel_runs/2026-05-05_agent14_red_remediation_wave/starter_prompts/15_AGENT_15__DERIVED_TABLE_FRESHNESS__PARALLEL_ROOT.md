# Agent 15 - Derived Table Freshness Remediation Plan

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/agent_15_derived_table_freshness_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_agent14_red_remediation_wave/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_14_c3_owner_brief_rematerialization_closeout.md`
7. `~/Docs/Autonomous_business/exports/operational_stock_daily_truth/2026-05-03/source-truth-wave2-final/owner_blocked_brief.md`
8. this starter prompt

## Mission

Read-only diagnosis of stale operational derived tables and exact next implementation plan.

Focus on:

- `sales_fact_v2` max order date `2026-04-15`
- `stock_ledger` max event date `2026-04-15`
- `fact_cashflow_daily` max date `2026-04-15`
- `fact_order_entries_kaspi` reaching `2026-05-04`

Determine the safest way to replay or rebuild derived sales, stock, and cashflow daily state to the latest complete as-of date, likely `2026-05-04`, without breaking Agent 13's lifecycle/PO production fixes.

## Write Boundary

Read-only against production `db/app.db`.

Allowed writes:

- your closeout;
- optional read-only query outputs under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/agent_15_evidence/`.

Forbidden:

- production DB writes;
- workbook edits;
- external-system writes;
- code changes.

## Required Work

1. Identify current source max dates and row counts.
2. Inventory existing scripts that can rebuild:
   - `sales_fact_v2`;
   - `stock_ledger` sales/order deltas;
   - `fact_cashflow_daily`.
3. Determine whether a temp DB proof can be run in the next lane, and list exact commands.
4. Explicitly state whether the next lane should use as-of `2026-05-04` instead of `2026-05-03`.
5. Identify tests/validators required before production apply.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- current table max dates and row counts;
- exact recommended next commands;
- scripts to inspect or patch;
- temp DB proof plan;
- production apply stoplines.
