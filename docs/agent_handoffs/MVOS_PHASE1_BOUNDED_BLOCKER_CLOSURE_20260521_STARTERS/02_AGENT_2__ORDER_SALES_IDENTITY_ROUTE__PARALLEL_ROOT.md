# Agent 2 - Order-Entry And Sales Identity Route

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent2_order_sales_identity_route_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/current/FINAL_10_OUT_OF_10_EXECUTION_PLAN.md`
4. `~/Docs/Autonomous_business/docs/current/CURRENT_BLOCKER_BOARD.tsv`
5. `~/Docs/Autonomous_business/docs/current/CURRENT_GATE_MATRIX.tsv`
6. `~/Docs/Autonomous_business/docs/current/CURRENT_SOURCE_TRUTH_MAP.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-21_mvos_phase1_clean_then_blocker_closure/CLEAN_FIRST_BOUNDARY.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-21_mvos_phase1_clean_then_blocker_closure/DIRTY_STATE_GROUPS.tsv`
9. this starter prompt

## Mission

Close or precisely route the order-entry and sales identity blockers:

- `B001c_child_source_order_entry`
- `B001e_child_source_sales`
- `B004_universal_storeb_order_entry_identity`
- sales/workbook side of `B005_workbook_content_lag`

Focus especially on Universal offer `132822924_328581041` and STOREB/UNIVERSAL identity coverage.

## Boundary

Read-only and copied-temp only.

Allowed:

- inspect local repo evidence, source contracts, imports, and existing handoffs;
- read `~/Docs/Web_automation` read-only only if needed for local source/offer identity context;
- create copied DBs and evidence only under `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent2_evidence/`;
- run strict rebuild/freshness validators against copied DBs only.

Forbidden:

- production DB writes;
- workbook writes;
- scheduler/source-pointer/external/Web_automation writes;
- Kaspi/API/WebUI mutations;
- owner publication;
- implementation edits or `.claude/*` edits.

## Required Output

Write the assigned closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact identity evidence found or missing;
- exact copied-temp validator commands and results;
- whether Universal offer `132822924_328581041` is resolved, quarantined, or owner-needed;
- exact rows/contracts that remain retained blockers;
- next command that would close the blocker.

Use `GREEN` only if strict copied-temp rebuild/freshness gates pass for the declared scope. Use `YELLOW` for missing/ambiguous source or owner-needed identity. Use `RED` for authority conflict or protected-surface drift.
