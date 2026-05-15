# Agent823 - PO / Inbound Decision Proof Analyst

Gate target: `GREEN` if you isolate PO/inbound blockers and route options without creating PO/payment authority.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_execution_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_EXECUTION_WAVE_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_post_order_entry_next_phase_proof_wave/agent816_cash_po_exception_source_packet_closeout.md`
6. this starter prompt

## Assignment

Create a decision memo for PO/inbound blockers.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_execution_wave/20260515_111124/agent823_po_inbound_decision_proof/`

Required report:

`PO_INBOUND_DECISION_PROOF.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_execution_wave/agent823_po_inbound_decision_proof_closeout.md`

## Required Content

- PO-4.0 LINE61 `92` vs `115`, delta `23`.
- Part total `1902` vs `1925`, delta `23`.
- Source route options: `REFRESH_CANONICAL_WORKBOOK`, `APPROVE_REPLACEMENT_SOURCE_BUNDLE_FOR_COPIED_TEMP_PROOF_ONLY`, or `KEEP_BLOCKED`.
- What needs owner decision vs data repair vs copied-temp proof.
- No supplier payment or PO commitment recommendation.

## Boundaries

Read-only only except assigned evidence and closeout. No workbook mutation, production DB write, supplier contact/payment, PO commitment, cash movement, stock change, price change, scheduler change, external write, or owner publication.

Gate: GREEN
