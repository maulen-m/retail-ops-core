# Agent 53 - Option B Agent31 Production-Safe Wrapper Temp Proof After Agent 52 GREEN

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_option_b_agent31_production_safe_wrapper_temp_proof_after_52_green_closeout.md`

## Dependency

Do not start until Agent 52 is complete and reviewed by the orchestrator.

Required review:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_52.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_option_abc_decision_grade_sequence/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_51.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_52.md`
8. Agent 51 and Agent 52 closeouts/evidence
9. this starter prompt

## Mission

Close the last mechanical write-safety gap before a later production apply.

Agent 52 proved the full current-SHA temp replay, but its production contract still depends on `scripts/materialize_storeb_api_order_entries_from_agent31.py`, which intentionally refuses direct production `db/app.db` writes. Build the same class of production-safe wrapper used for STOREB product-identity quarantine, but for Agent 31 STOREB API order-entry materialization.

This lane must not mutate production.

## Write Boundary

Allowed:

- code/tests for the Agent 31 production-safe wrapper;
- temp DB and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_evidence/`;
- assigned closeout;
- `.claude/ISSUES.md` only if a new blocker must be recorded.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- Web_automation writes;
- external/live calls;
- ad hoc SQL against production;
- copying temp tables into production;
- weakening existing temp-only guards or validators.

## Required Work

1. READCHECK with exact files read, current protected production SHA, and current production table matrix.
2. Write tests before code changes.
3. Inspect:
   - `scripts/materialize_storeb_api_order_entries_from_agent31.py`;
   - `scripts/apply_storeb_product_identity_quarantine_production_safe.py`;
   - `tests/test_materialize_storeb_api_order_entries_from_agent31.py`;
   - `tests/test_storeb_product_identity_quarantine_prod_wrapper.py`;
   - Agent 52 replay commands and Agent 53 production apply contract.
4. Add the smallest safe wrapper for Agent 31 STOREB API order entries.
   - Prefer a new script, for example `scripts/apply_storeb_api_order_entries_from_agent31_production_safe.py`.
   - Preserve the existing temp-only default and guard in `scripts/materialize_storeb_api_order_entries_from_agent31.py`.
5. The wrapper must require:
   - explicit `--apply`;
   - new env gate `ENABLE_STOREB_API_ORDER_ENTRY_PRODUCTION_APPLY=1`;
   - required backup directory;
   - pre-write SHA check;
   - pre-write `PRAGMA integrity_check`;
   - expected safe order rows `253`;
   - expected candidate entry rows `258`;
   - expected inserted entry rows `258` unless a reviewed drift proof shows rows already exist;
   - expected quarantine rows `23`;
   - proof that no quarantine rows are inserted as product truth;
   - post-write `PRAGMA integrity_check`;
   - structured `summary.json`;
   - rollback command pointing to the actual backup file.
6. Prove wrapper mechanics on small unit-test DB fixtures.
7. Prove wrapper behavior on a fresh copy of current production only:
   `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_evidence/agent53_agent31_wrapper_temp_20260505.db`
8. Rerun focused tests:
   - new wrapper tests;
   - `tests/test_materialize_storeb_api_order_entries_from_agent31.py`;
   - `tests/test_storeb_product_identity_quarantine_prod_wrapper.py`;
   - py_compile for relevant scripts.
9. Rerun the Agent 52 full temp replay on a fresh current-production copy using both wrappers if feasible.
   - If that is too expensive, run a narrow proof and explicitly state what Agent 54 must re-prove before production apply.
10. Write an exact Agent 54 production apply readiness contract but do not execute it.

## Expected Gate

`GREEN` only if the Agent 31 wrapper is tests-first, production remains untouched, wrapper proof passes on a fresh production copy, and the next production apply contract is exact enough for a serialized Agent 54 apply lane.

`YELLOW` if the wrapper is safe but full Agent 52 replay needs one more temp proof before production.

`RED` if production is mutated, wrapper gates are incomplete, expected deltas cannot be proven, or tests fail.
