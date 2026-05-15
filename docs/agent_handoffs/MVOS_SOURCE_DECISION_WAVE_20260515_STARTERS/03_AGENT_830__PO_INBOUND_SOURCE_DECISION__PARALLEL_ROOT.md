# Agent830 - PO / Inbound Source Decision

Gate target: `GREEN` if the PO-4.0 LINE61 delta `23` has a source-backed route and copied-temp proof path. Use `YELLOW` if owner/source route selection is still required.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_source_decision_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_DECISION_WAVE_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_execution_wave/agent823_po_inbound_decision_proof_closeout.md`
6. `~/Docs/Autonomous_business/exports/validation/mvos_execution_wave/20260515_111124/agent827_mvos_command_board/MVOS_OWNER_ACTION_LIST.md`
7. this starter prompt

## Assignment

Build the PO/inbound source-decision packet.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent830_po_inbound_source_decision/`

Required report:

`~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent830_po_inbound_source_decision/PO_INBOUND_SOURCE_DECISION_PACKET.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_decision_wave/agent830_po_inbound_source_decision_closeout.md`

## Required Work

- Preserve Agent823 route options exactly: `REFRESH_CANONICAL_WORKBOOK`, `APPROVE_REPLACEMENT_SOURCE_BUNDLE_FOR_COPIED_TEMP_PROOF_ONLY`, and `KEEP_BLOCKED`.
- Re-check current canonical inbound workbook path/SHA/mtime and current validator status.
- Explain the PO-4.0 LINE61 `92` actual received vs `115` cargo/ordered delta `23`, and part total `1902` vs `1925`.
- If a replacement source bundle already exists locally, profile it read-only and state whether it is line-grain enough for copied-temp proof.
- Do not repair or write the workbook.

## Boundaries

Read-only source packet only. No workbook mutation, production DB write, supplier payment/contact, PO commitment, owner publication, scheduler mutation, external write, cash, ads, price, stock, or lifecycle/status production repair.

Gate: GREEN
