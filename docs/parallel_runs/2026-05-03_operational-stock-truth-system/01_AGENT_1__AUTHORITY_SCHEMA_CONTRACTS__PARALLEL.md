# Agent 1 - Authority, Schema, Contracts Analyst

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/01_AGENT_1__AUTHORITY_SCHEMA_CONTRACTS__PARALLEL.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-03/101657_TASK-000_operational-stock-orders-sales-system-review/Answer/Code_Captain_answer_2026-05-03_12_05_00.md`

Role:

- Read-only analyst.
- Do not modify repo files.
- Do not mutate `db/app.db`.
- Do not read sibling reports before publishing your first-pass report.

Focus:

- Authority conflicts.
- Schema/migration gaps.
- Stale docs/code references to v8/v2/v6/V15.
- Required contract updates before implementation.

Inspect:

- `~/Docs/Autonomous_business/docs/inventory/Master_Inventory_Rules_v9.md`
- `~/Docs/Autonomous_business/docs/protocol/active/PO_making_logic_v3.md`
- `~/Docs/Autonomous_business/docs/inventory/Sales_Data_Model_V16.md`
- `~/Docs/Autonomous_business/docs/inventory/Excel_UI_Contract_for_CRM_V1.md`
- `~/Docs/Autonomous_business/docs/ARCHITECTURE.md`
- `~/Docs/Autonomous_business/db/schema.sql`
- current migrations/tests if present
- code references to deprecated authority strings

Output:

- Write closeout/report to `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_1_authority_schema_contracts_closeout.md`.

Required report sections:

- READCHECK.
- Authority conflicts found.
- Missing required schema/tables/indexes.
- Tests Agent 5 should write first.
- Exact files Agent 5 should change, with risk notes.
- Stoplines.
- Standalone line: `Gate: <GREEN/YELLOW/RED>`.
