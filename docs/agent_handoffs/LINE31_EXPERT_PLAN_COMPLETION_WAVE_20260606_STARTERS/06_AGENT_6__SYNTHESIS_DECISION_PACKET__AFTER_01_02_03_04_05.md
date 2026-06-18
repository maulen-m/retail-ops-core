# Agent 6 - Synthesis And Decision Packet

Before executing, read:
1. `~/AGENTS.md`
2. `~/Docs/Autonomous_business/AGENTS.md`
3. `~/Docs/Business_3/Facebook_ads/AGENTS.md`
4. `~/Docs/acmewear_web_v2/AGENTS.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-06_line31_expert_plan_completion_wave/PLAN.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_EXPERT_PLAN_COMPLETION_WAVE_20260606_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_expert_plan_completion_wave/agent1_meta_current_state_metrics_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_expert_plan_completion_wave/agent2_line31_order_truth_refresh_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_expert_plan_completion_wave/agent3_stock_cash_po_guard_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_expert_plan_completion_wave/agent4_website_tracking_qa_refresh_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_expert_plan_completion_wave/agent5_meta_api_factory_smoke_closeout.md`
12. This assigned starter prompt.

Workdir:

`~/Docs/Autonomous_business`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_expert_plan_completion_wave/agent6_synthesis_decision_packet_closeout.md`

Assigned evidence root:

`~/Docs/Autonomous_business/exports/validation/line31_expert_plan_completion_20260606/agent6_synthesis_decision_packet`

## Task

Read Agents 1-5 closeouts and create the final decision packet for the orchestrator/human owner.

Synthesize:

- Whether the external expert plan is now complete, partially complete, or blocked.
- Whether the current $55/day budget means the 25k controlled-scale step is already active.
- Whether to hold, reduce, continue, or request a new budget/action approval.
- Whether API factory is GREEN for future campaign creation or still YELLOW.
- Whether website traceability is GREEN, soft-pass YELLOW, or blocked.
- Whether same-day stock/cash/PO guard is GREEN/YELLOW/RED.
- Whether and when to create a separate exploration cell for 6-8 additional videos.
- Exact retained blockers and next actions ranked by urgency.

Produce:

- `line31_expert_plan_completion_decision_packet.md`
- `line31_expert_plan_completion_gate_matrix.csv`
- `line31_next_actions_owner_brief.md`
- optional exact approval phrases, only if a next live action is justified.

## Forbidden

No Meta writes, website deploys, Kaspi/WebUI/API writes, CRM writes, price/stock/cash/PO/supplier actions, DB/workbook writes, scheduler/source-pointer changes, owner publication, internal Kaspi campaign changes, or unrelated external action.

## Gate

`GREEN` if all expert-plan completion gates pass and no retained blocker remains for current controlled scale/API readiness.

`YELLOW` if current controlled scale is usable but one or more retained blockers remain, such as cash freshness, Cloudflare SQL, API factory, or order maturation.

`RED` if evidence shows unsafe spend, broken funnel, dangerous campaign drift, or boundary violation.

## Closeout Requirements

Include `Gate: <GREEN/YELLOW/RED>`, source closeout paths, final gate matrix summary, recommended next owner action, and no-write attestation.
