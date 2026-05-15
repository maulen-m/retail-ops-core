# Agent 1 - AB Operational Source Refresh Analyst

Mode: read-only analyst.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-refresh-owner-review-wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-refresh-owner-review-wave/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_8.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_8_c3_daily_runner_owner_brief_closeout.md`
8. This assigned starter prompt.

## Mission

Find the safest, most efficient way to refresh AB operational source truth so these current blockers can be resolved:

- stale `stock_ledger`;
- stale `sales_fact_v2`;
- stale `fact_order_entries_kaspi`;
- stale `fact_cashflow_events`;
- stale `fact_cashflow_daily`;
- empty `order_status_event`;
- `ORDER_LIFECYCLE_MISSING_COMPLETED`;
- `ORDER_ENTRY_MISSING`.

## Allowed Work

You may read repo files, DB schema/data through read-only SQLite, local exports/logs, and source-refresh scripts.

You may run dry-run/read-only validation commands.

You must not mutate repo files, DB rows, workbooks, external repos, external systems, CRM workbooks, APIs, browser sessions, or env files.

Do not run live Kaspi import commands. Identify the commands and gates for Agent 6 instead.

If credentials are relevant, identify only variable names and required source paths. Do not print secret values.

## Required Analysis

Determine:

- which scripts currently populate or rebuild `order_status_event`, `fact_order_entries_kaspi`, `sales_fact_v2`, `stock_ledger`, `fact_cashflow_events`, and `fact_cashflow_daily`;
- which commands are dry-run safe and which require env-gated apply;
- whether current blockers are data-staleness blockers, missing script blockers, mapping blockers, or owner-review blockers;
- the exact serialized command sequence Agent 6 should use, including DB backup and validators;
- what can be refreshed locally without human owner action;
- what, if anything, requires the owner to review or approve.

## Required Output

Write a concise, source-backed closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files/scripts/tables inspected;
- exact recommended Agent 6 command sequence;
- expected source table effects;
- validation gates after each step;
- blockers;
- `OWNER_ATTENTION_REQUIRED` only if a human owner task is truly required, with exact paths and plain-English steps.

Do not read sibling agent reports before writing your own first-pass findings.

ASSIGNED CLOSEOUT: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_1_ab_operational_source_refresh_closeout.md`
