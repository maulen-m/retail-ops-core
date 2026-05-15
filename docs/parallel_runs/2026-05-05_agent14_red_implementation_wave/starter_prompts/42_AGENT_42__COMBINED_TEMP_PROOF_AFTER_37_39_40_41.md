# Agent 42 - Combined Temp Proof After 37, 39, 40, 41

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_42_combined_temp_proof_after_37_39_40_41_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_36.md`
5. closeouts for Agents 37, 39, 40, and 41
6. this starter prompt

## Dependency

Do not start until Agents 37, 39, 40, and 41 are complete and reviewed by the orchestrator.

## Mission

Create the next combined temp proof after the cashflow daily rebuild, Web_automation source packet bridge, STOREB residual classification/recovery, and exception queue classification lanes.

The goal is not to force green. The goal is to produce the most exact residual matrix and determine whether we are ready for a serialized production apply lane.

## Write Boundary

Allowed:

- temp DB and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_42_evidence/`;
- assigned closeout.

Forbidden:

- production DB writes;
- workbook edits;
- Web_automation writes;
- live external calls;
- weakening validators.

## Required Work

1. Start from the best temp DB from Agent 37 or Agent 41, as justified by the reviewed closeouts.
2. Apply only reviewed and accepted temp changes from Agents 37, 39, 40, and 41.
3. Rerun all critical validators:
   - operational stock integration;
   - ads sidecar readiness;
   - ads offer-universe coverage;
   - ads spend reality;
   - source freshness;
   - policy gate results;
   - order cashflow coverage;
   - cashflow invariants;
   - DB integrity.
4. Produce a before/after matrix from Agent 36 to Agent 42.
5. State whether a backup-first production apply lane is now safe, still blocked, or needs human owner decisions.

## Expected Gate

`GREEN` only if all strict validators pass and no production/external write occurred.

`YELLOW` if temp proof improves the system but owner/source residuals remain.

`RED` if combining lanes regresses truth, hides blockers, or creates double counting.
