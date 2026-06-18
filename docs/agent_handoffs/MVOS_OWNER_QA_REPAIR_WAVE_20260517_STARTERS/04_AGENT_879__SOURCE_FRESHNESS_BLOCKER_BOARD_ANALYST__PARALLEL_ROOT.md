# Agent879 Starter: Source-Freshness And Retained-Blocker Board Analyst

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent879_source_freshness_blocker_board_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent879_source_freshness_blocker_board_evidence`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_owner_qa_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_owner_qa_repair_wave/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260517.md`
7. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent875_contract_registry_closeout.md`
9. this starter prompt.

## Assignment

Prepare the read-only source-freshness and retained-blocker board inputs that Agent880 will need after the repair lanes close.

You may read repo files, existing validation outputs, Agent868-874 evidence, Agent875 registry artifacts, and local DB copies. You may run read-only validators against production DB or copied DBs only when they do not mutate state. You may write only to your assigned evidence folder and assigned closeout. Do not edit repo files.

Do:

- Build a source-freshness matrix for all active MVOS contracts in the registry.
- Identify the exact validator commands Agent880 should run.
- Identify blockers that must remain visible if proof is YELLOW.
- Separate accepted copied-temp contracts from production-ineligible contracts.
- Record source paths and hashes for any evidence used.

Do not:

- mutate repo files, production DB, workbook, scheduler, source pointers, Web_automation, Kaspi/API/WebUI, ad platforms, cash, PO, stock, price, or external systems;
- call a missing source fresh;
- call a retained-blocker proof GREEN.

Closeout must include:

- standalone `Gate: <GREEN/YELLOW/RED>` line;
- source-freshness matrix;
- retained-blocker board candidate;
- exact Agent880 validator command list;
- blockers/questions remaining.
