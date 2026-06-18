# Agent911D / Transport Agent9114 - Inbound Workbook Schema Correction

Gate target: `GREEN` if the validator can read the migrated canonical workbook fields with tests, otherwise `YELLOW` with exact ambiguous columns/cells needing human decision.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/04_AGENT_9114__INBOUND_WORKBOOK_SCHEMA_CORRECTION__PARALLEL_ROOT_SERIALIZED_CODE.md`
6. `~/Docs/Autonomous_business/exports/validation/mvos_option1_next_repair_wave/agent910_copied_temp_contract_proof/AGENT910_COPIED_TEMP_CONTRACT_PROOF_CLOSEOUT.md`
7. `~/Docs/Autonomous_business/docs/inventory/Excel_UI_Contract_for_CRM_V1.md`

## Assignment

Fix the inbound workbook schema parser/validator route for recent owner workbook format edits. This is the only root lane allowed to edit repo code/tests.

Owner truth:

- Missing `To_pay_BASE_KZT` / `To_pay_DLV_KZT` is not expected.
- The workbook/source likely changed format because of recent owner edits.
- Overall workbook architecture remains canonical priority.
- Inspect migrated cells/columns and correct parsing/validator logic if safe.
- Do not edit the workbook.

## Required Work

1. Verify protected boundary before analysis.
2. Inspect the inbound workbook read-only:
   - `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`
3. Identify whether `To_pay_BASE_KZT` and `To_pay_DLV_KZT` moved, were renamed, or became derived cells.
4. If the mapping is unambiguous:
   - update owning doc first if business-facing schema behavior changes;
   - add focused tests;
   - patch the validator/parser narrowly;
   - rerun focused tests and PO money-gate on copied DB where appropriate.
5. If the mapping is ambiguous:
   - do not guess;
   - output candidate columns/cells and ask human for exact mapping.

## Write Scope

Allowed repo write scope:

- `docs/inventory/Excel_UI_Contract_for_CRM_V1.md` or a narrower owning validation doc if needed;
- the specific inbound workbook validation/parser script(s);
- focused tests for the validator/parser;
- local evidence and closeout files.

Forbidden:

- workbook writes;
- production DB writes;
- broad refactors;
- changing PO formulas without owner/source contract.

## Outputs

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911d_inbound_workbook_schema_correction_closeout.md`

Evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911d_inbound_workbook_schema_correction_evidence`

Required artifacts:

- `INBOUND_WORKBOOK_SCHEMA_SCAN.tsv`
- `TO_PAY_FIELD_MAPPING_DECISION.md`
- `VALIDATOR_EXIT_MATRIX.tsv`
- focused test output
- closeout with changed file paths

## Stoplines

- Stop `YELLOW` if multiple plausible migrated mappings exist.
- Stop `RED` if protected DB/workbook boundary changed before start.
- Do not edit the workbook.
- Do not weaken the validator to ignore required money fields.
