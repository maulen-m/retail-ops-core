# Agent 2 - Stock, Orders, Returns, QC, And Snapshot Truth

Assigned closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_2_c3_stock_orders_returns_qc_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/ops/OPERATIONAL_DECISION_POLICY_V1.md`
7. `~/Docs/Autonomous_business/config/operational_decision_policy.yaml`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/OWNER_QA_OPTION_C_INPUTS_20260503_203849_ALMT.md`
9. this assigned starter prompt.

## Mode

Read-only analyst. Do not edit repo files, `.claude/*`, DB, workbooks, env files, or external systems. The only allowed write is your assigned closeout.

## Mission

Define the complete C3 stock/order/returns/QC implementation contract.

Cover:

- current stock anchor and 20% proportional LINE51 baseline decrease;
- negative active stock normalized to zero with exception;
- pending does not reduce stock, dispatched/shipped reduces stock, delivered remains sold;
- cancelled, returned, and QC acceptance event logic;
- quarantine stock separation from active sellable stock;
- two white T-shirt `sku_key` values merging to one canonical key;
- unmapped SKU ignore/quarantine rule for at most two sales;
- stock snapshot rebuild source, lineage, and accuracy gates;
- tests Agent 7/8 must pass before decision-grade publication.

## Required Closeout Content

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files, DB tables, scripts, and reports inspected with absolute paths;
- exact recommended event model and snapshot math;
- list of current blockers to decision-grade stock;
- test plan and validation commands for implementation agents;
- confirmation that no repo, DB, env, external, or Web_automation files were modified.
