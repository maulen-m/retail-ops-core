# Agent829 - Cashflow Cost / Source Decision

Gate target: `GREEN` if the 8 missing-cost rows and stale bank/manual source have exact source-backed decisions and copied-temp strict proof is ready. Use `YELLOW` if exact owner/source input is still required.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_source_decision_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_DECISION_WAVE_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_execution_wave/agent822_cashflow_source_cost_packet_closeout.md`
6. `~/Docs/Autonomous_business/exports/validation/mvos_execution_wave/20260515_111124/agent827_mvos_command_board/MVOS_OWNER_ACTION_LIST.md`
7. this starter prompt

## Assignment

Build the cashflow decision packet for the current source-decision wave.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent829_cashflow_cost_source_decision/`

Required report:

`~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent829_cashflow_cost_source_decision/CASHFLOW_COST_SOURCE_DECISION_PACKET.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_decision_wave/agent829_cashflow_cost_source_decision_closeout.md`

## Required Work

- Reproduce or source-copy the exact 8 missing-cost rows from Agent822.
- Inspect current SKU/cost source candidates for `LINE-31-TS`, `SUIT-21-TS`, `SUIT-31-LS`, and `SUIT-31-TS`.
- Inspect bank/manual source freshness and the exact route needed to make it fresh or decision-grade.
- Run strict translator dry-run on a copied DB only if useful; if apply-like flags are needed, they must target only a copied DB inside your evidence root.
- Produce an explicit decision matrix: source-backed cost exists, owner/source input required, or deterministic quarantine/exclusion required.

## Boundaries

No production DB write, workbook write, bank write, cash movement, supplier payment, owner publication, scheduler mutation, external write, ads, PO, price, stock, or lifecycle/status production repair. Do not invent costs or economics.

Gate: GREEN
