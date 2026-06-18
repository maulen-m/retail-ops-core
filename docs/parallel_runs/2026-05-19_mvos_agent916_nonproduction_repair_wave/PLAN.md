# Agent916 Non-Production MVOS Repair Wave Plan

Created: 2026-05-19 12:48 +05

Gate: OWNER_ENVELOPE_APPROVED_PHASE1_READY

## Source Decision

This plan integrates CodeCaptain's review:

`~/Docs/Oracle/Autonomous_business/2026-05-19/120557_TASK-000_mvos-agent915-yellow-copied-temp-proof-codecaptain/Answer/Code Captain_19.05.2026_12_38_16.md`

CodeCaptain confirmed Agent915 is correctly:

`YELLOW_RETAINED_BLOCKER_BOARD_PROOF_CONFIRMED`

Agent915 is useful copied-temp progress, not copied-temp green proof, not production readiness, and not production preflight/apply approval.

## Objective

Turn the Agent915 yellow retained-blocker board into the smallest safe path toward copied-temp green by repairing concrete source-contract blockers first, then running one full copied-temp MVOS proof rerun.

## Execution Envelope Required Before Launch

No production approval is required for this wave. The owner provided the non-production envelope on 2026-05-19 13:07 +05:

```text
APPROVE NON-PRODUCTION MVOS REPAIR WAVE FOR COPIED-TEMP PROOFS, READ-ONLY ANALYSIS, CONTRACT PATCHES, TESTS, AND EVIDENCE PACKAGING ONLY. NO PRODUCTION DB WRITES, NO WORKBOOK WRITES, NO SCHEDULER CHANGES, NO WEB_AUTOMATION WRITES, NO EXTERNAL WRITES, NO OWNER PUBLICATION, NO CASH MOVEMENT, NO PO COMMITMENT, NO AD SPEND, NO PRICE CHANGES, AND NO STOCK CHANGES.
```

This unlocks Agents9161-9166 read-only/evidence lanes. Agent9167 remains locked until all six Phase 1 closeouts are reviewed.

If owner mapping decisions are needed during execution, use this inert source-decision form:

```text
INERT SOURCE DECISION FOR COPIED-TEMP PROOF ONLY: I confirm the mapping in [MAPPING_TABLE_PATH] may be used for copied-temp MVOS proof. This does not authorize production writes, owner publication, ad spend, price changes, stock changes, cash movement, PO commitment, scheduler changes, or external writes.
```

## Non-Authorization

This plan does not authorize:

- production DB writes;
- workbook writes;
- source-pointer writes;
- scheduler/LaunchAgent/cron changes;
- Web_automation writes;
- Kaspi/API/WebUI mutations;
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

Phase 1 runs six independent read-only/evidence lanes in parallel. These agents write only to the out-of-repo handoff folder.

- Agent9161: stock pricelist contract/materializer route.
- Agent9162: sales identity repair matrix.
- Agent9163: ads packet adapter and STOREB product-code mapping route.
- Agent9164: COGS one-row resolver route.
- Agent9165: day-complete two-row resolver route.
- Agent9166: PO/single-truth reconciliation route.

Phase 2 runs one serialized writer/proof integrator after all six Phase 1 closeouts are reviewed.

- Agent9167: only write-capable lane; may patch contracts/code/tests and run copied-temp proof only within the approved non-production envelope.

## Lane Details

### Agent9161 - Stock Pricelist Contract Route

Purpose:

- decide whether Agent9141 Merchant Cabinet pricelist packets can safely materialize a copied-temp stock snapshot.

Outputs:

- `MERCHANT_CABINET_PRICELIST_STOCK_CONTRACT_RECOMMENDATION.md`;
- `STOCK_PACKET_FIELD_MATRIX.tsv`;
- `STOCK_MATERIALIZER_ACCEPTANCE_GATES.tsv`.

Gate:

- `GREEN` only if the source semantics, zero/missing handling, ACTIVE/ARCHIVE separation, mapping basis, and relation to the 9 `STOCK/HIGH/OPEN` exceptions are fully specified.
- `YELLOW` if Merchant Cabinet quantity cannot be safely treated as canonical snapshot proof.

### Agent9162 - Sales Identity Repair Matrix

Purpose:

- close or retain the strict `sales_fact_v2` identity blockers without weakening evidence rules.

Targets:

- Universal offer `132822924_328581041` for orders `913421682` and `921067176`;
- STOREB orders `914238753`, `914286181`, `914319851`, `914340762`, `914363937`;
- four order-entry quarantine rows from Agent915.

Outputs:

- `SALES_IDENTITY_REPAIR_MATRIX.tsv`;
- `ORDER_ENTRY_QUARANTINE_CLASSIFICATION.tsv`;
- `SALES_STRICT_REBUILD_DECISION.md`.

Gate:

- `GREEN` only if every target row has source-backed mapping or explicit retained quarantine.
- `YELLOW` if any row needs owner source decision.

