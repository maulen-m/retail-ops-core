# Agent 2 Starter: Kaspi Pay Cash Anchor Evidence Map

Gate: read-only analyst. Do not modify DB, Excel workbooks, source statements, or shared code.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/SOURCE_AUTHORIZATION_ORDER_ENTRY_CASHFLOW_20260504_131100_ALMT.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_3_cashflow_bank_obligations_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/ORCHESTRATOR_FINAL_REVIEW.md`
7. this starter prompt

## Mission

Build a read-only evidence map for converting the provided Kaspi Pay statements and sales reports into a trusted cash anchor through `2026-05-03`.

New source root:

`~/Docs/agent_handoffs/kaspi_pay/20260504_131100/Statements/kaspi_stores`

Prior January backup if needed:

`~/Documents/External_database/snapshots.nosync/20260213_211004/External_database/kaspi_pay/statements/kaspi_stores`

## Required Analysis

1. Inspect statement/report formats by store without exposing account numbers or sensitive transaction details in closeout.
2. Identify the parser/import path already present in the repo, if any.
3. Determine coverage by store and date.
4. Use `2026-05-03` as the complete decision-grade cutoff because `2026-05-04` is partial.
5. Determine what anchor records are required: opening balance, closing balance, last statement date, source path, store, account identity hash or masked identifier, and reconciliation status.
6. Determine whether existing DB cashflow gaps can be reconciled from the provided package.
7. Keep actual cash separate from modeled receivables.

## Hard Rules

- Do not design recurring manual statement downloads as the future daily source.
- Do not convert account balances into fake cash-in events.
- Do not merge `ACTUAL` cash and `MODELED` receivables.
- Do not write to `db/app.db`.
- Do not modify statement/report files.
- Do not include raw bank account numbers, BIN/IIN, or sensitive transaction text in the closeout.

## Closeout

Write closeout to:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/agent_2_kaspi_pay_cash_anchor_closeout.md`

Include:

- Gate: `GREEN`, `YELLOW`, or `RED`.
- Sources inspected.
- Commands run.
- Coverage by store/date.
- Parser/import path found or missing.
- Proposed cash-anchor schema/records.
- Reconciliation risks.
- Exact proposed Phase 2 apply plan and tests.
