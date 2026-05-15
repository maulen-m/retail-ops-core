# Agent796 Starter - PO/Inbound Source Decision Packet

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent796_po_inbound_source_packet_20260513_192243_closeout.md`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_PLAN_20260513_192243.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_HANDOFF_20260513_192243.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent793_boundary_reanchor_20260513_192243_closeout.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT793_ORCHESTRATOR_REVIEW_ACCEPT_BOUNDARY_GREEN_20260513_193650.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent791_po_inbound_source_decision_20260513_121500_closeout.md`
8. this starter prompt

## Mission

Produce the smallest safe PO/inbound source decision packet for copied-temp proof readiness.

## Scope

Read-only/source-decision work only.

Allowed writes:

- evidence under `~/Docs/Autonomous_business/exports/validation/autonomous_phase0_3_source_truth_wave/20260513_192243/agent796_po_inbound_source_packet/`
- assigned closeout only.

Forbidden:

- canonical workbook replacement;
- production DB/workbook mutation;
- source pointer changes;
- supplier contact;
- PO commitment;
- cash movement;
- owner publication.

## Required Work

1. Verify Agent793 `Domain Status: BOUNDARY_GREEN` and the orchestrator routing review above, then use its boundary.
2. Reconfirm current canonical inbound workbook freshness and consistency status.
3. Inventory fresh local replacement-bundle candidates from E-commerce, Sourcing-Research, payment evidence, and PO artifacts.
4. Separate trusted vs draft sources.
5. Preserve line grain: PO x SKU/component x size.
6. Keep paid/unpaid tied to controlled payment evidence.
7. Keep planned/preorder units separate from received/current sellable stock.
8. Produce one decision packet with three routes:
   - refresh canonical workbook;
   - approve replacement source bundle for copied-temp proof only;
   - keep blocked.
9. Closeout must include:
   - `Gate: GREEN` if the decision packet is complete;
   - `Domain Status: GREEN/YELLOW/RED`;
   - exact stale/validator-red facts;
   - recommended route;
   - exact owner/source input required;
   - non-mutation statement.