### Agent9163 - Ads Packet Adapter And STOREB Mapping Route

Purpose:

- adapt Agent9143 evidence into `ads_web_source_packet.v1` without weakening the validator;
- classify every STOREB product-code mapping.

Outputs:

- `ADS_SOURCE_PACKET_V1_ADAPTER_PLAN.md`;
- `ADS_SOURCE_PACKET_V1_REQUIRED_FIELDS.tsv`;
- `STOREB_ADS_PRODUCT_CODE_MAPPING_DECISION_MATRIX.tsv`.

Gate:

- `GREEN` only if the adapter contract can be implemented without Web_automation writes or secrets, and every STOREB code is classified as owner-confirmed, order-entry conversion evidence, exact article map, ambiguous retained blocker, or no-product-truth retained blocker.
- `YELLOW` if owner decisions are required.

### Agent9164 - COGS One-Row Resolver Route

Purpose:

- resolve or retain the single unresolved COGS row/SKU.

Outputs:

- `COGS_SINGLE_UNRESOLVED_ROW_REPAIR.tsv`;
- `COGS_SOURCE_DECISION.md`.

Gate:

- `GREEN` only if the row has source-backed COGS or explicit retained blocker.
- `YELLOW` if source truth is still missing.

### Agent9165 - Day-Complete Two-Row Resolver Route

Purpose:

- repair or retain the two day-complete violations.

Targets:

- `844362551 / ACMEWEAR / CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL`;
- `861137901 / UNIVERSAL / CL_NEW-CLO_KIDS_KID-31_BLACK`.

Outputs:

- `DAY_COMPLETE_TWO_ROW_REPAIR_MATRIX.tsv`;
- `DAY_COMPLETE_SOURCE_DECISION.md`.

Gate:

- `GREEN` only if both rows have source-backed status/size handling or explicit retained blocker.
- `YELLOW` if owner/manual source evidence is needed.

### Agent9166 - PO/Single-Truth Reconciliation Route

Purpose:

- produce the exact canonical refresh route for PO money and single-truth blockers.

Required preservation:

- Line61 shortage remains accepted real business truth:
  - ordered/cargo `115`;
  - actual received `92`;
  - shortage `23`;
  - XL `7`;
  - 2XL `5`;
  - 3XL `6`;
  - 4XL `5`;
  - classification `PO_ACCEPTED_REAL_SHORTAGE_LINE61_2026_05_OWNER_CONFIRMED`.

Outputs:

- `PO_SINGLE_TRUTH_REPAIR_PLAN.md`;
- `PO_PART_HISTORY_MISMATCH_MATRIX.tsv`;
- `PO_BASE_PAYMENT_MISMATCH_MATRIX.tsv`;
- `PO4_TOTAL_WEIGHT_ROUTE.md`.

Gate:

- `GREEN` only if the route preserves Line61 shortage while keeping PO money, part-history, base-payment, and alignment blockers visible.
- `YELLOW` if workbook/DB refresh requires a later production/write approval.

### Agent9167 - Serialized Implementation And Copied-Temp Proof Integrator

Purpose:

- after Agents9161-9166 close out and the orchestrator reviews them, perform the single write-capable non-production implementation/proof lane.

Allowed only after owner envelope is present:

- contract patches;
- focused code/test patches;
- copied DB creation;
- copied-temp-only materialization;
- validator reruns;
- evidence packaging.

Forbidden:

- all production/external/protected writes listed above.

Outputs:

- `AGENT9167_IMPLEMENTATION_MATRIX.tsv`;
- `AGENT9167_VALIDATOR_MATRIX.tsv`;
- `AGENT9167_RETAINED_BLOCKER_COUNTS.tsv`;
- `CODECAPTAIN_PACKET_DRAFT.md`;
- closeout:
  - `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_copied_temp_rerun_closeout.md`.

Gate:

- `GREEN` only if copied-temp validators pass and protected surfaces remain unchanged.
- `YELLOW` if retained blockers remain explicit.
- `RED` for boundary violation or false-green risk.

## Stoplines

Stop immediately if:

- production DB is modified;
- workbook is modified;
- scheduler/LaunchAgent/cron is changed;
- Web_automation is written;
- external systems are written;
- ad-platform changes occur;
- stock/price/cash/PO actions are implied;
- Agent9143 manifest is accepted without `ads_web_source_packet.v1` adaptation;
- Merchant Cabinet pricelist is treated as physical warehouse stock without contract;
- stock source snapshot is called fresh without accepted source packet;
- header-only rows become product truth;
- STOREB ads blocked spend becomes zero spend;
- sales identity mappings are inferred silently;
- Line61 shortage is used to green unrelated PO failures;
- copied-temp proof is called production truth;
- retained blockers are hidden.

## Next Gate

Owner provides the non-production execution envelope, then the orchestrator may launch Agents9161-9166 in parallel under tmux. Agent9167 launches only after all six closeouts are reviewed.
