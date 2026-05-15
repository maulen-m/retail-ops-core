# Agent 51 - Option B Production-Safe Wrapper Temp Proof After Agent 50 GREEN

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_51_option_b_production_safe_wrapper_temp_proof_after_50_green_closeout.md`

## Dependency

Do not start until Agent 50 is complete and reviewed by the orchestrator.

Required review:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_50.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_option_abc_decision_grade_sequence/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_46.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_47.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_49.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_50.md`
10. Agent 50 closeout and evidence manifest
11. this starter prompt

## Mission

Create the minimum safe production-apply bridge for Agent 50's accepted temp replay, without mutating production.

Agent 50 proved that a fresh production copy can be brought to the accepted Agent 46 gate surface. The remaining stopline is that `scripts/materialize_storeb_product_identity_quarantine.py` intentionally refuses production `db/app.db` writes. That guard is good. Do not weaken it casually.

Your job is to add or prove a production-safe wrapper/mode that preserves the guardrail but allows a later explicitly authorized, backup-first production apply.

## Write Boundary

Allowed:

- code/tests needed for the wrapper or production-safe mode;
- temp DB and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_51_evidence/`;
- assigned closeout;
- `.claude/ISSUES.md` only if a new blocker must be recorded.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- Web_automation writes;
- external/live calls;
- ad hoc SQL against production;
- copying Agent 46/50 temp tables into production;
- weakening existing validators;
- bypassing script guards by editing environment checks without replacement controls.

## Required Work

1. READCHECK with exact files read and current protected production SHA.
2. Write tests before code changes.
3. Inspect:
   - `scripts/materialize_storeb_product_identity_quarantine.py`
   - `scripts/materialize_storeb_api_order_entries_from_agent31.py`
   - existing tests for both scripts
   - Agent 50 replay commands and expected deltas
4. Add the smallest safe wrapper or explicit production mode for the quarantine step.
   - Prefer a new wrapper script over weakening the temp materializer.
   - If you modify the existing materializer, preserve temp-only default behavior.
5. The production-safe path must require:
   - explicit apply flag;
   - explicit env gate, with a new production-specific gate name;
   - required backup path or backup directory;
   - pre-write SHA check;
   - pre-write `PRAGMA integrity_check`;
   - expected candidate rows `23`;
   - expected product-cashflow delete rows `2` when production pre-SHA is `ca83da76aae57593d89dad72f477f6cacee6d1094995934e5ff6577f43c66557`;
   - expected stock-ledger delete rows `0`;
   - proof that order-level `CASH_IN` rows are preserved;
   - post-write `PRAGMA integrity_check`;
   - structured summary JSON;
   - rollback instructions pointing to the actual backup file.
6. Inspect whether `scripts/materialize_storeb_api_order_entries_from_agent31.py` needs the same wrapper treatment.
   - If it is still needed in production, add the same class of protection or write a concrete blocker.
   - If it becomes no-op after the Agent 50 replay sequence, prove no-op on a fresh production copy and document that proof.
7. Prove everything on a fresh copy of current production only.
   - Suggested temp DB path:
     `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_51_evidence/agent51_prod_wrapper_temp_20260505.db`
8. Rerun focused tests and relevant validators on temp:
   - new wrapper tests;
   - `tests/test_storeb_product_identity_quarantine.py`;
   - `tests/test_materialize_storeb_api_order_entries_from_agent31.py`;
   - operational stock integration gates;
   - policy gate results;
   - source freshness;
   - order cashflow coverage;
   - cashflow invariants;
   - cashflow actual/model separation;
   - ads sidecar readiness;
   - ads offer-universe coverage;
   - ads spend reality;
   - DB integrity.
9. Write the exact later production apply contract but do not execute it:
   - exact command;
   - env gates;
   - backup path pattern;
   - expected pre-SHA and deltas;
   - validators and expected statuses;
   - rollback command family.

## Expected Gate

`GREEN` only if tests are written first, production remains untouched, wrapper/prod-mode proof passes on a fresh production copy, and the later production apply contract is exact enough for a serialized Agent 52 apply lane.

`YELLOW` if the safe design is clear but code/proof is incomplete or the Agent 31 production path needs a separate wrapper lane.

`RED` if production is mutated, tests fail, safety gates are missing, or a wrapper would require weakening the existing fail-closed contract.
