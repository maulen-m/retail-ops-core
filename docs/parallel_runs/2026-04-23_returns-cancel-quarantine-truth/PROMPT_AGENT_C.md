# PROMPT_AGENT_C — Inventory And Quarantine Accounting Design

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_returns-cancel-quarantine-truth/PLAN.md`
5. this prompt

Shared handoff folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth`

## Role

You are Agent C, read-only analyst.

Your focus is the safest inventory/accounting model for returns and cancellations when manual QC is not available yet.

## Independence Rule

Do not read Agent B's report before publishing your own first-pass report.

## Task

Design the minimum safe truth model for:

- sales counting
- active stock movement
- quarantine stock
- future employee QC queue
- validator stoplines
- cashflow/profit implications

Business reality:

- since about 2026-02-01, returned/cancelled items have not been manually recounted back into active stock
- returned items are physically collected in a warehouse section
- employee must inspect item, condition, and size before active restock
- this phase must rely only on existing processing/data, not new manual results

Inspect only what is needed, likely:

- `docs/inventory/Master_Inventory_Rules_v9.md`
- `docs/inventory/Sales_Data_Model_V16.md`
- `docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
- `docs/KASPI_ORDER_LIFECYCLE_AND_STATUS_CONTRACT.md`
- `scripts/rebuild_sales_fact_v2_from_kaspi_entries.py`
- inventory snapshot / ledger scripts if relevant
- current DB schema read-only if useful

## Required Findings

Your report must answer:

1. What is the correct active-stock effect for each lifecycle bucket?
2. What is the correct quarantine-stock effect for each lifecycle bucket?
3. What should never be automatically restocked?
4. What should the future employee QC queue contain?
5. What ledger/table/event model is safest if Agent A implements one?
6. What env/CLI gates are needed for any write path?
7. What validators or fail-closed checks should block decision-grade stock?

## Constraints

- Do not modify repo files.
- Do not mutate `db/app.db`.
- Do not assume returned stock is active sellable stock.
- Do not invent employee QC outcomes.

## Output

Write:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth/agent_c_report.md`

Include:

- sources inspected
- commands run
- lifecycle-to-stock-effect matrix
- proposed quarantine ledger / export contract
- exact next action for Agent A
- open risks
