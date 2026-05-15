# Launch Order

Run Agents 1-4 in parallel. They are read-only analysts.

1. Agent 1:
   - Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/01_AGENT_1__AUTHORITY_SCHEMA_CONTRACTS__PARALLEL.md`.
2. Agent 2:
   - Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/02_AGENT_2__STOCK_ANCHOR_20PCT_LEDGER__PARALLEL.md`.
3. Agent 3:
   - Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/03_AGENT_3__ORDERS_SALES_RETURNS_QC__PARALLEL.md`.
4. Agent 4:
   - Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/04_AGENT_4__PO_ADS_CASHFLOW__PARALLEL.md`.

Run Agents 5-8 sequentially. They are write-capable implementation agents.

5. Agent 5:
   - After Agents 1-4 publish closeouts, execute `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/05_AGENT_5__P0_AUTHORITY_SCHEMA_GATES__AFTER_01_02_03_04.md`.
6. Agent 6:
   - After Agent 5 closeout is complete and green, execute `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/06_AGENT_6__STOCK_REBUILD_20PCT__AFTER_05.md`.
7. Agent 7:
   - After Agent 6 closeout is complete and green, execute `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/07_AGENT_7__ORDERS_PO_ADS_CASHFLOW__AFTER_06.md`.
8. Agent 8:
   - After Agent 7 closeout is complete and green, execute `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/08_AGENT_8__DAILY_RUNNER_RELEASE__AFTER_07.md`.

Shared handoff folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system`

Hard rule:

- Agents 5-8 must not run in parallel unless a new owner-approved split defines isolated worktrees, disjoint write sets, and serialized DB/apply gates.
