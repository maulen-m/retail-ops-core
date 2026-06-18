# Agent 3 - LINE31 Stock Cash PO Guard

Before executing, read:
1. `~/AGENTS.md`
2. `~/Docs/Autonomous_business/AGENTS.md`
3. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-06_line31_expert_plan_completion_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_EXPERT_PLAN_COMPLETION_WAVE_20260606_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. This assigned starter prompt.

Workdir:

`~/Docs/Autonomous_business`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_expert_plan_completion_wave/agent3_stock_cash_po_guard_closeout.md`

Assigned evidence root:

`~/Docs/Autonomous_business/exports/validation/line31_expert_plan_completion_20260606/agent3_stock_cash_po_guard`

## Task

Refresh or verify LINE31 stock/cash/PO guard for the expert plan. Keep stock truth, cash truth, and PO/payable truth separate.

Verify:

- Latest LINE31 stock packet and current sellable/available/not-for-sale values.
- Whether LINE31 stock remains safe for the current $55/day controlled-scale test.
- Latest cash balance source timestamp and whether it is same-day.
- SHR/ARC/PO payable context only if source-backed from local evidence.
- Whether lack of same-day cash source should keep the guard YELLOW.

Use read-only commands and local evidence only. You may inspect:

- `~/Docs/Autonomous_business/exports/validation/product_truth_yellow_to_apply_ready_20260529_123827`
- `~/Docs/Autonomous_business/exports/validation/product_truth_yellow_to_apply_ready_20260529_123827/product_truth_apply_ready_workbook.xlsx`
- `~/Docs/Autonomous_business/exports/validation/product_truth_yellow_to_apply_ready_20260529_123827/product_truth_yellow_to_apply_ready_manifest.json`
- latest cash balance files and `_sync` artifacts under the PO workbook area.

Do not mutate the workbook or DB.

## Forbidden

No production DB writes, workbook writes, source-pointer writes, scheduler changes, WebUI/Kaspi/API writes, Meta writes, website deploys, stock changes, price changes, cash movement, supplier payment, PO commitment, or owner publication.

## Gate

`GREEN` if stock is safe and cash/PO guard has same-day source-backed confirmation.

`YELLOW` if stock is safe but cash/PO source is stale or needs owner confirmation.

`RED` if LINE31 stock is unsafe for current spend, cash/PO evidence contradicts scale, or a forbidden write occurs.

## Closeout Requirements

Include `Gate: <GREEN/YELLOW/RED>`, source paths, timestamps, LINE31 stock table summary, cash/PO freshness table, current scale recommendation, and no-write attestation.
