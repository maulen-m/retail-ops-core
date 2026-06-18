# Agent883 Starter: Day-Complete Two-Row Repair

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent883_day_complete_two_row_repair_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent883_day_complete_two_row_repair_evidence`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_retained_blocker_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_retained_blocker_repair_wave/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent878_day_complete_status_ledger_repair_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent880_synthesis_copied_temp_board_proof_closeout.md`
8. this starter prompt.

## Assignment

Resolve or preserve the two remaining day-complete rows:

- `844362551 / ACMEWEAR / CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL`
- `861137901 / UNIVERSAL / CL_NEW-CLO_KIDS_KID-31_BLACK`

Produce:

- `DAY_COMPLETE_FINAL_TWO_ROWS_SIZE_EVIDENCE.csv`
- `DAY_COMPLETE_RERUN_AFTER_FINAL_TWO_ROWS.json` if source evidence is sufficient for a copied-temp rerun
- source manifests/hashes for any evidence used
- assigned closeout with a standalone `Gate: <GREEN/YELLOW/RED>` line

Minimum CSV columns:

- `order_id`
- `store_code`
- `sku_id`
- `evidence_source`
- `assigned_size`
- `my_size`
- `owner_operator_confirmation`
- `proof_scope`
- `production_authority`
- `decision_status`
- `decision_reason`

Read-only evidence search routes:

- `db/app.db` read-only queries;
- local WebUI archive/import evidence;
- CRM/workbook-derived readonly exports if safe;
- prior validation outputs.

Do not:

- invent size truth;
- hide unresolved rows behind exclusions;
- write production DB or workbook;
- mutate scheduler/source pointers/Web_automation/Kaspi/API/WebUI/ad platforms/cash/PO/stock/price/owner publication/external systems.

Gate guidance:

- `GREEN` if both rows are source-backed or explicitly owner/operator-confirmed in inert copied-temp evidence.
- `YELLOW` if one or both rows still need owner/source decision.
- `RED` if evidence contradicts the validator or a protected boundary is violated.
