# Agent 6 - Stock Rebuild And 20% Adjustment Executor

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/06_AGENT_6__STOCK_REBUILD_20PCT__AFTER_05.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_5_p0_authority_schema_gates_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/orchestrator_gate_decision_after_agent5.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_2_stock_anchor_20pct_ledger_report.md`

Role:

- Sequential write-capable implementation agent.
- You are not alone in the codebase. Do not revert edits made by others. Reread live files before editing.
- DB writes require backup, explicit apply gate, and rollback instructions.

Task:

- Implement the stock anchor and one-time 20% adjustment workflow.
- Keep the stock anchor immutable.
- Generate adjustment events in `stock_ledger` or tested equivalent.
- Rebuild current stock snapshot from ledger mode only.
- Produce owner-facing stock output with trust banner or blocked status.

Required tests before changes:

- 20% rounding fixture.
- Adjustment idempotency fixture.
- No-negative-stock fixture.
- Ledger-to-snapshot fixture.
- High-risk family exception fixture.

Suggested closeout:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_6_stock_rebuild_20pct_closeout.md`

Required verification:

- Focused stock tests.
- Ledger duplicate validation.
- No-negative validation.
- `scripts/check_no_db_tracked.sh`
- `scripts/lint_docs.sh` if docs are touched.

Stop if:

- Agent 5 closeout is missing, or the orchestrator gate decision after Agent 5 is missing or not green.
- Anchor approval is absent.
- The 20% batch appears already applied.
- High-risk SKU/family review is not represented.
