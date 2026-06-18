# Agent877 Starter: Lifecycle API Exposure Materialization

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent877_lifecycle_api_exposure_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent877_lifecycle_api_exposure_evidence`

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
9. this starter prompt.

## Assignment

Build copied-temp-only evidence for the five owner-accepted lifecycle rows under this exact contract:

`API_CANCELLING_NON_DELIVERED_EXPOSURE_FOR_COPIED_TEMP_ONLY_NO_WEBUI_STATUS_CHANGE_AT`

You may read repo files, copied evidence, API raw evidence, WebUI archive manual imports, and local DB copies. You may create temporary copied DBs or local analysis files only inside your assigned evidence folder. You may write only to your assigned evidence folder and assigned closeout. Do not edit repo files.

Do:

- Identify the five `KASPI_DELIVERY / CANCELLING` lifecycle rows and their evidence.
- Prove the contract does not create WebUI `status_change_at`.
- Prove the contract does not mark rows as `WEBUI_CANCELLED`.
- Prove the contract does not recognize delivered cash-in or sales revenue.
- Prove the contract does not add active stock back while `returnedToWarehouse=false`.
- Keep the optional later manual WebUI upgrade path separate.
- Produce a small machine-readable matrix of the five rows.

Do not:

- write production DB;
- write workbook;
- mutate scheduler, source pointers, Web_automation, Kaspi/API/WebUI, or external systems;
- treat API status as WebUI status-change truth;
- hide uncertainty.

Closeout must include:

- standalone `Gate: <GREEN/YELLOW/RED>` line;
- exact row matrix and source evidence;
- commands run and exits;
- copied-temp proof recommendation for Agent880;
- remaining blockers or CodeCaptain questions.
