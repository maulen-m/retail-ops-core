# Agent 4 - Cashflow Freshness Route

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent4_cashflow_freshness_route_closeout.md`

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

Close or precisely route:

- `B001b_child_source_cashflow`
- `B002b_c3_cashflow_source_truth`

Preserve the non-spendable reserve distinction.

## Boundary

Read-only and copied-temp only.

Allowed:

- inspect local cashflow docs, configs, source packets, and prior handoffs;
- create copied DBs/evidence only under `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent4_evidence/`;
- run cashflow and policy/source-freshness validators against copied DBs only.

Forbidden:

- cash/bank movement;
- production DB writes;
- workbook writes;
- scheduler/source-pointer/external writes;
- owner publication;
- implementation edits or `.claude/*` edits.

## Required Output

Write the assigned closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- latest accepted cash/bank source evidence found;
- whether `src_ab_db_cashflow_truth` can be made copied-temp fresh;
- exact copied-temp validator commands/results;
- explicit treatment of the reserve as non-spendable unless owner authority says otherwise;
- exact blocker remaining if not green.

Use `GREEN` only if copied-temp cashflow source freshness and cashflow invariants pass. Use `YELLOW` if source freshness remains stale or owner/source evidence is missing. Use `RED` for protected-surface drift or authority conflict.
