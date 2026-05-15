# Agent 696 - Header-Only Source-Gap Quarantine Contract

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_696_header_only_source_gap_quarantine_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_696_evidence/`

Parallel group:

`agent696_header_only_contract`

## Mission

Implement and prove, on copied temp DB only, a separate contract for the `252` STOREB header-only source-gap rows identified by Agent69E.

This lane must not pretend header-only sales/CRM fields are real Kaspi item-entry truth. The contract must keep the rows visible as warnings, exclude them from product-level stock/COGS/profit/SKU publication truth, and preserve order-level cash separately.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT69ABC_ORCHESTRATOR_REVIEW_20260508.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT69DE_ORCHESTRATOR_REVIEW_20260508.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69d_order_entry_recovery_asof_contract_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69d_evidence/AGENT70_INPUTS_69D.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69e_order_entry_275_residual_classification_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69e_evidence/AGENT70_INPUTS_69E.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69e_evidence/QUARANTINE_CONTRACT_FIT_REVIEW.md`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69e_evidence/RESIDUAL_275_ROW_CLASSIFICATION.tsv`
14. `~/Docs/Autonomous_business/core/ops/operational_stock_integration_gates.py`
15. `~/Docs/Autonomous_business/scripts/materialize_storeb_product_identity_quarantine.py`
16. `~/Docs/Autonomous_business/tests/test_operational_stock_integration_gates.py`

Primary temp DB input:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69d_evidence/agent69d_order_entry_recovery_working.db`

Expected input SHA256:

`4fbfd9013ae151092a406a0bb4074ba2e2c86f714bdf6a1d6e173740831041eb`

Strict product-identity quarantine candidate file for the 23 API-backed rows:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69e_evidence/OPTIONAL_CANDIDATE_QUARANTINE_ROWS.csv`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_696_header_only_source_gap_quarantine_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_696_evidence/**`

Conditional code write set:

- `~/Docs/Autonomous_business/core/ops/operational_stock_integration_gates.py`
- `~/Docs/Autonomous_business/scripts/materialize_header_only_source_gap_quarantine.py`
- `~/Docs/Autonomous_business/tests/test_operational_stock_integration_gates.py`
- `~/Docs/Autonomous_business/tests/test_header_only_source_gap_quarantine.py`

Only touch additional files if they are strictly required for tests/imports, and list them in the closeout.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate Agent69D or Agent69E source DBs.
- Do not mutate scheduler state.
- Do not call live Kaspi/API/bank/Google/Meta/Web_automation/browser/external writes.
- Do not production-apply or ask owner for authorization.
- Do not insert the `252` header-only rows into `fact_order_entries_kaspi`.
- Do not fabricate API entry IDs, offer codes, product IDs, SKU IDs, or size evidence.

## Required Work

1. Write READCHECK into the closeout.
2. Copy the Agent69D temp DB into the Agent696 evidence folder and verify SHA/integrity.
3. Write failing tests first for the header-only source-gap quarantine contract. At minimum test:
   - header-only quarantined rows emit a visible WARN such as `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED`;
   - they no longer count as unhandled `ORDER_ENTRY_MISSING`;
   - they cannot leak into product stock, product COGS, product profit, or SKU publication truth;
   - no `fact_order_entries_kaspi` rows are inserted for them;
   - missing proof fails closed.
4. Implement the smallest safe materializer/contract:
   - create a separate table, recommended name `fact_order_entry_header_only_source_gap_quarantine`;
   - reason code `HEADER_ONLY_NO_REAL_ITEM_ENTRY_EVIDENCE`;
   - active publication-exclusion flags;
   - source hierarchy proof JSON;
   - header fields stored only as header evidence, not canonical item-entry truth;
   - copied-temp-DB apply only with an env gate;
   - dry-run default.
5. On the copied Agent696 temp DB:
   - apply the existing `23` API-backed strict product-identity quarantine using the existing materializer;
   - apply the new `252` header-only source-gap quarantine using the new materializer;
   - delete/exclude only product-level leakage for quarantined rows;
   - preserve order-level cash-in truth.
6. Run focused tests and capture output.
7. Run validators on the copied Agent696 temp DB:

   ```bash
   python3 scripts/validate_operational_stock_integration_gates.py --db <agent696_temp_db> --as-of 2026-05-04 --json
   python3 scripts/validate_policy_source_freshness.py --db <agent696_temp_db> --as-of 2026-05-04 --strict --json
   ```

8. Produce exact before/after finding counts. Expected target if successful:
   - `ORDER_ENTRY_MISSING` from the 275 residual should be cleared or reduced to zero;
   - `ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED=23` should remain visible;
   - `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED=252` or equivalent visible WARN should appear;
   - ads/cashflow findings may remain for Agent70.
9. Produce Agent70 inputs:
   - exact commands;
   - code files changed;
   - tests run;
   - temp DB SHA;
   - row-count/leakage matrix;
   - whether Agent70 can combine next;
   - CodeCaptain review risks.

## Required Evidence Files

Create/populate:

- `READCHECK.md`
- `COMMANDS_RUN.md`
- `INPUT_SHA_AND_INTEGRITY.txt`
- `TESTS_FIRST_PROOF.md`
- `HEADER_ONLY_QUARANTINE_CANDIDATES.tsv`
- `HEADER_ONLY_QUARANTINE_APPLY_SUMMARY.json`
- `STRICT_23_QUARANTINE_APPLY_SUMMARY.json`
- `VALIDATOR_BEFORE_AFTER.json`
- `LEAKAGE_MATRIX.tsv`
- `ORDER_LEVEL_CASH_PRESERVATION.tsv`
- `AGENT70_INPUTS_696.md`
- `CODECAPTAIN_REVIEW_NOTES.md`
- `EVIDENCE_MANIFEST.txt`

## Gate Semantics

`GREEN`:

- tests-first implementation exists;
- the `252` header-only rows are safely quarantined on copied temp DB only;
- product-level leakage is blocked;
- order-level cash preservation is proven;
- no production/external mutation occurred;
- Agent70 has exact combine instructions.

`YELLOW`:

- contract is designed/proven partially but needs CodeCaptain review or a follow-up implementation lane;
- validator semantics still need a narrow fix;
- no unsafe mutation occurred.

`RED`:

- production/external mutation occurs;
- header-only rows are inserted as real item entries;
- evidence is fabricated;
- validators silently clear the issue without visible warning;
- tests fail without a safe explanation.
