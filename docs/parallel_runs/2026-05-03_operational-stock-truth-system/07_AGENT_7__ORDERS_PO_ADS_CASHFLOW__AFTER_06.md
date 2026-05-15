# Agent 7 - Orders, PO, Ads, Cashflow Integration Executor

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/07_AGENT_7__ORDERS_PO_ADS_CASHFLOW__AFTER_06.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_6_stock_rebuild_20pct_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/orchestrator_gate_decision_after_agent6.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_3_orders_sales_returns_qc_report.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_4_po_ads_cashflow_report.md`

Role:

- Sequential write-capable implementation agent.
- You are not alone in the codebase. Do not revert edits made by others. Reread live files before editing.
- DB writes require backup, explicit apply gate, and rollback instructions.

Task:

- Integrate order lifecycle, sales mapping, return/QC quarantine, PO/inbound, ads coverage, and D1 cashflow gates into the stock truth system.
- Do not make owner profit/product-test/cargo/PO decisions green when ads/cash/return/inbound data is missing or stale.

Required tests before changes:

- Sales/order dedup fixture.
- Return/QC active-stock fixture.
- PO/inbound reconciliation fixture.
- Ads coverage fixture with STOREB missing/blocked.
- D1 delivered-order cashflow fixture.
- Cashflow roll-forward invariant fixture.

Suggested closeout:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system/agent_7_orders_po_ads_cashflow_closeout.md`

Required verification:

- Relevant focused pytest.
- `python3 scripts/validate_cashflow_invariants.py`
- `python3 scripts/validate_po_dashboard_invariants.py`
- `scripts/check_no_db_tracked.sh`
- `scripts/lint_docs.sh` if docs are touched.

Stop if:

- Agent 6 closeout is missing, or the orchestrator gate decision after Agent 6 is missing or not green.
- Missing ads coverage is treated as zero spend.
- Returned/cancelled units add active sellable stock without QC.
- PO inbound and stock inbound events double-count.
