# Agent 6 - Phase 1 Synthesis After Root Agents

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent6_phase1_synthesis_closeout.md`

## Dependency

Agents 1, 2, 3, 4, and 5 have written closeouts and the Main Orchestrator has reviewed them. Execute this synthesis now.

Root closeouts:

- Agent 1 `YELLOW`: `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent1_physical_stock_po_route_closeout.md`
- Agent 2 `YELLOW`: `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent2_order_sales_identity_route_closeout.md`
- Agent 3 `YELLOW`: `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent3_single_truth_po_money_route_closeout.md`
- Agent 4 `GREEN`: `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent4_cashflow_freshness_route_closeout.md`
- Agent 5 `YELLOW`: `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent5_ads_truth_route_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/current/FINAL_10_OUT_OF_10_EXECUTION_PLAN.md`
4. `~/Docs/Autonomous_business/docs/current/CURRENT_BLOCKER_BOARD.tsv`
5. `~/Docs/Autonomous_business/docs/current/CURRENT_GATE_MATRIX.tsv`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-21_mvos_phase1_clean_then_blocker_closure/CLEAN_FIRST_BOUNDARY.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent1_physical_stock_po_route_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent2_order_sales_identity_route_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent3_single_truth_po_money_route_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent4_cashflow_freshness_route_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent5_ads_truth_route_closeout.md`
12. this starter prompt

## Mission

Synthesize the root Phase 1 closeouts into one route decision:

- blockers closed;
- blockers retained;
- owner questions required;
- CodeCaptain review required or not;
- next safest Phase 2 copied-temp proof route;
- no fake success declarations.

## Boundary

Read-only synthesis only. Do not edit repo state unless the Main Orchestrator later sends a separate approved prompt.

## Required Output

Write the assigned closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- root-agent gate matrix;
- blocker delta from `CURRENT_BLOCKER_BOARD.tsv`;
- exact Phase 2 recommendation;
- exact owner request queue;
- exact CodeCaptain request queue.
