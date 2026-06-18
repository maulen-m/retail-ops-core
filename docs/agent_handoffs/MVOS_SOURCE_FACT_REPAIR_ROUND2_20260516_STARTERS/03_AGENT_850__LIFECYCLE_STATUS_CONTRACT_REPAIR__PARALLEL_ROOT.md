# Agent850 - Lifecycle Status Contract Repair

You are Agent850 in the May 16 MVOS source-fact repair round 2.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-16_mvos_source_fact_repair_round2/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_REPAIR_ROUND2_20260516_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_REPAIR_ROUND2_20260516_STARTERS/03_AGENT_850__LIFECYCLE_STATUS_CONTRACT_REPAIR__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_resolution_wave/agent845_lifecycle_status_residual_route_closeout.md`
8. `~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent838_lifecycle_webui_archive/LIFECYCLE_WEBUI_ARCHIVE_SOURCE_PACKET.md`

## Assignment

Repair the `112` lifecycle/status residual route or prepare the exact contract packet needed to keep it blocked cleanly.

You must:

- preserve the accepted `33` WebUI status-change pairs as copied-temp-only WebUI truth;
- reclassify the `112` residual pairs from Agent845;
- check whether existing local API/current-status, courier, shipment, or WebUI Archive evidence can safely support a separate non-WebUI contract;
- if fresh WebUI Archive rows are available locally, use them as evidence;
- if the only safe route is a new contract, write the exact owner/CodeCaptain contract language and keep the gate `YELLOW`;
- never synthesize WebUI `status_change_at` from API/current/courier/shipment evidence.

You may use read-only WebUI Archive/local evidence discovery if needed. Do not mutate production DB, workbook, scheduler, WebUI, Kaspi state, or external systems.

## Write Scope

You may write only:

- `~/Docs/Autonomous_business/exports/validation/mvos_source_fact_repair_round2/20260516_154410/agent850_lifecycle_status_contract_repair/`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_repair_round2/agent850_lifecycle_status_contract_repair_closeout.md`

## Stoplines

Stop `RED` if production lifecycle repair, DB/workbook mutation, scheduler mutation, Kaspi/API state mutation, or external writes are required.

Stop `YELLOW` if the residuals require a new owner/CodeCaptain source-rule decision.

Do not synthesize WebUI lifecycle truth from non-WebUI evidence.

## Closeout

Write the closeout first. Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- accepted `33` pair basis;
- residual `112` classification;
- contract language if required;
- evidence paths;
- commands run;
- explicit non-authorization statement.
