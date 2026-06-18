# Agent 1 Starter - AB Strategy Ingest And Business Preflight

You are Agent 1. Your lane is read-only/evidence-only with respect to production state.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-28_acmewear_parent_child_rush31_strategy_ingest/PLAN.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/ACMEWEAR_PARENT_CHILD_RUSH31_STRATEGY_DRYRUN_20260528_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
7. `~/Docs/Autonomous_business/docs/agent_handoffs/ACMEWEAR_PARENT_CHILD_RUSH31_STRATEGY_DRYRUN_20260528_STARTERS/01_AGENT_1__AB_STRATEGY_INGEST_PREFLIGHT__PARALLEL_ROOT.md`

## Source Inputs

Read these source files:

1. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/00_MAX20_MANIFEST.md`
2. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/01_MAIN_ORACLE_CONTEXT_AND_REQUEST.md`
3. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/11_SOURCE_FILE_MANIFEST.json`
4. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/Answer/Answer_part_1/28.05.2026_15_24_15.md`
5. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/Answer/part_2/Strategy_expert_28.05.2026_18_25_06.md`

## Scope

Write only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent1_ab_strategy_ingest_preflight_evidence/`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent1_ab_strategy_ingest_preflight_closeout.md`

Do not edit repo files, production DB, workbooks, config, source pointers, schedulers, Web_automation, Kaspi/API/WebUI/Meta/CRM, external systems, supplier messages, stock, price, bid, budget, cash, or PO surfaces.

## Task

Create the Autonomous_business review-only ingest packet for the two strategy answers.

Required checks:

- Verify the four source hashes from the canonical plan.
- Extract and normalize the strategy conclusions into an AB-owned decision matrix.
- Compare the strategy against available AB local evidence paths for:
  - latest cash snapshot and SHR payable;
  - V3 all-products inventory capital workbook/summary;
  - Line61 owner stock guardrails;
  - LINE51 4XL out-of-stock conflict;
  - LINE31 PO1B and 7-day timing evidence state.
- Keep ACTUAL, OWNER_REPORTED, MODELLED, WORKING_ESTIMATE, and UNVERIFIED separate.

## Required Outputs

Inside your evidence folder:

- `SOURCE_HASH_CHECK.tsv`
- `AB_STRATEGY_DECISION_MATRIX.tsv`
- `BUSINESS_PREFLIGHT_GAP_TABLE.tsv`
- `OWNER_ONLY_ACTIONS.md`
- `COMMANDS_RUN.tsv`

The closeout must include a standalone line:

`Gate: <GREEN/YELLOW/RED>`

Use `GREEN` only if source hashes match and the business preflight cleanly identifies the next read-only route. Use `YELLOW` if current cash/stock/PO/live-state evidence is incomplete or stale. Use `RED` for boundary violation or unsafe live-action recommendation.
