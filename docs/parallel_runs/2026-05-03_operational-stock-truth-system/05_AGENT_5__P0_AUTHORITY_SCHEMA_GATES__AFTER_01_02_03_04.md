# Agent 5 - P0 Authority, Schema, Gate Executor

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/05_AGENT_5__P0_AUTHORITY_SCHEMA_GATES__AFTER_01_02_03_04.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_1_authority_schema_contracts_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_2_stock_anchor_20pct_ledger_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_3_orders_sales_returns_qc_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_4_po_ads_cashflow_closeout.md`

Role:

- Sequential write-capable implementation agent.
- You are not alone in the codebase. Do not revert edits made by others. Reread live files before editing.
- Do not mutate `db/app.db` unless the plan and repo gates explicitly require it, and backup first.

Task:

- Implement P0 authority/schema validation gates and tests before behavior changes.
- Correct stale authority pointers required for implementation.
- Fix or quarantine `scripts/reconcile_ledger_to_snapshot.py` idempotency before Agent 6 can rely on it.

Required tests before changes:

- Authority-current gate fixture.
- Required runtime table/schema fixture.
- Reconcile adjustment idempotency fixture.

Suggested closeout:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_5_p0_authority_schema_gates_closeout.md`

Required verification:

- Focused pytest for touched validators.
- `python3 scripts/validate_params.py --strict`
- `scripts/check_no_db_tracked.sh`
- `scripts/lint_docs.sh` if docs are touched.

Stop if:

- Any required analyst closeout/report is missing.
- A formula/business rule must change but owning docs are not updated first.
- A write path lacks dry-run/apply/backout controls.
