# Agent 902: Orders, Lifecycle, Day-Complete, Status-Ledger, And COGS

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_owner_approved_green_repair/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OWNER_APPROVED_GREEN_REPAIR_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OWNER_APPROVED_GREEN_REPAIR_20260518_STARTERS/02_AGENT_902__ORDERS_LIFECYCLE_COGS__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260518_RETAINED_BLOCKERS.md`
7. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/ORCHESTRATOR_OWNER_APPROVED_REBASELINE_CLOSEOUT.md`

You are not alone in the codebase. Do not revert or overwrite work by other agents.

## Assignment

Run a copied-temp/read-only repair proof for:

- order-entry freshness for `STOREB`, `ACMEWEAR`, `UNIVERSAL`;
- day-complete retained rows;
- scoped status-ledger continuity;
- lifecycle residuals;
- COGS completeness using accepted copied-temp contracts only.

Use these owner decisions without re-asking:

- `11KZ` and `MELVIS` are inactive until future owner activation;
- current scope is `STOREB`, `ACMEWEAR`, `UNIVERSAL`;
- copied-temp parent-unit COGS route may be used only under its registered contract;
- copied-temp proof must not become production truth.

## Boundary

Accepted production boundary:

- DB SHA: `8d45d928888b0a03b42d8a2e73638a5f0ac30caa82b45943623e8df6433196d3`
- Workbook SHA: `0dd9da0233fd30607b6f858db2ea7532bc9ec954021f5e9c195814a41d128313`

If the live protected DB/workbook hashes differ at start, stop `RED`.

## Required Output

Evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_owner_approved_green_repair/agent902_orders_lifecycle_cogs_repair_evidence`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_owner_approved_green_repair/agent902_orders_lifecycle_cogs_repair_closeout.md`

The closeout must include a standalone line:

`Gate: GREEN` or `Gate: YELLOW` or `Gate: RED`

## Rules

- Use a copied DB only.
- Do not mutate production `db/app.db`.
- Do not synthesize WebUI `status_change_at` from API evidence.
- Do not hide quarantine warning classes.
- Do not claim full five-store status-ledger green.
