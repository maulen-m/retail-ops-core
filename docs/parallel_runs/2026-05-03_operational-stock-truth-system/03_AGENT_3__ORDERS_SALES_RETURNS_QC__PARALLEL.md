# Agent 3 - Orders, Sales, Returns, QC Analyst

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/03_AGENT_3__ORDERS_SALES_RETURNS_QC__PARALLEL.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-03/101657_TASK-000_operational-stock-orders-sales-system-review/Answer/Code_Captain_answer_2026-05-03_12_05_00.md`

Role:

- Read-only analyst.
- Do not modify repo files.
- Do not mutate `db/app.db`.
- Do not read sibling reports before publishing your first-pass report.

Focus:

- Kaspi order lifecycle status truth.
- Sales mapping and deduplication.
- Delivery-dispatched versus pending-to-ship stock semantics.
- Returns/cancellations/QC quarantine behavior.
- Ignored unmapped SKU rule for maximum 2 sales.

Inspect:

- `~/Docs/Autonomous_business/docs/KASPI_ORDER_LIFECYCLE_AND_STATUS_CONTRACT.md`
- `~/Docs/Autonomous_business/docs/inventory/Sales_Data_Model_V16.md`
- `~/Docs/Autonomous_business/docs/KASPI_API_INTEGRATION.md`
- order import/sales ingest scripts.
- tests around sales/order/cashflow translation.
- WebUI archive CSV references from the external pack, read-only.

Output:

- Write closeout/report to `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_3_orders_sales_returns_qc_closeout.md`.

Required report sections:

- READCHECK.
- Canonical lifecycle event model recommendation.
- Sales mapping gaps.
- Return/QC stock-addback rules.
- Tests Agent 7 should write first.
- Stoplines before sales events drive stock.
- Standalone line: `Gate: <GREEN/YELLOW/RED>`.
