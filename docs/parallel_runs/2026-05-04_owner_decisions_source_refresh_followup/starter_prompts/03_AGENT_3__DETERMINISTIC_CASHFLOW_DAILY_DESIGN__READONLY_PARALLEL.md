# Agent 3 Starter: Deterministic Daily Cashflow Design

Gate: read-only analyst. Do not modify DB, Excel workbooks, source statements, or shared code.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
4. `~/Docs/Autonomous_business/config/payout_model.yaml`
5. `~/Docs/Autonomous_business/config/bank_accounts.yaml`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/SOURCE_AUTHORIZATION_ORDER_ENTRY_CASHFLOW_20260504_131100_ALMT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_3_cashflow_bank_obligations_closeout.md`
8. this starter prompt

## Mission

Design the minimum safe repo-native workflow that stops relying on manual daily bank statement downloads.

The target operating model:

- ingest the latest provided statement/report package as a trusted cash anchor;
- fetch Kaspi orders and sales daily through existing API paths;
- compute expected payouts/receivables deterministically from order lifecycle and payout rules;
- reconcile expected movement against latest cash anchor and periodic balance anchors;
- fail closed when API data, lifecycle status, payout model, or anchor freshness is insufficient.

## Required Analysis

1. Identify existing scripts, tables, and configs that already model Kaspi orders, sales, payouts, receivables, and cashflow.
2. Propose the smallest authoritative data contract for daily cashflow after the anchor.
3. Define actual-vs-modeled state transitions.
4. Define stale/missing/duplicate event handling.
5. Define required validators before cashflow can publish green.
6. Define what still needs periodic human owner action, if anything, and how often.
7. Identify the minimum Phase 2 implementation slices and which must be serialized.

## Hard Rules

- Do not require daily manual statement downloads.
- Do not treat modeled receivables as cash on hand.
- Do not use dashboard/UI math as source of truth.
- Do not widen tolerances just to pass.
- Do not write to `db/app.db`.
- Do not modify source files unless a later executor prompt explicitly authorizes it.

## Closeout

Write closeout to:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/agent_3_deterministic_cashflow_daily_design_closeout.md`

Include:

- Gate: `GREEN`, `YELLOW`, or `RED`.
- Existing components found.
- Proposed daily workflow.
- Required data contracts.
- Failure/stopline rules.
- Human-owner touchpoints remaining.
- Exact proposed Phase 2 implementation slices and tests.
