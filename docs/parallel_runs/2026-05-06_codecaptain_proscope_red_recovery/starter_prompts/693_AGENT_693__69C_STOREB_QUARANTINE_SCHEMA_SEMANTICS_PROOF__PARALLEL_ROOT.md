# Agent 69C / Launcher ID 693 - STOREB Quarantine Schema/Semantics Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69c_storeb_quarantine_schema_semantics_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69c_evidence/`

Parallel group:

`agent69abc_root`

## Mission

Prove the correct temp-only schema and semantics for representing the `23` STOREB strict product-identity quarantine residuals so they stay visible but do not leak into product-level stock/COGS/profit publication.

This lane exists because Agent68's current-baseline temp DB is missing `fact_order_entry_product_identity_quarantine`.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT68_ORCHESTRATOR_REVIEW_20260507.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_quiet_window_current_baseline_temp_replay_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_31_storeb_order_entry_negative_ledger_readonly_recovery_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_39_storeb_order_entry_23_residual_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_43_option_a_storeb_23_quarantine_temp_proof_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_51_option_b_production_safe_wrapper_temp_proof_after_50_green_closeout.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_option_b_agent31_production_safe_wrapper_temp_proof_after_52_green_closeout.md`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_39_evidence/storeb_23_strict_quarantine_candidates.csv`
14. `~/Docs/Autonomous_business/tests/test_agent22_stock_ledger_sales_materializer.py`

Primary temp DB input:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_68_evidence/agent68_current_baseline_temp_replay.db`

Expected input SHA256:

`799b1c53a209f13e9bef155b929761be8c65125edc06b1c54e6062a048374954`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69c_storeb_quarantine_schema_semantics_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69c_evidence/**`

Allowed DB writes:

- One copied working temp DB under Agent69C evidence only.
- Any temp-only helper SQL/script under Agent69C evidence only.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate Agent68's input temp DB.
- Do not mutate scheduler state.
- Do not call live Kaspi/API/bank/Google/Meta/Web_automation/browser/external writes.
- Do not invent product identity for the 23 rows.
- Do not turn the 23 quarantine rows into sales/stock/COGS/profit facts.
- Do not production-apply or ask owner for authorization.

## Required Work

1. Write READCHECK into the closeout.
2. Copy the Agent68 temp DB to:

   `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69c_evidence/agent69c_storeb_quarantine_working.db`

3. Verify input SHA and copied DB integrity.
4. Reconstruct the authoritative `23` residual order set from prior evidence. Cross-check Agent31, Agent39, Agent43, Agent51, and Agent53 closeouts/evidence.
5. Inspect current schema expectations for `fact_order_entry_product_identity_quarantine`, including tests/materializers that reference it.
6. On the Agent69C temp DB only, create/prove the minimal quarantine table/schema if absent. This can be done with helper SQL under Agent69C evidence, but must be explicitly labeled temp-proof, not production migration.
7. Insert only the exact 23 strict quarantine candidates into the temp quarantine table, preserving:
   - order identifier;
   - store identity as `STOREB`;
   - reason/classification;
   - source evidence path;
   - no invented SKU/size/product identity.
8. Run focused validations/probes showing:
   - the 23 rows are represented in quarantine;
   - no stock, sales, COGS, or profit rows are created from them;
   - relevant materializers skip quarantined product-identity rows;
   - validators classify them as visible quarantine rather than missing product truth, if current validator support exists.
9. If current validators do not support this representation, produce the exact schema/validator contract needed for Agent70/CodeCaptain.
10. Produce Agent70 inputs:
    - exact SQL/migration contract;
    - exact row set;
    - expected validator semantics;
    - stoplines for production apply.

## Required Evidence Files

Create/populate:

- `READCHECK.md`
- `COMMANDS_RUN.md`
- `STOREB_23_AUTHORITY_MATRIX.tsv`
- `STOREB_23_QUARANTINE_ROWS.csv`
- `QUARANTINE_SCHEMA_PROOF.sql`
- `QUARANTINE_TEMP_APPLY_RESULT.json`
- `NO_LEAKAGE_PROOF.tsv`
- `VALIDATOR_BEFORE_AFTER_MATRIX.tsv`
- `AGENT70_INPUTS_69C.md`
- `EVIDENCE_MANIFEST.txt`

## Gate Semantics

`GREEN`:

- exact 23 row set is source-backed;
- temp quarantine schema/rows are proven;
- no product-level leakage occurs;
- Agent70 has a clear combined-proof contract.

`YELLOW`:

- row set is source-backed but current validators/materializers need code/schema contract work before green;
- no unsafe mutation or invented mapping occurred.

`RED`:

- production/external mutation occurs;
- row set cannot be reconciled;
- product identity is invented or quarantine leaks into stock/profit publication;
- no safe next path exists.
