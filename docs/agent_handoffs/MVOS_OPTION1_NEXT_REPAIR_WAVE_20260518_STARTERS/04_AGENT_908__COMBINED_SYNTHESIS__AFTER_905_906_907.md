# Agent908 - Combined Copied-Temp Synthesis Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent908_combined_synthesis_proof_closeout.md`

Assigned evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent908_combined_synthesis_proof_evidence`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_option1_next_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/04_AGENT_908__COMBINED_SYNTHESIS__AFTER_905_906_907.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent905_order_entry_source_hierarchy_repair_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent906_stock_po_shortage_repair_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent907_cashflow_source_freshness_integration_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/ORCHESTRATOR_REVIEW_AFTER_905_907.md`

## Launch Gate

Do not execute this starter until the orchestrator explicitly launches it after reviewing Agents `905`, `906`, and `907`.

If any dependency closeout is missing, stop `RED`.

If any dependency is `RED`, stop `RED`.

If any dependency is `YELLOW`, run only a synthesis and CodeCaptain packet lane. Do not claim copied-temp green.

Current launch decision: Agents `905`, `906`, and `907` are all `YELLOW`, so this run is synthesis/CodeCaptain-packet only.

## Mission

Run one combined copied-temp proof attempt using the accepted boundary and the results of Agents `905`, `906`, and `907`.

## Required Work

1. Verify accepted DB/workbook boundary at start.
2. Create one copied DB for synthesis.
3. Apply only accepted copied-temp repair artifacts from Agents `905`, `906`, and `907`.
4. Run the relevant 10/10 contract validators for the declared scope.
5. Build:
   - gate matrix;
   - source-freshness matrix;
   - retained-blocker matrix;
   - production-authority matrix;
   - CodeCaptain packet recommendation.
6. Write closeout with `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

## Gate Rules

- `GREEN`: all required copied-temp validators pass for declared scope and no unaccepted blocker is hidden.
- `YELLOW`: useful synthesis exists but retained blockers remain or CodeCaptain review is required.
- `RED`: dependency red/missing, boundary drift, production mutation, hidden blocker, or false green.

## Non-Authorization

This task does not authorize production DB writes, workbook writes, scheduler changes, external writes, owner publication, cash movement, supplier payment, PO commitment, stock changes, price changes, or production apply.
