# Agent 904: PO, Stock Freshness, And Exception Retained Blockers

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_owner_approved_green_repair/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OWNER_APPROVED_GREEN_REPAIR_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OWNER_APPROVED_GREEN_REPAIR_20260518_STARTERS/04_AGENT_904__PO_STOCK_EXCEPTION__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260518_RETAINED_BLOCKERS.md`
7. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/ORCHESTRATOR_OWNER_APPROVED_REBASELINE_CLOSEOUT.md`

You are not alone in the codebase. Do not revert or overwrite work by other agents.

## Assignment

Run a copied-temp/read-only repair proof for:

- PO-4.0 Line61 actual-received shortage fact;
- stock snapshot freshness;
- stock-ledger-to-snapshot proof if available;
- PO money gate blockers;
- exception queue retained blockers.

Use these owner decisions without re-asking:

- PO-4.0 Line61 actual received `92`, ordered/cargo `115`, shortage `23` is real;
- all `9` high-stock exceptions remain visible retained blockers.

## Boundary

Accepted production boundary:

- DB SHA: `8d45d928888b0a03b42d8a2e73638a5f0ac30caa82b45943623e8df6433196d3`
- Workbook SHA: `0dd9da0233fd30607b6f858db2ea7532bc9ec954021f5e9c195814a41d128313`

If the live protected DB/workbook hashes differ at start, stop `RED`.

## Required Output

Evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_owner_approved_green_repair/agent904_po_stock_exception_repair_evidence`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_owner_approved_green_repair/agent904_po_stock_exception_repair_closeout.md`

The closeout must include a standalone line:

`Gate: GREEN` or `Gate: YELLOW` or `Gate: RED`

## Rules

- Use a copied DB only.
- Do not mutate production `db/app.db`.
- Do not mutate workbook or stock.
- Do not commit PO or supplier payment.
- Keep the 9 high-stock exceptions visible unless source/warehouse proof resolves them.
