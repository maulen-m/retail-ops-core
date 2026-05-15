# Agent839 - PO Owner Fact Bundle + Current Boundary Carry-Forward

Gate target: `GREEN` if the owner-confirmed PO-4.0 LINE61 facts are packaged as a non-authorizing replacement-source candidate for copied-temp proof, with current boundary drift handled explicitly.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_source_fact_implementation/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_IMPLEMENTATION_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent835_source_decision_synthesis_packet/MVOS_NEXT_CODECAPTAIN_PACKET.md`
6. `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent830_po_inbound_source_decision/PO_INBOUND_SOURCE_DECISION_PACKET.md`
7. `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent835_source_decision_synthesis_packet/MVOS_OWNER_WEB_AUTOMATION_SUPPLEMENT_20260515_143545.md`
8. this starter prompt

## Assignment

Package the owner-confirmed PO-4.0 LINE61 truth as a review-only source bundle candidate, and prepare the PO lane for the next copied-temp proof without touching production.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent839_po_owner_fact_bundle/`

Required packet:

`~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent839_po_owner_fact_bundle/PO_OWNER_FACT_BUNDLE_PACKET.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_fact_implementation/agent839_po_owner_fact_bundle_closeout.md`

## Required Work

- Verify current DB SHA/integrity at start and write it to evidence.
- Record the owner-confirmed facts exactly:
  - ordered/cargo `115`;
  - actual received `92`;
  - short `23`;
  - XL `7`, 2XL `5`, 3XL `6`, 4XL `5`;
  - part total mismatch `1902` actual-received basis vs `1925` ordered/cargo basis, delta `23`.
- Treat this as `OWNER_CONFIRMED_PO_FACTS_FOR_COPIED_TEMP_PROOF_ONLY_NO_PRODUCTION_AUTHORITY`.
- Produce a source-bundle manifest with source text, timestamp, SHA-256 of the packet, line-grain fields, and remaining CodeCaptain question: whether owner-chat confirmation is enough or a canonical artifact is still required.
- Preserve that this does not authorize supplier action, PO commitment, workbook mutation, production DB mutation, or owner publication.
- Include a small carry-forward note for Agent831/Agent834: sales-fact and exception green proofs remain copied-temp only and must be reanchored before any production lane.

## Boundaries

No production DB write, workbook repair, supplier action, PO commitment, source-pointer write, scheduler mutation, external write, owner publication, cash/ads/price/stock action, or lifecycle/status production repair.

You are not alone in the codebase. Do not revert or overwrite edits made by others.

Gate: GREEN
