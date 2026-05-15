# Agent 6 - Wiki Context Synthesis And Cross-Repo Memory Routing

Assigned closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_6_c3_wiki_context_synthesis_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/OWNER_QA_C3_SUPPLIER_LINE31_CONTEXT_20260503_210720_ALMT.md`
7. this assigned starter prompt.

## Key Wiki Paths

- `~/Docs/Oracle/knowledge-workspace/wikis/business-wiki`
- `~/Docs/Oracle/knowledge-workspace/wikis/commerce-ops-wiki`
- `~/Docs/Oracle/knowledge-workspace/wikis/finance-exec-wiki`

## Mode

Read-only analyst. Do not edit AB repo files, wiki files, `.claude/*`, DB, env files, or external systems. The only allowed write is your assigned closeout.

## Mission

Create a compact C3 context routing synthesis from the wikis.

Do not copy large wiki content into AB. Identify only:

- which wiki pages or source folders are fundamental for inventory/PO/cashflow/cargo/supplier/ads decisions;
- which wiki owns which type of memory;
- what AB should store as source pointers and what it should not store;
- how Agent 7 should represent wiki-derived facts without turning them into stale rules;
- how route-specific facts, such as ARC LINE31 shortage dispute vs Tracy route, should be preserved.

## Required Closeout Content

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- wiki files/folders read with absolute paths;
- compact routing table by domain;
- recommended source-pointer fields for AB;
- stale/contradictory/missing wiki risks;
- confirmation that no AB repo, wiki, DB, env, external, or Web_automation files were modified.
