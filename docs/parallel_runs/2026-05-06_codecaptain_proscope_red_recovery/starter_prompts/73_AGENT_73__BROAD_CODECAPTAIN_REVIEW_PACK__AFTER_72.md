# Agent 73 - Broad CodeCaptain Review Pack After Agent72

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_73_broad_codecaptain_review_pack_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_73_evidence/`

Parallel group:

`agent73_broad_codecaptain_pack`

Dependency:

Do not run until Agent72 closeout is reviewed and non-RED.

## Mission

Package Agent72's production repair/apply contract for CodeCaptain review with a broad, high-density decision-scope dataset. The goal is to let CodeCaptain evaluate the production contract as part of the full business operating system: stock, orders, sales, ads, cashflow, PO/inbound, daily automation, owner decision gates, release hygiene, and capital protection.

This is a packaging and review-preparation lane only. Do not production-apply. Do not ask the owner for authorization. Do not mutate the live workbook, schedulers, external systems, or `db/app.db`.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_AGENT70_GREEN_TEMP_PROOF_REVIEW_20260508.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PRODUCTION_REPAIR_APPLY_CONTRACT_DRAFT_AGENT72_20260508.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72_production_repair_apply_contract_draft_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_combined_current_baseline_temp_proof_closeout.md`
10. `~/Docs/Oracle/Autonomous_business/2026-05-08/161156_TASK-000_codecaptain-agent70-green-temp-proof-review/Answer/Code_Captain_2026-05-08_16_38_00.md`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_73_broad_codecaptain_review_pack_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_73_evidence/**`
- One flat Oracle/CodeCaptain review pack under `~/Docs/Oracle/Autonomous_business/2026-05-08/` with a timestamped task folder name.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate Agent70 or Agent72 evidence.
- Do not mutate scheduler state.
- Do not call live Kaspi/API/bank/Google/Meta/Web_automation/browser/external writes.
- Do not production-apply.
- Do not ask owner for authorization.
- Do not activate Agent64.
- Do not reuse or request old Agent54.
- Do not hide warning classes or convert header-only rows into product truth.

## Required Work

1. Write READCHECK into the closeout.
2. Verify Agent72 contract exists and is non-RED.
3. Create a flat Oracle review pack under:

   `~/Docs/Oracle/Autonomous_business/2026-05-08/<HHMMSS>_TASK-000_codecaptain-agent72-production-contract-broad-review/`

4. Keep the pack flat. Target at most `16` files. If more context is needed, merge it into the primary request markdown or a single broad context markdown instead of creating subfolders.
5. Include one primary request markdown named clearly, for example:

   `CodeCaptain_Agent72_Production_Contract_Broad_Review_Request_20260508.md`

6. Include Agent72's contract as a separate high-importance file.
7. Include a broad decision-scope context markdown that covers:
   - current authority ladder and stoplines;
   - operational stock truth and stock snapshots;
   - orders, sales, cancellations, returns, and quarantines;
   - ads truth, Kaspi Marketing source coverage, and STOREB/ACMEWEAR scope;
   - cashflow model versus actual cash anchors;
   - PO, inbound, cargo, supplier obligations, and owner reserve;
   - daily automation / Option C validate-only requirements;
   - owner-facing daily decision outputs;
   - release hygiene and rollback;
   - unresolved warnings and non-authorizations.
8. Include the most important Agent70 sidecars or concise copies:
   - Agent70 closeout;
   - `VALIDATOR_BEFORE_AFTER.json`;
   - `TABLE_ROWCOUNT_MATRIX.tsv`;
   - `LEAKAGE_MATRIX.tsv`;
   - `REPLAY_STEP_MATRIX.tsv`;
   - `FINAL_POLICY_SOURCE_FRESHNESS.json`;
   - `FINAL_OPERATIONAL_INTEGRATION_GATE.json`;
   - `ORDER_LEVEL_CASH_PRESERVATION.tsv`.
9. Include CodeCaptain's Agent70 answer or cite it in the primary request if file budget is tight.
10. Include a pack manifest listing every file, source path, and why it is included.
11. The request must ask CodeCaptain to evaluate:
   - whether Agent72's production repair/apply contract is sufficient to open a fresh owner-request preflight lane;
   - whether the broad business context reveals any missing source, gate, rollback, cashflow, PO, ads, or stock dependency;
   - whether the `23` and `252` warning classes remain safe;
   - whether any supplemental proof is required before owner-request preflight;
   - what exact stoplines must carry forward.
12. Open the pack folder in Finder after creation if safe.

## Gate Semantics

`GREEN`:

- Flat broad CodeCaptain pack exists, has at most `16` files, includes Agent72 contract and high-density decision-scope context, and is ready for manual/external review.
- No forbidden mutation occurred.

`YELLOW`:

- Pack exists but needs missing context, evidence, or source availability detail before external review.
- No forbidden mutation occurred.

`RED`:

- Pack implies owner authorization or production apply, hides warning classes, narrows the review too much, fabricates evidence, mutates forbidden surfaces, or exceeds the allowed review boundary.
