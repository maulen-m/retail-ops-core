# Agent 12 - Phase 3 Synthesis

Parallel group: `after_8_9_10_11`
Dependencies: Agents 8, 9, 10, and 11 must close out first.
Assigned gate: synthesis only
Closeout path: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase3_retained_blocker_deepening/agent12_phase3_synthesis_closeout.md`
Evidence root: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase3_retained_blocker_deepening/agent12_evidence/`
Repo review draft: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-22_mvos_phase3_retained_blocker_deepening/PHASE3_ORCHESTRATOR_REVIEW_DRAFT.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE3_RETAINED_BLOCKER_DEEPENING_20260522_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE3_RETAINED_BLOCKER_DEEPENING_20260522_STARTERS/12_AGENT_12__PHASE3_SYNTHESIS__AFTER_08_09_10_11.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-21_mvos_phase2_owner_confirmed_blocker_closure/PHASE2_ORCHESTRATOR_REVIEW.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase3_retained_blocker_deepening/agent8_workbook_anchor_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase3_retained_blocker_deepening/agent9_status_day_complete_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase3_retained_blocker_deepening/agent10_ads_retained_spend_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase3_retained_blocker_deepening/agent11_c3_source_freshness_closeout.md`

## Mission

Synthesize the Phase 3 root-agent outputs into a concise next routing decision. Do not hide retained blockers.

## Required Work

1. Read all four dependency closeouts and their key evidence artifacts.
2. Determine the aggregate gate:
   - `GREEN` only if all scoped retained blockers are closed in read-only/copied-temp proof and protected surfaces remained unchanged;
   - otherwise `YELLOW` with exact retained blockers;
   - `RED` for any boundary violation or contradictory evidence.
3. Write a repo review draft at the assigned path with:
   - status label;
   - closed blockers;
   - partially closed blockers;
   - retained blockers;
   - exact next autonomous route;
   - exact human questions if any;
   - whether CodeCaptain packet should be amended.
4. Write your closeout.

## Forbidden

- No production DB writes.
- No workbook writes.
- No source-pointer writes.
- No scheduler/LaunchAgent/cron changes.
- No external writes or fetches.
- No owner publication or production preflight.

## Closeout Requirements

Write the closeout at the assigned path. Include:

- standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- aggregate route decision;
- exact dependency gates;
- exact review draft path;
- whether the current CodeCaptain pack should be amended before sending;
- protected-surface boundary result.
