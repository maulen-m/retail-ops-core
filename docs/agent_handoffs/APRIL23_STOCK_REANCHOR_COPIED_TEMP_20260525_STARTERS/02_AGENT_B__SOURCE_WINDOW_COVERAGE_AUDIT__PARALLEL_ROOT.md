# Agent B - Source Window Coverage Audit

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/PLAN.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/VALIDATOR_MATRIX.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/00_SUBORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/02_AGENT_B__SOURCE_WINDOW_COVERAGE_AUDIT__PARALLEL_ROOT.md`

## Assignment

Audit source coverage for post-anchor replay window `2026-04-24..2026-05-25` read-only.

Do not mutate production DB, workbook, source pointers, scheduler, Web_automation, Kaspi/API/WebUI, external systems, stock, price, cash, PO, or publication surfaces.

Rank sources:

1. DB stock ledger physical-out events with identity and source.
2. API raw order entries with entry IDs and quantity.
3. WebUI ArchiveOrders lifecycle/status for terminal states and `status_change_at`.
4. DB order facts with exact SKU/size and lifecycle.
5. CRM workbook rows with exact identity only when lifecycle is source-backed.
6. May 25 deduction audit for reconciliation only.

## Outputs

Write closeout and evidence under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-25_april23_stock_reanchor_copied_temp/agent_b_source_window_coverage_audit/`

Required files:

- `agent_b_source_window_coverage_audit_closeout.md`
- `POST_ANCHOR_SOURCE_GAP_REPORT.md`
- `POST_ANCHOR_REPLAY_WINDOW_COVERAGE.json`
- `POST_ANCHOR_SOURCE_RANKING_DECISION_DRAFT.md`

## Gate

Use `Gate: GREEN` only when the full replay window is source-covered or every source gap is explicitly bounded and retained.

Use `Gate: YELLOW` when source gaps remain visible.

Use `Gate: RED` if a source gap is hidden or a mutable/external surface is touched.
