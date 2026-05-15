# Agent 72 - Production Repair/Apply Contract Draft

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72_production_repair_apply_contract_draft_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72_evidence/`

Primary contract output:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PRODUCTION_REPAIR_APPLY_CONTRACT_DRAFT_AGENT72_20260508.md`

Parallel group:

`agent72_contract_draft`

## Mission

Draft a non-mutating production repair/apply contract from Agent70 and CodeCaptain's Agent70 review. This contract is for review only. It must define exactly how a later, separately authorized DB-only production apply could be done safely.

Do not production-apply. Do not ask the owner for authorization. Do not mutate the live workbook, schedulers, external systems, or `db/app.db`.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_AGENT70_GREEN_TEMP_PROOF_REVIEW_20260508.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-08/161156_TASK-000_codecaptain-agent70-green-temp-proof-review/Answer/Code_Captain_2026-05-08_16_38_00.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT70_ORCHESTRATOR_REVIEW_20260508.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_combined_current_baseline_temp_proof_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/EVIDENCE_MANIFEST.txt`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/VALIDATOR_BEFORE_AFTER.json`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/TABLE_ROWCOUNT_MATRIX.tsv`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/LEAKAGE_MATRIX.tsv`
14. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/REPLAY_STEP_MATRIX.tsv`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72_production_repair_apply_contract_draft_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72_evidence/**`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PRODUCTION_REPAIR_APPLY_CONTRACT_DRAFT_AGENT72_20260508.md`

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate Agent70 evidence.
- Do not mutate scheduler state.
- Do not call live Kaspi/API/bank/Google/Meta/Web_automation/browser/external writes.
- Do not production-apply.
- Do not ask owner for authorization.
- Do not activate Agent64.
- Do not reuse or request the old Agent54 owner phrase.
- Do not treat header-only rows as product truth.
- Do not hide or downgrade the `23` and `252` quarantine warnings.

## Required Work

1. Write READCHECK into the closeout.
2. Verify the required Agent70 evidence files exist.
3. Draft the production repair/apply contract with these sections:
   - scope and non-authorization banner;
   - Agent70 source proof path, final temp DB SHA, integrity, and `2026-05-04` boundary;
   - production write boundary: DB-only `~/Docs/Autonomous_business/db/app.db`;
   - explicit non-write boundaries for workbook, schedulers, external systems, APIs, Kaspi, ads, Google, banks, browser, and Web_automation;
   - expected table deltas from Agent70, including `source_freshness_result +22`, `ads_source_refresh_runs +365`, `ads_campaign_product_daily +1231`, `sales_fact_v2 +1284`, `stock_ledger +957`, `fact_inventory_snapshot_size +363`, `order_status_event +75`, `fact_cashflow_events +66`, `fact_cashflow_daily +19`, `fact_order_entries_kaspi +758`, `fact_order_entry_product_identity_quarantine = 23`, `fact_order_entry_header_only_source_gap_quarantine = 252`, and `view_sales_line_truth +920`;
   - exact ordered command family, dry-run first;
   - env gates and explicit `--apply` flags required for any later write;
   - no ad hoc SQL and no implicit migrations during validation;
   - backup-first requirements, backup SHA, backup integrity, and rollback command;
   - pre-owner-request gates;
   - pre-production-apply gates;
   - post-apply validators;
   - post-apply row-count matrix and leakage matrix;
   - release-anchor requirements;
   - rollback triggers;
   - preserved warning language for `ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED=23` and `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED=252`.
4. Include a "what this contract does not authorize" section.
5. Include a "what Agent73 must package for CodeCaptain" section.
6. Do not create an owner phrase.
7. Do not create production apply commands that are ready to copy-paste without review; mark them as draft contract commands requiring Agent73/CodeCaptain acceptance.

## Gate Semantics

`GREEN`:

- Contract draft exists, is specific enough for CodeCaptain review, and preserves all stoplines.
- No forbidden mutation occurred.

`YELLOW`:

- Contract draft exists but is missing evidence, command specificity, row deltas, or gates.
- No forbidden mutation occurred.

`RED`:

- Contract implies authorization, asks owner, mutates production/workbook/schedulers/external systems, hides warnings, uses old Agent54, activates Agent64, or treats header-only rows as product truth.
