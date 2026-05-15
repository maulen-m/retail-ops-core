# Agent 4 - PO, Inbound, And Supplier Route Refresh Analyst

Mode: read-only analyst.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-refresh-owner-review-wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-refresh-owner-review-wave/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_3_c3_po_inbound_supplier_routes_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_8_c3_daily_runner_owner_brief_closeout.md`
8. This assigned starter prompt.

## Mission

Find the safest, most efficient way to refresh PO/inbound/supplier route truth:

- stale inbound workbook source;
- stale E-commerce PO artifact source;
- stale Sourcing-Research supplier route source;
- `PO_INBOUND_REFERENCE_NOT_LINE_GRAIN`;
- `PO_INBOUND_DOUBLE_COUNT`;
- PO-4.0 line-grain/total mismatch blockers;
- LINE31 PO1A source-state separation from old ARC shortage dispute.

## Allowed Work

You may read AB repo files, DB tables through read-only SQLite, the inbound workbook, E-commerce source files, and Sourcing-Research source summaries.

You must not modify workbooks, external repos, supplier communications, DB rows, payment evidence, or source evidence folders.

Do not copy private cargo/payment receiver details into broad output. Use source paths and route IDs.

## Required Analysis

Determine:

- whether the inbound workbook can be considered current or must remain stale;
- exact workbook sheets/columns and scripts needed for a safe refresh;
- whether PO-4.0 blockers are source data blockers or projection/DB blockers;
- how to fix PO inbound line-grain and double-count problems without rewriting source truth;
- how to represent LINE31 PO1A current paid/prep route separately from old ARC shortage dispute;
- exact Agent 6 command sequence and validators;
- any owner action required to confirm arrival, handoff, cargo payment, or employee receipt.

## Required Output

Write a concise, source-backed closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files/workbook sheets/scripts/tables inspected;
- exact recommended Agent 6 command sequence;
- source freshness classification;
- validation gates;
- blockers;
- `OWNER_ATTENTION_REQUIRED` only if human owner action is truly required, with exact paths and plain-English steps.

Do not read sibling agent reports before writing your own first-pass findings.

ASSIGNED CLOSEOUT: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_4_po_inbound_refresh_closeout.md`
