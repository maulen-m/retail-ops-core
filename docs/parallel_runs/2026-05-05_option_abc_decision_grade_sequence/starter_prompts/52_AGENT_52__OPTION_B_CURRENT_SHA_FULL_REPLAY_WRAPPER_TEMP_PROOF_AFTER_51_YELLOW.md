# Agent 52 - Option B Current-SHA Full Replay Wrapper Temp Proof After Agent 51 YELLOW

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_52_option_b_current_sha_full_replay_wrapper_temp_proof_after_51_yellow_closeout.md`

## Dependency

Do not start until Agent 51 is complete and reviewed by the orchestrator.

Required review:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_51.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_option_abc_decision_grade_sequence/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_50.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_51.md`
8. Agent 50 and Agent 51 closeouts and evidence
9. this starter prompt

## Mission

Prove or reject the full current-production apply contract on a fresh temp copy only.

Agent 51 proved the new quarantine wrapper, but full replay stopped because the current SHA path now requires deleting `23` stock-ledger rows for the owner-approved STOREB product-identity quarantine set. This is plausible and likely correct, but it must be proven end-to-end before any production apply lane.

## Write Boundary

Allowed:

- temp DB and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_52_evidence/`;
- assigned closeout;
- starter/run documentation if needed.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- Web_automation writes;
- external/live calls;
- ad hoc production SQL;
- copying temp tables into production;
- changing code unless a blocker is impossible to prove without a minimal test-first fix;
- weakening validators.

## Required Work

1. READCHECK with exact files read, current protected production SHA, and current production table matrix.
2. Copy current production `db/app.db` to:
   `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_52_evidence/agent52_current_sha_full_replay_temp_20260505.db`
3. Confirm the source copy SHA is:
   `e07315150fd3ad5ad10e6e09e7853159291e954d68a63933eb837fd1fe7c880d`
   If production has drifted again, stop and write the exact new SHA and drift classification.
4. Replay the Agent 50 materialization sequence on the Agent 52 temp DB only, using existing scripts and existing env gates. Reuse Agent 51 commands where useful, but do not copy temp tables.
5. Include the Agent 31 STOREB API order-entry step and prove its exact deltas:
   - safe order rows `253`;
   - candidate entry rows `258`;
   - inserted entry rows expected from the current production copy unless already present.
6. Run the quarantine wrapper after the replay with this revised expected contract:
   - `expected_candidate_rows=23`;
   - `expected_product_cashflow_delete_rows=2`;
   - `expected_stock_ledger_delete_rows=23`;
   - order-level `CASH_IN` must be preserved.
7. After wrapper apply on temp only, prove no product publication leakage for the `23` quarantined orders:
   - `fact_order_entries_kaspi` rows for those order IDs: `0`;
   - `stock_ledger` refs: `0`;
   - product cashflow refs: `0`;
   - published sales truth line rows: `0`;
   - order-level `CASH_IN` rows preserved.
8. Rerun full validators on the final temp DB:
   - DB integrity;
   - operational stock integration gates;
   - policy gate results;
   - source freshness;
   - order cashflow coverage;
   - cashflow invariants;
   - cashflow actual/model separation;
   - ads sidecar readiness;
   - ads offer-universe coverage;
   - ads spend reality.
9. Compare final temp matrix against Agent 50 final temp and explain any row-count differences.
10. If the final temp proof is green, produce an exact Agent 53 production apply contract:
    - exact command sequence;
    - exact env gates;
    - backup directory;
    - expected pre-SHA;
    - expected row deltas;
    - rollback command family;
    - post-apply validators and expected statuses.
11. Do not run Agent 53 and do not mutate production.

## Expected Gate

`GREEN` only if a current-production-derived temp DB reaches decision-grade Option B gate status with only accepted visible limitations, using `expected_stock_ledger_delete_rows=23`, and production remains untouched.

`YELLOW` if the revised contract is plausible but any final validator remains blocked or the current SHA drifts again.

`RED` if temp replay regresses, product leakage remains, `CASH_IN` is not preserved, or production is mutated.
