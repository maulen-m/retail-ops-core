# Agent 21 - Combined Temp Proof After Agents 18-20

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_21_combined_temp_proof_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_agent14_red_implementation_wave/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_18_derived_table_temp_proof_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_19_c3_policy_exception_temp_proof_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_20_ads_materializer_temp_proof_closeout.md`
9. this starter prompt

## Mission

Run a serialized combined temp proof after the orchestrator has reviewed Agents 18-20.

Do not start unless Agents 18, 19, and 20 have closeouts and the orchestrator has explicitly launched you.

## Write Boundary

Allowed:

- isolated temp DB copies;
- combined evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_21_evidence/`;
- assigned closeout.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- external-system writes;
- ad-platform writes;
- broad code refactors.

## Required Work

1. Read the three upstream closeouts and verify their changed-file claims.
2. Create one clean temp DB copy from production.
3. Replay the derived-table, C3 policy, and ads materializer proof steps in the correct order.
4. Run strict validators against the temp DB where supported.
5. Classify remaining blockers as:
   - safe for production apply lane;
   - needs Web_automation retry;
   - needs owner attention;
   - code/schema blocker.
6. Recommend whether a serialized production apply Agent 22 is safe to launch.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact commands run;
- temp DB path;
- before/after blocker counts;
- whether production apply is safe;
- exact next agent prompt if production apply is safe;
- owner action only if truly required.
