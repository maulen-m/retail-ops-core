# Agent 2 Starter - Unrelated Failure Triage

You are Agent 2. Your lane is read-only triage for the owner-requested option 2: repair unrelated failures first.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-01_line31_green_except_creative_round3_strict_unrelated_repair/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_ROUND3_STRICT_UNRELATED_20260601_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_ROUND3_STRICT_UNRELATED_20260601_STARTERS/02_AGENT_2__UNRELATED_FAILURE_TRIAGE__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_repair_round2_20260601/agent1_strict_gate_repair/pytest_full_after_repair.stdout`

## Objective

Reproduce, classify, and prioritize the unrelated broad-suite failures so Agent 3 can repair the safe ones before or alongside the strict retained blockers.

## Rules

- Read-only only. Do not modify repo files, DB, workbook, scheduler, source pointers, external systems, prices, stock offers, cash, PO, ads, or website.
- You may run targeted tests and write local evidence plus closeout.
- Do not run live/external write commands.
- Do not run `scripts/run_end_of_day.py --verbose`; it is known not to be passive.

## Required Work

1. Parse the previous broad-suite failure output from:
   `~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_repair_round2_20260601/agent1_strict_gate_repair/pytest_full_after_repair.stdout`
2. Rerun only targeted failing tests or small groups needed to confirm current failures.
3. Classify each failure:
   - safe code/test repair now;
   - stale test expectation;
   - environment/external-state dependent;
   - blocked by current strict-gate retained COGS/on-delivery issue;
   - should not block LINE31 launch-readiness.
4. Produce a prioritized repair queue for Agent 3 with exact files/tests/commands.

## Required Evidence Folder

`~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_round3_strict_unrelated_repair_20260601/agent2_unrelated_failure_triage/`

## Assigned Closeout

`~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_round3_strict_unrelated_repair/agent2_unrelated_failure_triage_closeout.md`

Closeout must include standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

Use `GREEN` if the repair queue is complete and safe for Agent 3. Use `YELLOW` if some failures remain ambiguous or too broad.
