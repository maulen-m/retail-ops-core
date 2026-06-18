# Agent917 MVOS Yellow-To-Green Non-Production Repair Wave Plan

Created: 2026-05-19 17:03 +05

Gate: OWNER_ENVELOPE_APPROVED_ROOT_READY

## Source Decision

This plan integrates CodeCaptain's review:

`~/Docs/Oracle/Autonomous_business/2026-05-19/134551_TASK-000_mvos-agent9167-yellow-copied-temp-rerun-codecaptain/Answer/Code Captain_19.05.2026_16_48_33.md`

CodeCaptain confirmed Agent9167 is correctly:

`YELLOW_RETAINED_BLOCKER_BOARD_PROOF`

Agent9167 is useful copied-temp progress, not copied-temp green proof, not production readiness, and not production preflight/apply approval.

## Owner Envelope

The owner approved the Agent917 non-production envelope on 2026-05-19:

```text
I approve Agent917 MVOS yellow-to-green non-production repair wave in Autonomous_business. Agents may run read-only
  analysis, copied-temp-only materialization/proofs, local evidence generation, source contract docs, focused tests,
  closeouts, and one serialized repo code/test integration lane. No production DB writes, workbook writes, source-pointer
  writes, scheduler/LaunchAgent/cron changes, Web_automation writes, Kaspi/API/WebUI writes, external writes, ad-platform
  writes, ad spend, stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, or
  production apply are authorized.
```

## Objective

Move from Agent9167's broad yellow proof to the smallest safe copied-temp green candidate by repairing exact non-production blockers first, then running one fresh copied-temp proof rerun.

## Non-Authorization

This plan does not authorize:

- production DB writes;
- workbook writes;
- source-pointer writes;
- scheduler/LaunchAgent/cron changes;
- Web_automation writes;
- Kaspi/API/WebUI writes or mutations;
- external writes;
- ad-platform writes;
- ad spend;
- stock changes;
- price changes;
- cash movement;
- PO commitment;
- owner publication;
- production preflight;
- production apply.

## Sequence

Phase 1 runs seven independent root lanes in parallel. These agents are read-only with respect to repo state and write only to the out-of-repo handoff folder.

- Agent9171: stock offer-availability source contract and test route.
- Agent9172: sales identity repair matrix and quarantine closure route.
- Agent9173: Agent9143 ads packet v1 adapter and retained-spend route.
- Agent9174: COGS single-row copied-temp evidence route for integrity.
- Agent9175: day-complete current-result cleanup and stale-file decision.
- Agent9176: PO/single-truth canonical reconciliation route.
- Agent9177: proof-board, C3 source-freshness bridge, and registry integration route.

Phase 2 is one serialized writer/proof integrator after the orchestrator reviews all seven Phase 1 closeouts.

- Agent9178: only write-capable lane; may patch source contracts, code, and focused tests, create a fresh copied DB, run copied-temp materializers/validators, and prepare the next CodeCaptain packet.

## Required Upstream Inputs

- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent916_nonproduction_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT9167.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_copied_temp_rerun_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/AGENT9167_VALIDATOR_MATRIX.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/AGENT9167_RETAINED_BLOCKER_COUNTS.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/AGENT9167_IMPLEMENTATION_MATRIX.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/COPIED_DB_MANIFEST.json`

## Lane Details

### Agent9171 - Stock Offer Availability Contract

Purpose:

- convert CodeCaptain's stock guidance into an implementable copied-temp offer-availability contract;
- prove what Merchant Cabinet/pricelist packets may and may not claim.

Required preservation:

- Merchant Cabinet/pricelist may prove `offer_availability_snapshot` only;
- it must not prove canonical physical warehouse stock;
- it must not update `stock_ledger` or `fact_inventory_snapshot_size.current_stock`;
- the `9` `STOCK/HIGH/OPEN` exceptions remain visible unless an independent physical stock source closes them.

Outputs:

- `MERCHANT_CABINET_PRICELIST_OFFER_AVAILABILITY_COPIED_TEMP_V1.md`
- `STOCK_PHYSICAL_TRUTH_SEPARATION_MATRIX.tsv`
- `OFFER_AVAILABILITY_MATERIALIZER_TEST_PLAN.tsv`
- `agent9171_stock_offer_availability_contract_closeout.md`

### Agent9172 - Sales Identity Repair Matrix

Purpose:

- resolve or explicitly retain every sales identity blocker without guessing.

Targets:

- Universal offer `132822924_328581041` for orders `913421682` and `921067176`;
- five STOREB `sku_identity` gaps previously addressed by Agent9162;
- four remaining order-entry recovery quarantine rows.

Outputs:

- `SALES_IDENTITY_REPAIR_MATRIX.tsv`
- `UNIVERSAL_132822924_328581041_DECISION.md`
- `ORDER_ENTRY_RETAINED_QUARANTINE_MATRIX.tsv`
- `agent9172_sales_identity_matrix_closeout.md`

### Agent9173 - Ads Packet V1 Adapter

Purpose:

- keep the strict `ads_web_source_packet.v1` contract and adapt packet shape instead of weakening validators;
- preserve STOREB business-store identity separately from Universal access identity;
- keep positive retained spend visible, not zeroed.

Targets:

- Agent9143/Agent9167 STOREB and ACMEWEAR packet manifests;
- STOREB retained unmapped product-code spend, currently `3837.32 KZT` in Agent9167 evidence.

Outputs:

- `AGENT9143_TO_ADS_WEB_SOURCE_PACKET_V1_ADAPTER_PLAN.md`
- `ADS_WEB_SOURCE_PACKET_V1_REQUIRED_FIELDS.tsv`
- `STOREB_RETAINED_ADS_SPEND_DECISION_MATRIX.tsv`
- `agent9173_ads_packet_v1_adapter_closeout.md`

### Agent9174 - COGS Single-Row Integrity Route

Purpose:

- decide and design the smallest copied-temp route that lets strict COGS integrity consume accepted unit evidence without turning it into production economics truth.

Target:

- `909054064 / ACMEWEAR / SUIT-31-TS_3XL`

Outputs:

- `COGS_UNIT_EVIDENCE_COPIED_TEMP_V1.md`
- `COGS_INTEGRITY_PATCH_PLAN.tsv`
- `COGS_PRODUCTION_STRICTNESS_GUARD.md`
- `agent9174_cogs_single_row_integrity_closeout.md`

### Agent9175 - Day-Complete Current Result Cleanup

Purpose:

- resolve the stale standalone day-complete file versus current Agent9167 matrix mismatch.

Rule:

- include one current day-complete result in the next packet;
- if the two rows reappear, rerun the copied-temp two-row repair;
- do not infer size/status truth without source-backed evidence.

Outputs:

- `DAY_COMPLETE_CURRENT_RESULT_DECISION.md`
- `DAY_COMPLETE_STALE_FILE_CLASSIFICATION.tsv`
- `DAY_COMPLETE_PACKET_INCLUSION_RULE.md`
- `agent9175_day_complete_current_result_closeout.md`

### Agent9176 - PO/Single-Truth Canonical Reconciliation

Purpose:

- identify the exact non-production route to close or preserve PO money and single-truth failures without hiding Line61 accepted shortage.

Required preservation:

- Line61 ordered/cargo `115`;
- actual received `92`;
- shortage `23`;
- size shortage XL `7`, 2XL `5`, 3XL `6`, 4XL `5`;
- this accepted shortage does not green unrelated PO money or alignment failures.

Targets:

- `17` historical DB-only part IDs;
- PO-4 total/weight mismatch;
- PO-5.2/PO-6 base-payment mismatches;
- inventory cost drift and single-truth alignment failures;
- PO money gate retained failures.

Outputs:

- `PO_SINGLE_TRUTH_CANONICAL_RECONCILIATION_PLAN.md`
- `PO_PART_HISTORY_MISMATCH_MATRIX.tsv`
- `PO_BASE_PAYMENT_MISMATCH_MATRIX.tsv`
- `PO_MONEY_GATE_CLOSURE_CONDITIONS.tsv`
- `agent9176_po_single_truth_reconciliation_closeout.md`

### Agent9177 - Proof Board, C3 Bridge, And Registry Integration

Purpose:

- design the proof-board and source-contract registry update that lets accepted Agent914/916/917 packets contribute to copied-temp C3 source freshness without claiming physical stock freshness.

Targets:

- `validate_policy_source_freshness.py` missing rows;
- `validate_policy_gate_results.py` blocked C3 gates;
- `docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`;
- `scripts/materialize_copied_temp_source_freshness_bridge.py`;
- proof-board output for next CodeCaptain pack.

Outputs:

- `C3_SOURCE_FRESHNESS_BRIDGE_ACCEPTANCE_MATRIX.tsv`
- `MVOS_SOURCE_CONTRACT_REGISTRY_PATCH_PLAN.md`
- `NEXT_COPIED_TEMP_PROOF_BOARD_SPEC.md`
- `STOPLINE_MATRIX.tsv`
- `agent9177_proof_board_c3_integration_closeout.md`

### Agent9178 - Serialized Integrator And Copied-Temp Rerun

Purpose:

- after all Phase 1 closeouts are reviewed, implement the smallest safe code/contract/test changes and run one copied-temp proof rerun.

Allowed:

- source contract docs;
- focused code/test patches;
- copied DB creation;
- copied-temp materialization;
- validators against copied DB/source packets;
- local evidence and CodeCaptain packet draft.

Forbidden:

- all protected production/external actions listed in the non-authorization section.

Expected outputs:

- `AGENT9178_IMPLEMENTATION_MATRIX.tsv`
- `AGENT9178_VALIDATOR_MATRIX.tsv`
- `AGENT9178_RETAINED_BLOCKER_COUNTS.tsv`
- `COMMANDS_RUN.tsv`
- `CODECAPTAIN_PACKET_DRAFT.md`
- `agent9178_serialized_integrator_copied_temp_rerun_closeout.md`

## Green Criteria

Agent9178 may call copied-temp `GREEN` only if:

- protected production surfaces are unchanged;
- copied DB integrity is `ok`;
- all claimed source contracts are registered and validator-visible;
- ads v1 packets validate without weakening validators;
- missing spend is not zeroed;
- physical stock is not greened from offer availability;
- Universal XL-vs-3XL is resolved by source-backed truth or retained visibly;
- the COGS row is resolved by accepted copied-temp evidence or retained visibly;
- PO/single-truth blockers are closed by exact reconciliation or retained visibly;
- no retained blocker affects the claimed green scope.

If any retained blocker still affects the claimed scope, the proof remains `YELLOW`.

## Launch Rule

Launch Agents9171-9177 in parallel. Do not launch Agent9178 until:

- all seven root closeouts exist;
- no root lane is `RED`;
- the orchestrator has written `ORCHESTRATOR_REVIEW_AFTER_AGENT917_ROOT.md`;
- the review explicitly unlocks Agent9178.
