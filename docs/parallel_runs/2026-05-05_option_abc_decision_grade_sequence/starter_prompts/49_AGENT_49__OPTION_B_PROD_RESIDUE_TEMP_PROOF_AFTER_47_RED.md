# Agent 49 - Option B Production Residue Temp Proof After Agent 47 RED

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_49_option_b_prod_residue_temp_proof_after_47_red_closeout.md`

## Dependency

Do not start until Agent 47 is complete and reviewed by the orchestrator.

Required review:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_47.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_option_abc_decision_grade_sequence/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_46.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_47.md`
8. Agent 47 closeout and evidence
9. this starter prompt

## Mission

Prove, on a copied temp DB only, whether the current production residue path is safe:

- STOREB order `896750859` has two product-level `fact_cashflow_events` rows that were absent from the reviewed Agent 46 temp proof.
- The two product-level rows must be removed or neutralized by the reviewed quarantine path.
- The order-level `CASH_IN` rows for the same order must remain.

This is a temp-proof lane only. Do not mutate production.

## Write Boundary

Allowed:

- temp DB and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_49_evidence/`;
- assigned closeout.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- Web_automation writes;
- external/live calls;
- ad hoc production SQL;
- weakening validators.

## Required Work

1. Copy current production `db/app.db` to:
   `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_49_evidence/agent49_prod_residue_temp_20260505.db`
2. Record SHA-256 and integrity for source and temp DB.
3. Capture pre-state for order `896750859`:
   - all `fact_cashflow_events` rows;
   - product-level leakage count;
   - order-level `CASH_IN` count.
4. Apply `scripts/materialize_storeb_product_identity_quarantine.py` to the temp DB only with:
   - candidates: `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_39_evidence/storeb_23_residual_classification.csv`
   - env gate: `ENABLE_STOREB_PRODUCT_IDENTITY_QUARANTINE_TEMP_APPLY=1`
   - `--apply`
5. Prove post-state:
   - `inserted_quarantine_rows=23`;
   - `deleted_product_cashflow_rows=2`;
   - `deleted_stock_ledger_rows=0`;
   - `product_cashflow_reference_count=0`;
   - `fact_order_entries_count=0`;
   - product stock/COGS/profit/sales publication leakage remains zero;
   - order-level `CASH_IN` rows for order `896750859` remain exactly `2`;
   - no production protected surface changed.
6. Materialize source freshness and policy gates on the temp DB only, with backups under Agent 49 evidence.
7. Rerun the Agent 46 validator set on the temp DB:
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
8. Run focused tests if code/test surfaces are touched. If no code is touched, state that and run only the validators.
9. State whether a production apply can be re-authorized, and identify whether the current temp-only script needs a production-safe wrapper or patch before production apply.

## Expected Gate

`GREEN` only if the current production residue path is fully proven on temp DB, all validators pass with only known `exception_queue` limitation, and production is untouched.

`YELLOW` if the temp proof is directionally useful but production apply still needs code/wrapper hardening or human authorization.

`RED` if temp proof regresses validators, deletes cash-in, broadens cleanup beyond the two known rows, or cannot prove production remained untouched.
