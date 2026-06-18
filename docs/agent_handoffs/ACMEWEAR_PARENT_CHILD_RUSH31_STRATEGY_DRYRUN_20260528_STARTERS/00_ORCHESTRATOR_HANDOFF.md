# Orchestrator Handoff - ACMEWEAR Parent/Child/RUSH31 Strategy Dry-Run

Created: 2026-05-28

Gate: ROOT_READY_REVIEW_ONLY

## Objective

Launch a review-only split-repo planning wave for the two Strategy Expert answers from the Web_automation Oracle pack.

The goal is to prepare evidence, preflight, dry-run command plans, and next approval phrases. This handoff does not authorize production applies or live system writes.

## Canonical Plan

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-28_acmewear_parent_child_rush31_strategy_ingest/PLAN.md`

## Starter Folder

`~/Docs/Autonomous_business/docs/agent_handoffs/ACMEWEAR_PARENT_CHILD_RUSH31_STRATEGY_DRYRUN_20260528_STARTERS`

## Shared Handoff Folder

`~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun`

## Source Inputs

- Oracle pack root: `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18`
- Root request: `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/01_MAIN_ORACLE_CONTEXT_AND_REQUEST.md`
- Strategy answer part 1: `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/Answer/Answer_part_1/28.05.2026_15_24_15.md`
- Strategy answer part 2: `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/Answer/part_2/Strategy_expert_28.05.2026_18_25_06.md`
- Pack manifest: `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/00_MAX20_MANIFEST.md`

## Approval Boundary

The current approval allows:

- read-only preflight;
- local evidence generation under the shared handoff folder;
- dry-run command/diff planning;
- review packets;
- strategy ingestion docs in Autonomous_business.

The current approval does not authorize:

- production DB writes;
- workbook writes;
- source-pointer writes;
- scheduler or LaunchAgent changes;
- Web_automation repo writes;
- Kaspi/API/WebUI/Meta/CRM writes;
- external writes or supplier messages;
- payments, PO commitments, stock changes, price changes, ads changes;
- owner publication;
- production preflight or production apply.

## Launch Order

Launch root agents in parallel:

- Agent 1 - Autonomous_business source integrity and business preflight.
- Agent 2 - Web_automation dry-run route plan.
- Agent 3 - owner gate and approval phrase synthesis.

Do not launch Agent 4 until Agents 1-3 have written closeouts.

Launch Agent 4 after root review:

- Agent 4 - final split-repo review packet.

## Assigned Closeouts

- Agent 1: `~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent1_ab_strategy_ingest_preflight_closeout.md`
- Agent 2: `~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent2_web_automation_dryrun_route_closeout.md`
- Agent 3: `~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent3_owner_gate_approval_phrases_closeout.md`
- Agent 4: `~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent4_split_repo_review_packet_closeout.md`

## Anti-Drift Rules

- Do not treat this strategy as live action approval.
- Do not pay SHR/Sahar, send supplier messages, or commit PO.
- Do not change any offer state, price, bid, budget, campaign, Meta adset, CRM state, stock, or scheduler.
- Do not write inside `~/Docs/Web_automation` under this approval.
- Do not write production DB or Excel workbooks.
- Do not treat scheduled direct orders as cash truth.
- Do not treat Kaspi order intake as final sale truth.
- Do not fund LINE31 PO1B based on owner-reported 7-day timing without screenshot-backed evidence and explicit owner override.
- Do not reopen Line61 upper sizes broadly.

## Launch Lines

Root agents:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/ACMEWEAR_PARENT_CHILD_RUSH31_STRATEGY_DRYRUN_20260528_STARTERS/01_AGENT_1__AB_STRATEGY_INGEST_PREFLIGHT__PARALLEL_ROOT.md.
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/ACMEWEAR_PARENT_CHILD_RUSH31_STRATEGY_DRYRUN_20260528_STARTERS/02_AGENT_2__WEB_AUTOMATION_DRYRUN_ROUTE__PARALLEL_ROOT.md.
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/ACMEWEAR_PARENT_CHILD_RUSH31_STRATEGY_DRYRUN_20260528_STARTERS/03_AGENT_3__OWNER_GATES_APPROVAL_PHRASES__PARALLEL_ROOT.md.
```

Final synthesis, locked until root closeouts:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/ACMEWEAR_PARENT_CHILD_RUSH31_STRATEGY_DRYRUN_20260528_STARTERS/04_AGENT_4__SPLIT_REPO_REVIEW_PACKET__AFTER_1_2_3.md.
```
