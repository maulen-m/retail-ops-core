# Agent 1 - Physical Stock And PO/Stock Blocker Route

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent1_physical_stock_po_route_closeout.md`

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

Close or precisely route the physical-stock blockers:

- `B001f_child_source_stock`
- `B002d_c3_stock_source_truth`
- `B003_physical_stock_snapshot_stale`
- stock-related parts of `B008_po_money_gate` and `B009_high_stock_retained_exceptions`

## Boundary

Read-only and copied-temp only.

Allowed:

- inspect local repo evidence and current docs;
- inspect local imports/evidence if relevant;
- create copied DBs and evidence only under `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent1_evidence/`;
- run read-only/copied-temp validators.

Forbidden:

- production DB writes;
- workbook writes;
- scheduler/LaunchAgent/cron changes;
- source-pointer writes;
- WebUI/API/Kaspi/external writes;
- cash, PO, stock, price, ads, or owner-publication action;
- repo implementation edits or `.claude/*` edits.

## Required Output

Write the assigned closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact evidence paths read;
- exact commands run;
- whether a fresh physical stock source exists locally;
- whether offer availability was kept separate from physical stock;
- exact remaining owner request if fresh physical stock is missing;
- exact validator/gate that would close the blocker.

Use `GREEN` only if the stock/PO blocker is actually cleared for copied-temp proof with valid physical-stock authority. Use `YELLOW` if the correct next step is owner/source input. Use `RED` if protected surfaces drift or authority conflicts.
