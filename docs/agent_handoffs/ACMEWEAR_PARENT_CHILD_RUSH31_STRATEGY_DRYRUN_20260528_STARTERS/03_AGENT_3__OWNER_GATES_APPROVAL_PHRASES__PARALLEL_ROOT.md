# Agent 3 Starter - Owner Gates And Approval Phrases

You are Agent 3. Your lane is read-only/evidence-only and focused on owner-control gates.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-28_acmewear_parent_child_rush31_strategy_ingest/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/ACMEWEAR_PARENT_CHILD_RUSH31_STRATEGY_DRYRUN_20260528_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/ACMEWEAR_PARENT_CHILD_RUSH31_STRATEGY_DRYRUN_20260528_STARTERS/03_AGENT_3__OWNER_GATES_APPROVAL_PHRASES__PARALLEL_ROOT.md`

## Source Inputs

Read these source files:

1. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/01_MAIN_ORACLE_CONTEXT_AND_REQUEST.md`
2. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/Answer/Answer_part_1/28.05.2026_15_24_15.md`
3. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/Answer/part_2/Strategy_expert_28.05.2026_18_25_06.md`
4. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/12_SUPPLIER_CASH_PO_DECISION_CONTEXT.md`
5. `~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/15_LINE61_OWNER_APPROVED_STOCK_GUARDRAILS.csv`
6. `~/Docs/Autonomous_business/docs/contracts/CROSS_REPO_BUSINESS_EVENT_BRIDGE_V1.md` if present

## Scope

Write only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent3_owner_gate_approval_phrases_evidence/`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent3_owner_gate_approval_phrases_closeout.md`

Do not edit repo files, production DB, workbooks, config, source pointers, schedulers, Web_automation, Kaspi/API/WebUI/Meta/CRM, external systems, supplier messages, stock, price, bid, budget, cash, or PO surfaces.

## Task

Convert the Strategy Expert answers into exact owner-only gate language.

Separate these categories:

- read-only/source-refresh approvals;
- dry-run approvals that may write local artifacts only;
- Web_automation repo-write approvals;
- live Kaspi/WebUI/API/Repricer/Meta/CRM approval;
- supplier-message approval;
- payment approval;
- PO commitment approval;
- stock/price/bid/budget/campaign approval;
- scheduler approval;
- owner publication approval.

Required attention points:

- SHR/Sahar payment remains owner-only.
- Supplier message remains owner-only unless exact text/channel delegation is approved.
- LINE31 PO1B funding remains blocked unless the 7-day reservation rule is screenshot-backed and owner explicitly prioritizes it.
- LINE51 4XL OOS fix is technical but still requires exact live-write approval before apply.
- A dry-run that writes `runs/` artifacts inside Web_automation still counts as a Web_automation repo write unless the owner authorizes that surface.

## Required Outputs

Inside your evidence folder:

- `OWNER_GATE_MATRIX.tsv`
- `APPROVAL_PHRASES_READY_TO_PASTE.md`
- `ACTIONS_BLOCKED_UNTIL_OWNER_DECISION.md`
- `CODECAPTAIN_REVIEW_QUESTIONS_IF_NEEDED.md`
- `COMMANDS_RUN.tsv`

The closeout must include a standalone line:

`Gate: <GREEN/YELLOW/RED>`

Use `GREEN` only if exact approval phrases are separated cleanly and no phrase accidentally authorizes more than intended. Use `YELLOW` if unresolved ambiguity remains. Use `RED` for unsafe approval wording.
