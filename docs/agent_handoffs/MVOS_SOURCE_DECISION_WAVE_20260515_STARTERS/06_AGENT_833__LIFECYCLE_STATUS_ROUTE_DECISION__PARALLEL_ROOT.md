# Agent833 - Lifecycle / Status Route Decision

Gate target: `GREEN` if the 145 unresolved KASPI_DELIVERY pairs have source-backed lifecycle/status route decisions. Use `YELLOW` if more WebUI/API source input is required.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_source_decision_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_DECISION_WAVE_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_execution_wave/agent820_webui_lifecycle_status_copy_proof_closeout.md`
6. `~/Docs/Autonomous_business/exports/validation/mvos_execution_wave/20260515_111124/agent827_mvos_command_board/MVOS_OWNER_ACTION_LIST.md`
7. this starter prompt

## Assignment

Build the lifecycle/status route decision packet for the unresolved rows.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent833_lifecycle_status_route_decision/`

Required report:

`~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent833_lifecycle_status_route_decision/LIFECYCLE_STATUS_ROUTE_DECISION_PACKET.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_decision_wave/agent833_lifecycle_status_route_decision_closeout.md`

## Required Work

- Preserve Agent820 result: explicit WebUI CSV matched `490 / 635`; `145` KASPI_DELIVERY pairs remain unresolved.
- Classify the 145 unresolved pairs by status and date/source availability.
- Keep WebUI `status_change_at` truth separate from API courier/shipped truth.
- If read-only WebUI Archive source refresh or existing downloaded ArchiveOrders imports are available, use them only read-only and write local evidence only.
- Propose the exact route to GREEN: fresh WebUI Archive blocks, API-backed non-WebUI status contract, or keep blocked pending source.

## Boundaries

No production DB write, lifecycle/status production repair, workbook write, scheduler mutation, external write, owner publication, Kaspi/API write, Web_automation mutation, cash, PO, ads, price, or stock change.

Gate: GREEN
