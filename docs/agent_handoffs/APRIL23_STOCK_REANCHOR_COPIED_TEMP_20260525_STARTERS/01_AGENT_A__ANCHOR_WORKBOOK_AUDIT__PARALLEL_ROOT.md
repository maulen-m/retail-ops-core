# Agent A - Anchor Workbook Audit

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/PLAN.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/VALIDATOR_MATRIX.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/00_SUBORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/01_AGENT_A__ANCHOR_WORKBOOK_AUDIT__PARALLEL_ROOT.md`

## Assignment

Audit the April 23 anchor workbook read-only. Do not mutate any workbook, DB, source pointer, scheduler, external system, stock, price, cash, PO, or publication surface.

Anchor workbook:

`~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer copy/stock_anchor_selection_and_rebuild_v2_2026-04-23.xlsx`

Required checks:

- SHA256 equals `2474f3834784dc1c8368fd919a81800124e59eccba34fde15129c4d70e937ca2`, or explain mismatch.
- Expected sheets exist.
- `Current_Stock_Rebuild` expected columns exist.
- `stock_id` is unique.
- `sku_key + my_size` is unique or duplicates are listed.
- Risk counts are reported for `HIGH`, `MEDIUM`, `LOW`, `BLOCKED`, negative rows, zero rows, and missing COGS.
- Support sheets are present and summarized.
- `Current_Stock_Rebuild.estimated_current_stock` is confirmed as the replay anchor quantity, not `Composed_Anchor_SKU_Size.anchor_qty`.

## Outputs

Write closeout and evidence under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-25_april23_stock_reanchor_copied_temp/agent_a_anchor_workbook_audit/`

Required files:

- `agent_a_anchor_workbook_audit_closeout.md`
- `APRIL23_ANCHOR_SCHEMA_AUDIT.json`
- `APRIL23_ANCHOR_ROW_PROFILE.tsv`
- `APRIL23_SUPPORT_SHEET_AUDIT.md`

## Gate

Use `Gate: GREEN` only for route readiness if schema, SHA, and uniqueness pass and risk rows are visible.

Use `Gate: YELLOW` if the workbook is usable but retained risks remain.

Use `Gate: RED` for schema mismatch, duplicate active key stopline, mutation, or missing workbook.
