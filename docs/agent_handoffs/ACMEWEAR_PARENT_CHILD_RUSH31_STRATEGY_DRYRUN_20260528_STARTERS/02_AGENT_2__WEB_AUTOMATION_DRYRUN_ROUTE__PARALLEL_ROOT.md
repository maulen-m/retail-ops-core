# Agent 2 Starter - Web_automation Dry-Run Route Plan

You are Agent 2. Your lane is read-only/evidence-only. You are preparing the Web_automation dry-run route, not executing live changes.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-28_acmewear_parent_child_rush31_strategy_ingest/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/ACMEWEAR_PARENT_CHILD_RUSH31_STRATEGY_DRYRUN_20260528_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/ACMEWEAR_PARENT_CHILD_RUSH31_STRATEGY_DRYRUN_20260528_STARTERS/02_AGENT_2__WEB_AUTOMATION_DRYRUN_ROUTE__PARALLEL_ROOT.md`
6. `~/Docs/Web_automation/AGENTS.md`
7. `~/Docs/Web_automation/Docs/00_START_HERE.md`

## Source Inputs

Read these source files:

1. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/01_MAIN_ORACLE_CONTEXT_AND_REQUEST.md`
2. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/Answer/Answer_part_1/28.05.2026_15_24_15.md`
3. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/Answer/part_2/Strategy_expert_28.05.2026_18_25_06.md`
4. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/02_CURRENT_CAMPAIGN_STATE.csv`
5. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/07_BID_VIEW_SPEND_RESPONSE_MODEL.csv`
6. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/09_ROUTE_SCHEDULE_AND_FAST_FEEDBACK_PLAN.csv`
7. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/10_CHILD_BUNDLE_AND_RUSH31_CONTEXT.csv`
8. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/17_LOCAL_FUNNEL_CAPACITY_AND_AD_RESTART_NOTES.md`

## Scope

Write only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent2_web_automation_dryrun_route_evidence/`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent2_web_automation_dryrun_route_closeout.md`

Do not edit `~/Docs/Web_automation`. Do not execute commands that create Web_automation `runs/` artifacts under this approval. Do not execute live or dry-run commands against Kaspi/API/WebUI/Meta/CRM unless they are guaranteed no-write and write all output only to the shared handoff folder.

## Task

Prepare the Web_automation dry-run route plan from the strategy answers.

Required route surfaces:

- LINE51 4XL out-of-stock offer-state conflict: dry-run command requirements and expected diff shape.
- LINE51 G1 lower-risk posture: campaign `2380614`, BID `160 -> 120`, cap `15000 -> 10000`, price hold `16990`, dry-run requirements.
- Line61 guard verification: ensure 2XL/3XL remain guarded and 4XL is not exposed; no broad reopening.
- LINE51 G2/G3 micro-test planning: values, caps, stop rules, and prerequisites.
- LINE31/RUSH31 local discovery: no funding commitment; values, budget, stop rules, and evidence prerequisites.
- Monitoring/checkpoint cadence: command plan only; no scheduler mutation.

## Required Outputs

Inside your evidence folder:

- `WEB_AUTOMATION_DRYRUN_COMMAND_PLAN.tsv`
- `EXPECTED_DIFF_SURFACES.tsv`
- `ROUTE_VALUE_AND_STOP_RULE_MATRIX.tsv`
- `WEB_AUTOMATION_WRITE_APPROVALS_NEEDED.md`
- `COMMANDS_RUN.tsv`

The closeout must include a standalone line:

`Gate: <GREEN/YELLOW/RED>`

Use `GREEN` only if a later Web_automation dry-run agent has exact commands, inputs, no-write guarantees, and approval boundaries. Use `YELLOW` if command feasibility depends on live source refresh or a Web_automation write approval. Use `RED` for any accidental Web_automation or live-platform mutation.
