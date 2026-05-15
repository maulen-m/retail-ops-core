# Agent816 - Cash/PO/Exception Source Packet

Gate target: `GREEN` if a current owner/source decision packet is built for cash, PO/inbound, and exception blockers without mutating any business state.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_post_order_entry_next_phase_proof_wave/PLAN.md`
4. `~/Docs/Autonomous_business/exports/validation/order_entry_apply_and_daily_survival_parallel/20260515_085748/agent811_cash_po_exception_blocker_board/CASH_PO_EXCEPTION_BLOCKER_BOARD.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent788_cashflow_copy_temp_replay_20260513_121500_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent791_po_inbound_source_decision_20260513_121500_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent792_exception_owner_decision_packet_20260513_121500_closeout.md`
8. this starter prompt

Sibling Agents812-815 are parallel. Do not wait for them.

## Assignment

Build the current source/owner decision packet for:

- fresh bank/manual cash source requirements;
- compact SKU cost blockers for cashflow;
- PO/inbound replacement source bundle and PO-4.0 LINE61 delta `23`;
- 9 open STOCK/HIGH exception rows and required owner/warehouse/source facts.

Write evidence only under:

`~/Docs/Autonomous_business/exports/validation/post_order_entry_next_phase_proof_wave/20260515_0920/agent816_cash_po_exception_source_packet/`

Required output:

`~/Docs/Autonomous_business/exports/validation/post_order_entry_next_phase_proof_wave/20260515_0920/agent816_cash_po_exception_source_packet/CASH_PO_EXCEPTION_OWNER_SOURCE_PACKET.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_post_order_entry_next_phase_proof_wave/agent816_cash_po_exception_source_packet_closeout.md`

## Required Content

- What is known now.
- What source facts are missing.
- Which items can be resolved autonomously with copied-temp proof only.
- Which items require owner/source facts before production action.
- Exact future approval phrases, if any, but keep them inert and clearly non-authorizing.

## Boundaries

Read-only only except assigned evidence and closeout. No production DB writes, workbook writes, scheduler changes, external writes, owner publication, cash movement, supplier payment, PO commitment, ads/bid/budget changes, price changes, stock changes, or lifecycle/status production repair.

Gate: GREEN
