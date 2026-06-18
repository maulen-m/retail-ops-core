# Agent880 Starter: Synthesis Copied-Temp MVOS Board Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent880_synthesis_copied_temp_board_proof_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business/exports/validation/mvos_owner_qa_repair_wave/20260517_2223/agent880_synthesis_copied_temp_board_proof`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_owner_qa_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_owner_qa_repair_wave/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260517.md`
7. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent875_contract_registry_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent876_ads_current_source_refresh_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent877_lifecycle_api_exposure_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent878_day_complete_status_ledger_repair_closeout.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent879_source_freshness_blocker_board_closeout.md`
13. this starter prompt.

## Assignment

Run the copied-temp MVOS board proof after Agents876-879 complete and the orchestrator has reviewed their closeouts.

You may write only to your assigned evidence folder and assigned closeout, plus minimal repo-local derived evidence if a validator requires it and it remains non-production. Do not edit source code or docs unless the orchestrator explicitly relaunches you for a patch.

Do:

- Capture protected boundary hashes for `db/app.db`, `excel_ui/SALES_KSP_CRM_V3.xlsx`, and `exports/po_dashboard_data.json` if present.
- Check DB integrity.
- Copy production DB into your assigned evidence folder before any copied-temp materialization.
- Consume accepted contract outputs from Agents875-879.
- Run the exact validator matrix supported by the evidence.
- Emit a machine-readable board matrix of contracts, validators, blockers, and gate.
- Use `GREEN` only if validators genuinely pass and no retained blockers are hidden.
- Use `YELLOW_RETAINED_BLOCKER_BOARD_PROOF` if materialization works but blockers remain visible.

Do not:

- production-apply anything;
- mutate workbook, scheduler, source pointers, Web_automation, Kaspi/API/WebUI, ad platforms, cash, PO, stock, price, or owner-publication surfaces;
- treat missing spend as zero;
- synthesize WebUI `status_change_at` from API fields;
- call parent-unit COGS ChildSum production economics;
- hide day-complete or PO failures.

Closeout must include:

- standalone `Gate: <GREEN/YELLOW/RED>` line;
- proof label, including `YELLOW_RETAINED_BLOCKER_BOARD_PROOF` if applicable;
- protected boundary hashes;
- copied DB path and SHA;
- validator commands and exits;
- final blocker board;
- exact recommendation for the next CodeCaptain pack.
