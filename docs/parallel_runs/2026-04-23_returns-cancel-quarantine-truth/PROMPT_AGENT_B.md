# PROMPT_AGENT_B — Archive/API Lifecycle Coverage

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_returns-cancel-quarantine-truth/PLAN.md`
5. this prompt

Shared handoff folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth`

## Role

You are Agent B, read-only analyst.

Your focus is Archive/API lifecycle coverage for cancelled and returned orders after 2026-02-01.

## Independence Rule

Do not read Agent C's report before publishing your own first-pass report.

## Task

Determine whether the existing API/archive/WebUI methods can identify, date, and line-enrich:

- `CANCELLED`
- `CANCELLING`
- `KASPI_DELIVERY_RETURN_REQUESTED`
- `RETURNED`
- `returnedToWarehouse`
- order status-change dates
- SKU/size/quantity per order line

Inspect only what is needed, likely:

- `scripts/export_kaspi_archive_history.py`
- `scripts/export_sales_archive_statusdate_mapped.py`
- `scripts/validate_webui_archive_vs_current_db.py`
- `scripts/rebuild_sales_fact_v2_from_kaspi_entries.py`
- `core/integrations/kaspi_order_stage.py`
- `core/sync/order_sync_engine.py`
- `docs/KASPI_ORDER_LIFECYCLE_AND_STATUS_CONTRACT.md`
- `docs/KASPI_API_INTEGRATION.md`
- relevant DB schema/read-only SQL if useful

## Required Findings

Your report must answer:

1. Which source is strongest for each lifecycle state?
2. Which source has the best status-change date?
3. Which source has the best SKU/size/quantity line detail?
4. What can be trusted from API/archive immediately?
5. What cannot be known without future employee QC?
6. What exact columns should Agent A include in `return_cancel_backlog.csv`?
7. What exact commands should Agent A run first, if any current scripts already exist?

## Constraints

- Do not modify repo files.
- Do not mutate `db/app.db`.
- Do not produce final business truth; produce source-backed guidance for Agent A.
- Keep the report concise and actionable.

## Output

Write:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth/agent_b_report.md`

Include:

- sources inspected
- commands run
- lifecycle coverage table
- recommended implementation path for Agent A
- open risks
