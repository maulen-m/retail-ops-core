# Agent 4 Starter - Split-Repo Review Packet

You are Agent 4. Do not start until Agents 1, 2, and 3 have completed closeouts.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-28_acmewear_parent_child_rush31_strategy_ingest/PLAN.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/ACMEWEAR_PARENT_CHILD_RUSH31_STRATEGY_DRYRUN_20260528_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
7. `~/Docs/Autonomous_business/docs/agent_handoffs/ACMEWEAR_PARENT_CHILD_RUSH31_STRATEGY_DRYRUN_20260528_STARTERS/04_AGENT_4__SPLIT_REPO_REVIEW_PACKET__AFTER_1_2_3.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent1_ab_strategy_ingest_preflight_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent2_web_automation_dryrun_route_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent3_owner_gate_approval_phrases_closeout.md`

## Scope

Write only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent4_split_repo_review_packet/`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun/agent4_split_repo_review_packet_closeout.md`

Do not edit repo files, production DB, workbooks, config, source pointers, schedulers, Web_automation, Kaspi/API/WebUI/Meta/CRM, external systems, supplier messages, stock, price, bid, budget, cash, or PO surfaces.

## Task

Synthesize Agents 1-3 into one operator-ready packet.

Required decisions:

- Is the strategy packet ready for a Web_automation dry-run execution request?
- Which exact approvals are needed next?
- Which actions remain owner-only?
- Which questions require CodeCaptain review before live apply?
- Which current facts must be refreshed because the expert answer was based on a 2026-05-27 pack and a 2026-05-28 operating window?

## Required Outputs

Inside your evidence folder:

- `FINAL_SPLIT_REPO_REVIEW_PACKET.md`
- `NEXT_OWNER_APPROVAL_PHRASES.md`
- `WEB_AUTOMATION_DRYRUN_REQUEST.md`
- `AUTONOMOUS_BUSINESS_PREFLIGHT_REQUEST.md`
- `CODECAPTAIN_PACKET_REQUEST_IF_NEEDED.md`
- `COMMANDS_RUN.tsv`

The closeout must include a standalone line:

`Gate: <GREEN/YELLOW/RED>`

Use `GREEN` only if the next owner prompt can be safely copy-pasted and all live writes remain blocked. Use `YELLOW` if a current-source refresh or owner clarification is needed first. Use `RED` for boundary violations or unsafe execution wording.
