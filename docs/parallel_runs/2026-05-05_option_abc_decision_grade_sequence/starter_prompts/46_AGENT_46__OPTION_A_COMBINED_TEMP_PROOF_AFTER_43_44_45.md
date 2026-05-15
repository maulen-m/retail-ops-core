# Agent 46 - Option A Combined Temp Proof After 43, 44, 45

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_46_option_a_combined_temp_proof_after_43_44_45_closeout.md`

## Dependency

Do not start until Agents 43, 44, and 45 are complete and reviewed by the orchestrator.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_option_abc_decision_grade_sequence/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/README.md`
6. orchestrator reviews for Agents 43, 44, and 45
7. this starter prompt

## Mission

Combine the Option A root results into one temp proof and determine whether a narrow YELLOW production apply lane is safe to stage.

## Write Boundary

Allowed:

- temp DB and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_46_evidence/`;
- assigned closeout.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- Web_automation writes;
- external/live calls;
- weakening validators.

## Required Work

1. Start from the best reviewed temp DB after Agent 43, or Agent 42 if Agent 43 does not provide a safe DB.
2. Apply only reviewed temp changes from Agents 43, 44, and 45.
3. Rerun:
   - operational stock integration gates;
   - policy gate results;
   - source freshness;
   - order cashflow coverage;
   - cashflow invariants;
   - ads sidecar readiness;
   - ads offer-universe coverage;
   - ads spend reality;
   - DB integrity.
4. Produce a before/after matrix from Agent 42 to Agent 46.
5. State whether Option A is:
   - green enough for a narrow production apply;
   - still yellow but operationally usable with explicit quarantines/banners;
   - red/blocked.

## Expected Gate

`GREEN` only if strict validators pass or all remaining blockers are explicitly non-publication quarantines with validator proof.

`YELLOW` if the system is more operationally useful but still not publication green.

`RED` if combining lanes regresses truth or hides blockers.
