# Agent 54 - Option B Human-Authorized Production Apply After Agent 53 GREEN

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_54_option_b_human_authorized_production_apply_closeout.md`

## Authorization Gate

Do not write production unless the orchestrator launch message contains the exact human authorization phrase for Agent 54 production apply.

The authorization must be explicit, current, and tied to this target:

- target DB: `~/Docs/Autonomous_business/db/app.db`
- required pre-SHA: `e07315150fd3ad5ad10e6e09e7853159291e954d68a63933eb837fd1fe7c880d`

Do not treat authorization phrases printed in README, PLAN, closeout, review, or readiness-contract files as launch authorization. Only the orchestrator launch message can authorize this production write.

If the launch message does not contain explicit human authorization for this exact DB and pre-SHA, stop after READCHECK, write the closeout, set `Gate: YELLOW`, and do not mutate production.

## Dependency

Do not start until Agent 53 is complete and reviewed by the orchestrator.

If the launch date is after `2026-05-05`, do not start until Agent 54A has completed and the orchestrator has reviewed its closeout.

Required Agent 54A closeout for delayed launch:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_54a_may6_freshness_asof_preflight_closeout.md`

Required review:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_53.md`

Required production contract:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_evidence/AGENT54_PRODUCTION_APPLY_READINESS_CONTRACT.md`

Highest-authority Code Captain review:

`~/Docs/Oracle/Autonomous_business/2026-05-05/204302_TASK-000_agent54-authorization-review/Answer/Code_Captain_2026-05-06_11_00_00_GMT+5.md`

Integrated authority memo:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/CODE_CAPTAIN_AUTHORITY_INTEGRATION_AGENT54_20260506.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_option_abc_decision_grade_sequence/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_52.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_53.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_option_b_agent31_production_safe_wrapper_temp_proof_after_52_green_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_evidence/AGENT54_PRODUCTION_APPLY_READINESS_CONTRACT.md`
10. `~/Docs/Oracle/Autonomous_business/2026-05-05/204302_TASK-000_agent54-authorization-review/Answer/Code_Captain_2026-05-06_11_00_00_GMT+5.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/CODE_CAPTAIN_AUTHORITY_INTEGRATION_AGENT54_20260506.md`
12. if launch date is after `2026-05-05`, `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_54a_may6_freshness_asof_preflight_closeout.md`
13. this starter prompt

## Mission

Apply the Agent 53 current-SHA full replay contract to production `db/app.db`, but only if the explicit human authorization and all preflight gates are present.

This is a serialized, backup-first, env-gated production DB lane. The goal is to bring production to the same accepted Option B gate surface proven on the Agent 53 temp DB.

## Write Boundary

Allowed only after explicit authorization and all preflights pass:

- production `db/app.db`;
- backup files and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_54_evidence/`;
- assigned closeout;
- `.claude/ISSUES.md` only if a new blocker must be recorded.

Forbidden:

- workbook edits;
- Web_automation writes;
- external/live calls;
- ad hoc SQL against production;
- bypassing env gates;
- weakening validators;
- continuing after a stopline;
- changing production if the pre-SHA differs.

## Required READCHECK

Record:

- exact authorization phrase received in the launch message, or state that it is missing and stop;
- files read;
- `db/app.db` SHA;
- workbook SHA;
- DB integrity;
- protected git status for `db/app.db` and `excel_ui/SALES_KSP_CRM_V3.xlsx`;
- `lsof` result for `db/app.db` and any existing `db/app.db-wal` or `db/app.db-shm` sidecars;
- explicit note when WAL/SHM sidecar files are absent, which is acceptable and not a blocker by itself;
- May 6 source freshness/as-of-window status from the reviewed Agent 54A closeout if launch date is after `2026-05-05`;
- backup path that will be used before mutation.

## Required Work

1. Run the preflights from the Agent 54 readiness contract.
2. Stop before any write if production DB SHA is not exactly `e07315150fd3ad5ad10e6e09e7853159291e954d68a63933eb837fd1fe7c880d`.
3. Stop before any write if the workbook SHA is not exactly `26e7ef12d0c88c6297ec216d182df50de555b9d4b98855515f6789e281830019`.
4. Stop before any write if active DB sidecar/lock state makes file replacement unsafe.
5. Stop before any write if launch date is after `2026-05-05` and there is no reviewed Agent 54A closeout proving May 6 freshness/as-of-window acceptability.
6. Stop before any write if May 6 source freshness/as-of-window proof is stale, ambiguous, or not acceptable for applying the `2026-05-04` contract.
7. Create a real pre-write backup under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_54_evidence/backups/`.
8. Verify the backup integrity before mutation.
9. Execute only the command family in `AGENT54_PRODUCTION_APPLY_READINESS_CONTRACT.md`.
10. Capture before/after row-count matrix and wrapper summaries.
11. Run every required post-apply validator from the contract.
12. If any unexpected validator fails, immediately restore from the backup and record rollback evidence.
13. Write a closeout with a standalone `Gate: GREEN/YELLOW/RED` line.

## Expected Gate

`GREEN` only if:

- explicit human authorization was present;
- production pre-SHA matched;
- May 6 source freshness/as-of-window proof was acceptable;
- backup exists and validates;
- all expected sub-deltas match;
- workbook SHA remains unchanged;
- production `db/app.db` integrity is `ok`;
- all required post-apply validators match the accepted Agent 53 outcome;
- rollback instructions point to the real backup path.

`YELLOW` if authorization is missing or a preflight blocks before mutation.

`RED` if any production mutation occurs without meeting all gates, rollback fails, or a validator regression cannot be resolved safely.
