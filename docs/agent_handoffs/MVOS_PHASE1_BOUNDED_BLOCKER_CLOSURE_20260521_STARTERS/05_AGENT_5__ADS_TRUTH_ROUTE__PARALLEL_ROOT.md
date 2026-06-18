# Agent 5 - Ads Truth And STOREB Stopped-Campaign Route

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent5_ads_truth_route_closeout.md`

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

- `B001a_child_source_ads`
- `B002a_c3_ads_source_truth`
- STOREB stopped-campaign context from `2026-05-20 09:46:41`

Keep positive retained spend nonzero. Do not treat missing ads as zero.

## Boundary

Read-only and copied-temp only.

Allowed:

- inspect local Autonomous_business evidence;
- inspect `~/Docs/Web_automation` read-only for local ads/source context if needed;
- create copied DBs/evidence only under `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent5_evidence/`;
- run ads source/sidecar/policy validators against copied DBs only.

Forbidden:

- ad-platform writes;
- ad spend, bid, budget, campaign, or account changes;
- Web_automation writes;
- production DB writes;
- workbook/scheduler/source-pointer/external writes;
- owner publication;
- implementation edits or `.claude/*` edits.

## Required Output

Write the assigned closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact STOREB manual-stop evidence found or missing;
- exact local ads source packets used;
- whether ads source freshness and policy gates can pass in copied-temp;
- explicit confirmation missing ads spend was not zeroed;
- exact retained blocker if not green.

Use `GREEN` only if copied-temp ads source and policy gates pass with accepted evidence. Use `YELLOW` for stale/missing evidence or retained positive-spend blockers. Use `RED` for protected-surface drift or authority conflict.
