# Agent840 - Source Fact Synthesis Packet Writer

Do not run this starter until Agents836, 837, 838, and 839 have all written closeouts and the orchestrator has reviewed the gates.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_source_fact_implementation/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_IMPLEMENTATION_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_fact_implementation/agent836_cashflow_compact_sku_bank_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_fact_implementation/agent837_storeb_ads_source_mapping_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_fact_implementation/agent838_lifecycle_webui_archive_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_fact_implementation/agent839_po_owner_fact_bundle_closeout.md`
9. this starter prompt

## Assignment

Synthesize the root source-fact wave into the next CodeCaptain/Oracle packet and decide the minimum safe copied-temp proof route.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent840_source_fact_synthesis/`

Required packet:

`~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent840_source_fact_synthesis/MVOS_SOURCE_FACT_SYNTHESIS_PACKET.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_fact_implementation/agent840_source_fact_synthesis_closeout.md`

## Required Work

- Recheck current DB SHA/integrity and automation pause state.
- Read all four root closeouts and evidence packets.
- Produce updated blocker matrix: cashflow, bank/manual freshness, PO/inbound, STOREB ads, lifecycle/status, sales facts, exception queue, owner publication.
- State whether copied-temp proof can now run, and if yes, name the exact scope and remaining visible blockers.
- Prepare an inert CodeCaptain/Oracle packet. It must not ask for production apply or owner publication.
- If any root gate is `RED`, stop and mark synthesis `RED`.

## Boundaries

No production DB write, workbook write, scheduler mutation, source-pointer write, external write, Web_automation mutation, owner publication, cash movement, supplier payment, PO commitment, ad-platform write, stock change, price change, or lifecycle/status production repair.

You are not alone in the codebase. Do not revert or overwrite edits made by others.

Gate: YELLOW
