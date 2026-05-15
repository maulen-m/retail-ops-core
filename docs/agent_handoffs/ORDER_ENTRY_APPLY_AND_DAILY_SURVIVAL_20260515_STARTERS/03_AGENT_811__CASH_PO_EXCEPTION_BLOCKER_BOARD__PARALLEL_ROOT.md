# Agent811 - Cash/PO/Exception Blocker Board Read-Only Analyst

Gate target: `GREEN` if you produce a read-only blocker board showing cash risk, PO/inbound, exceptions, lifecycle/status, and what can proceed autonomously versus what needs owner/source facts.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_order_entry_apply_and_daily_survival_parallel/PLAN.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/DAILY_SURVIVAL_BRIEF_V1_20260511_141731.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent788_cashflow_copy_temp_replay_20260513_121500_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent791_po_inbound_source_decision_20260513_121500_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent792_exception_owner_decision_packet_20260513_121500_closeout.md`
8. `~/Docs/Autonomous_business/exports/validation/db_order_entry_owner_approval_request/20260515_085748_final_pre_owner_boundary_recapture/FINAL_PRE_OWNER_BOUNDARY_RECAPTURE.md`
9. this starter prompt

Sibling agents 809 and 810 are parallel. Do not wait for them.

## Assignment

Build the cash/PO/exception/lifecycle blocker board for the next autonomous execution phase.

Write evidence only under:

`~/Docs/Autonomous_business/exports/validation/order_entry_apply_and_daily_survival_parallel/20260515_085748/agent811_cash_po_exception_blocker_board/`

Required output:

`~/Docs/Autonomous_business/exports/validation/order_entry_apply_and_daily_survival_parallel/20260515_085748/agent811_cash_po_exception_blocker_board/CASH_PO_EXCEPTION_BLOCKER_BOARD.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_order_entry_apply_and_daily_survival_parallel/agent811_cash_po_exception_blocker_board_closeout.md`

## Required Content

- Cash risk current state and whether it is decision-grade, review-only, or blocked.
- PO/inbound source status and the exact blocker class if still blocked.
- Exception queue status and which items require owner/source facts.
- Lifecycle/status caveat created by missing `statusChangeDate` and why it is separate from order-entry recovery.
- Autonomous next tasks that are safe without owner intervention after the DB-only order-entry repair.
- Tasks that still require owner approval or source evidence.

## Boundaries

Read-only only. Do not mutate production DB, workbook, scheduler/LaunchAgent/plist/cron, cashflow events, bank balances, PO commitments, supplier payments, source pointers, owner-publication surfaces, Web_automation, browser/session/credential state, external accounts, ads, prices, or stock.

Do not run scheduler controls or `manage_business_automation.py verify`.

Gate: GREEN
