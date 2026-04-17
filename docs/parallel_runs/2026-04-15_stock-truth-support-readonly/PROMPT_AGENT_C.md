PROMPT_AGENT_C

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/parallel_runs/2026-04-15_stock-truth-support-readonly/PLAN.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_stock-truth-support-readonly`

Your role

- read-only reconstruction-method analyst

Your job

- inspect whether the current stock reconstruction path is methodologically safe enough to use as provisional truth
- separate warehouse-stock truth from offer-stock truth and identify missing movement classes or model gaps

Required sources

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_po-state-integrity-gap-closure/agent_a_execution_log.md`
- `~/Docs/Autonomous_business/scripts/sync_current_stock.py`
- `~/Docs/Autonomous_business/scripts/reconcile_ledger_to_snapshot.py`
- `~/Docs/Autonomous_business/scripts/daily_pipeline_v2.py`
- `~/Docs/Autonomous_business/scripts/ingest_sales_v2.py`
- `~/Docs/Autonomous_business/docs/ops/STOCK_SNAPSHOT_RUNBOOK.md`
- `~/Docs/Oracle/Autonomous_business/2026-04-04/MEMO_stock_audit_handoff_2026-04-15.md`

Required questions

1. Is the current subtraction / movement-rebuild path inside the repo’s existing truth architecture, or drifting into ad hoc reconstruction?
2. What movement classes are definitely covered, and which may still be missing?
3. Can current reconstructed stock be used as provisional truth for downstream phases if clearly labeled?
4. What exact stopline should block continuation?

Rules

- do not modify repo files
- do not mutate any DB
- do not read Agent B's report before publishing your own first-pass findings

Output

- write findings to `agent_c_report.md`
- end with one short recommendation:
  - `CONTINUE_PROVISIONAL`
  - `CONTINUE_AFTER_NAMED_REVIEW`
  - `STOP_UNTIL_CANONICAL_STOCK`
