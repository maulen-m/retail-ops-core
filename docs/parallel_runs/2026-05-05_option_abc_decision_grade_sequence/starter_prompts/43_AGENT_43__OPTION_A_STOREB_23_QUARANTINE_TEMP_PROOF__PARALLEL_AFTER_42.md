# Agent 43 - Option A STOREB 23 Product-Identity Quarantine Temp Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_43_option_a_storeb_23_quarantine_temp_proof_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_option_abc_decision_grade_sequence/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_42.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_39_evidence/storeb_23_strict_quarantine_contract_draft.md`
8. this starter prompt

## Mission

Implement and prove a strict STOREB `23` product-identity quarantine on a temp DB only.

The goal is to stop unknown-product STOREB orders from blocking useful operation while ensuring they cannot leak into product-level stock, COGS, product profit, or SKU publication.

## Write Boundary

Allowed:

- tests and code required for the quarantine contract;
- temp DB and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_43_evidence/`;
- assigned closeout.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- Web_automation writes;
- live external calls;
- weakening validators;
- inserting partial `fact_order_entries_kaspi` rows for the STOREB `23`.

## Required Work

1. Tests first for the quarantine contract from Agent 39:
   - unquarantined missing order entry remains blocking;
   - quarantined row without publication-exclusion proof remains blocking;
   - quarantined row with publication-exclusion proof is not counted as unhandled `ORDER_ENTRY_MISSING`;
   - mixed known/unknown order remains quarantined unless every entry has exact product identity;
   - quarantined orders cannot feed product stock, COGS, or product profit publication;
   - header fallback identity cannot satisfy product-level truth.
2. Add the minimal schema/table/loader/validator behavior needed for `fact_order_entry_product_identity_quarantine` or an equivalent explicitly named quarantine surface.
3. Start from Agent 42's combined temp DB:
   `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_42_evidence/agent42_combined_temp_after_37_39_40_41_20260504.db`
4. Temp-apply only the STOREB `23` quarantine rows using Agent 39 evidence.
5. Rerun:
   - operational stock integration gates;
   - policy gate results;
   - source freshness;
   - order cashflow coverage;
   - cashflow invariants;
   - DB integrity;
   - focused tests.
6. State whether `stock_source_truth` can become non-blocking only because the `23` are safely quarantined, not because they were hidden.

## Expected Gate

`GREEN` only if the temp DB proves the quarantine is safe and no product-level leakage is possible.

`YELLOW` if the implementation is partially proven but some publication-exclusion proof remains missing.

`RED` if the change hides `ORDER_ENTRY_MISSING`, weakens validators, or risks double counting.
