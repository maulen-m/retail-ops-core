# Agent813 - Copied-Temp Downstream Replay

Gate target: `GREEN` if a copied DB replay proves what downstream surfaces can safely derive after the order-entry production apply, while preserving all warning cohorts and avoiding production mutation.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_post_order_entry_next_phase_proof_wave/PLAN.md`
4. `~/Docs/Autonomous_business/exports/validation/db_order_entry_owner_apply/20260515_091102_authorized_db_only_order_entry_apply/DB_ORDER_ENTRY_PRODUCTION_APPLY_CLOSEOUT.md`
5. `~/Docs/Autonomous_business/exports/validation/order_entry_apply_and_daily_survival_parallel/20260515_085748/agent811_cash_po_exception_blocker_board/CASH_PO_EXCEPTION_BLOCKER_BOARD.md`
6. this starter prompt

Sibling Agents812, 814, 815, and 816 are parallel. Do not wait for them.

## Assignment

Create a copied-temp DB from current `db/app.db` only after confirming the production DB SHA is:

`9702c20cad71b808e52cf746c8574506aafe3f1f4d18fc6a2c48ee4880f98816`

Run downstream replay/proof on the copy only. Prioritize:

- order-entry freshness;
- `sales_fact_v2` rebuild or validator route if available;
- operational stock integration gates;
- cashflow translation/validator feasibility;
- owner-truth/owner-publication blockers as read-only or copied-temp diagnostics;
- warning cohort preservation: `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED=249`, `ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED=23`.

Write evidence only under:

`~/Docs/Autonomous_business/exports/validation/post_order_entry_next_phase_proof_wave/20260515_0920/agent813_copied_temp_downstream_replay/`

Required output:

`~/Docs/Autonomous_business/exports/validation/post_order_entry_next_phase_proof_wave/20260515_0920/agent813_copied_temp_downstream_replay/COPIED_TEMP_DOWNSTREAM_REPLAY.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_post_order_entry_next_phase_proof_wave/agent813_copied_temp_downstream_replay_closeout.md`

## Boundaries

You may mutate only your copied DB under your evidence folder. Never set a production write gate. Never mutate `~/Docs/Autonomous_business/db/app.db`.

If a script needs an apply flag for copied DB mutation, use it only against the copied DB and record the command. If a script cannot be proven copy-only, stop `YELLOW`.

No workbook writes, scheduler changes, external writes, owner publication, cash movement, PO commitment, ads/bid/budget change, price change, stock change, or production lifecycle/status repair.

Gate: GREEN
