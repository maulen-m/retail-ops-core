# MVOS 10/10 Contract Execution Plan

Purpose: implement the CodeCaptain-reviewed MVOS 10/10 acceptance contract through scoped read-only, copied-temp, and serialized implementation lanes.

Repo:

`~/Docs/Autonomous_business`

Canonical contract:

`~/Docs/Autonomous_business/docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md`

Orchestrator goal prompt:

`~/Docs/Autonomous_business/docs/contracts/MVOS_10_OUT_OF_10_ORCHESTRATOR_GOAL_PROMPT.md`

Starter folder:

`~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS`

Shared handoff folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution`

As-of window:

`2026-05-18`

## Operating Boundary

Allowed without further approval:

- read-only analysis;
- copied-temp proofs;
- local tests;
- contract docs;
- source-contract registry updates;
- non-production code changes;
- evidence packaging;
- validate-only owner/operator surfaces;
- internal runbooks;
- retained blocker boards.

Not authorized without later exact owner approval and CodeCaptain review:

- production `db/app.db` writes;
- protected workbook writes;
- scheduler, LaunchAgent, plist, cron, or automation-state mutation;
- Web_automation writes;
- browser-login automation;
- external-system writes;
- owner publication/send;
- cash movement;
- supplier payment;
- PO commitment;
- ad spend;
- price changes;
- stock changes.

## Topology

This plan follows `docs/PARALLEL_EXECUTION_PROTOCOL.md`:

- one serialized write-capable execution lane;
- parallel read-only or copied-temp analysts;
- one shared out-of-repo handoff folder;
- no concurrent production DB or protected workbook mutation.

## Sequence

1. Launch Agent 1 first to perform READCHECK, scope declaration, source-contract registry gap map, and write-safety implementation targets.
2. Launch Agents 2-6 in parallel after Agent 1 produces scope and boundary outputs.
3. Launch Agent 7 after Agents 2-6 close out to synthesize owner decision surfaces, full copied-temp proof, and a CodeCaptain-ready production preflight packet if allowed.
4. Stop before production apply, owner phrase request, scheduler mutation, external writes, or owner publication.

## Agent Map

| Starter | Role | Write boundary | Dependency |
| --- | --- | --- | --- |
| `01_AGENT_1__SCOPE_REGISTRY_BOUNDARY__SEQUENTIAL.md` | READCHECK, scope, registry, write safety | Repo docs/code/tests only; no protected production surfaces | None |
| `02_AGENT_2__C3_SOURCE_FRESHNESS__PARALLEL_AFTER_01.md` | C3 source freshness and policy gates | Read-only or copied-temp evidence only | Agent 1 |
| `03_AGENT_3__ORDERS_SALES_LIFECYCLE__PARALLEL_AFTER_01.md` | Orders, sales, lifecycle, COGS | Read-only or copied-temp evidence only | Agent 1 |
| `04_AGENT_4__ADS_TRUTH__PARALLEL_AFTER_01.md` | Ads source truth and spend reality | Read-only or copied-temp evidence only | Agent 1 |
| `05_AGENT_5__CASHFLOW_BANK__PARALLEL_AFTER_01.md` | Cashflow, bank, payment evidence | Read-only or copied-temp evidence only | Agent 1 |
| `06_AGENT_6__PO_STOCK_EXCEPTION__PARALLEL_AFTER_01.md` | PO, stock, inbound, exception queue | Read-only or copied-temp evidence only | Agent 1 |
| `07_AGENT_7__SYNTHESIS_COPY_TEMP_PREFLIGHT__AFTER_02_03_04_05_06.md` | Owner decision surfaces, full copied-temp board, CodeCaptain preflight packet | Serialized repo/evidence writing only; no production apply | Agents 2-6 |

## Required Closeout Standard

Every closeout must include:

- standalone `Gate:` line;
- exact commands run;
- artifacts created;
- protected-surface status;
- copied-temp vs production-truth distinction;
- retained blockers and next smallest safe action.

## Success For This Run

This run is complete when Agent 7 produces one of:

- `COPIED_TEMP_GREEN_PROOF` plus a CodeCaptain-ready production preflight packet; or
- `YELLOW_RETAINED_BLOCKER_BOARD_PROOF` with exact blocker repairs; or
- `RED` with exact stopline cause.
