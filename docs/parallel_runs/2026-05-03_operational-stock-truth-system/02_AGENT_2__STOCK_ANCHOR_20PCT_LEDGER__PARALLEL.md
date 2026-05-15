# Agent 2 - Stock Anchor, 20% Adjustment, Ledger Analyst

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/02_AGENT_2__STOCK_ANCHOR_20PCT_LEDGER__PARALLEL.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-03/101657_TASK-000_operational-stock-orders-sales-system-review/Answer/Code_Captain_answer_2026-05-03_12_05_00.md`

Role:

- Read-only analyst.
- Do not modify repo files.
- Do not mutate `db/app.db`.
- Do not read sibling reports before publishing your first-pass report.

Focus:

- Most reliable stock anchor.
- One-time 20% stock decrease design.
- Ledger/snapshot rebuild path.
- Current stock snapshot storage and rebuild evidence.
- High-risk families: `LINE52 4XL`, `T-SHIRT BLACK S/M/L`, LINE51/LINE61 owner truth.

Inspect:

- stock audit workbooks and memos referenced by the external answer.
- `scripts/sync_current_stock.py`
- `scripts/rebuild_snapshot.py`
- `scripts/reconcile_ledger_to_snapshot.py`
- `core/calc/stock_timeline.py`
- stock audit code/tests if present.
- `fact_inventory_snapshot_size` and `stock_ledger` usage, read-only only.

Output:

- Write closeout/report to `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_2_stock_anchor_20pct_ledger_closeout.md`.

Required report sections:

- READCHECK.
- Recommended anchor and confidence level.
- 20% adjustment batch contract.
- Rounding/idempotency tests Agent 6 should write first.
- Ledger/snapshot rebuild risks.
- High-risk SKU/family exception list.
- Stoplines before apply.
- Standalone line: `Gate: <GREEN/YELLOW/RED>`.
