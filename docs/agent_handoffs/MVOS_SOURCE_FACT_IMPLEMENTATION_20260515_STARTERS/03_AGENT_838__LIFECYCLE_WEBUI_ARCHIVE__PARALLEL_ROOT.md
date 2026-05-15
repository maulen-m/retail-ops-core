# Agent838 - Lifecycle / Status WebUI Archive Evidence Packet

Gate target: `GREEN` if fresh pair-level lifecycle/status evidence resolves the remaining unresolved KASPI_DELIVERY pairs for copied-temp proof. Use `YELLOW` if the route works but residual pairs remain.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_source_fact_implementation/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_IMPLEMENTATION_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent835_source_decision_synthesis_packet/MVOS_NEXT_CODECAPTAIN_PACKET.md`
6. `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent833_lifecycle_status_route_decision/LIFECYCLE_STATUS_ROUTE_DECISION_PACKET.md`
7. `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent835_source_decision_synthesis_packet/MVOS_OWNER_WEB_AUTOMATION_SUPPLEMENT_20260515_143545.md`
8. this starter prompt

## Assignment

Use the approved read-only WebUI Archive route to collect or import fresh source evidence for the remaining Agent833 lifecycle/status pairs:

- `145` unresolved KASPI_DELIVERY pairs;
- `9` ACCEPTED, `45` READY, `82` SHIPPED, `9` CANCELLED;
- keep WebUI status-change truth separate from API courier/shipped evidence.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent838_lifecycle_webui_archive/`

Required packet:

`~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent838_lifecycle_webui_archive/LIFECYCLE_WEBUI_ARCHIVE_SOURCE_PACKET.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_fact_implementation/agent838_lifecycle_webui_archive_closeout.md`

## Required Work

- Verify current DB SHA/integrity at start and write it to evidence.
- Identify the unresolved pair list or residual evidence from Agent833/Agent820 artifacts.
- Use existing AB entrypoints, read-only:
  - `~/Docs/Autonomous_business/scripts/run_webui_archive_source_refresh.py`
  - `~/Docs/Autonomous_business/scripts/playwright/download_kaspi_archive_webui.py`
- Prefer `import-existing` if sufficient current ArchiveOrders files already exist. If insufficient, use approved read-only live modes only.
- Produce pair-level evidence coverage: resolved pairs, unresolved pairs, source fields, status_change_at / `Дата изменения статуса` availability, and whether each pair is WebUI lifecycle truth or API-only active/shipped/courier truth.
- Do not synthesize WebUI dates from API dates. If API-backed non-WebUI status contract is needed, describe it as a separate route.

## Boundaries

No production DB apply, workbook mutation, scheduler mutation, source-pointer write, Kaspi/API writes, external-system writes, owner publication, cash/PO/ads/price/stock actions, or lifecycle/status production repair.

Existing scripts may read `.env` or local browser/session state for read-only access, but secrets must not appear in logs or artifacts.

You are not alone in the codebase. Do not revert or overwrite edits made by others.

Gate: YELLOW
