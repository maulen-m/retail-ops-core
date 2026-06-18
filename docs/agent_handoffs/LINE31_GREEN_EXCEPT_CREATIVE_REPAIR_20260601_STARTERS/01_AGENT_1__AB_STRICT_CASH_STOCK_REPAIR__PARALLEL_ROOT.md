# Agent 1 Starter - Autonomous_business Strict Gate, Cash, And Stock Repair

You are Agent 1. Your lane is the write-capable Autonomous_business repair lane for LINE31 `GREEN_EXCEPT_CREATIVE`.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-01_line31_green_except_creative_repair/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_20260601_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_20260601_STARTERS/01_AGENT_1__AB_STRICT_CASH_STOCK_REPAIR__PARALLEL_ROOT.md`

## Owner Facts To Apply

- Protected reserve is `800000 KZT`.
- Cash source is `Cash_Balances` plus SHR payments log in `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`.
- The 18th `7000 CNY` SHR payment is paid and supplier-paid, even though receipt screenshot is pending.
- LINE31 stock source is exact rebuild from April leftovers plus PO1-A arrival.
- Creative assets are still pending and must not block your lane.

## Scope

Allowed:

- edit `Autonomous_business` docs/scripts/tests/config and local evidence;
- run validators;
- perform production DB/workbook mutation only if strictly necessary, backup-first, narrow, write-gated, and followed by validator replay.

Forbidden:

- Meta publish;
- website deploy;
- campaign/promo/bid/budget changes;
- cash movement, supplier payment, PO commitment;
- owner publication;
- internal LINE31 Kaspi isolation.

## Task

Repair or classify current strict gate failures before final LINE31 readiness synthesis:

- `inbound_sheet_consistency`: encode owner truth for PO-4.0 LINE61 shortage if the validator is treating cargo 115 as received instead of accepted received 92.
- `single_truth_system`: repair or classify workbook/DB mismatches with exact source paths and no hand-waving.
- `on_delivery_freeze`: repair missing `INVENTORY_ON_DELIVERY_COST` balances if a deterministic source exists; otherwise produce a fail-closed blocker with row list.
- `business_insides`: create the missing `2026-05-31` snapshot if source data is sufficient.
- `cogs_integrity` / `profit_publication_integrity`: repair the one unresolved `SUIT-31-TS` COGS/publication issue if source truth exists.
- `dim_sku_light_alignment`: repair or classify the 10 weight mismatches.
- refresh the LINE31 cash gate using `800000 KZT` protected reserve and owner-confirmed `7000 CNY` payment.
- refresh LINE31 stock gate using April leftovers plus PO1-A arrival rebuild.

## Required Outputs

Evidence folder:

`~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_repair_20260601/agent1_ab_strict_cash_stock/`

Required files:

- `strict_gate_before_after.md`
- `strict_gate_failure_repair_matrix.csv`
- `cash_shr_reserve_refresh.json`
- `line31_april_po1a_stock_refresh.csv`
- `production_mutation_ledger.md`
- `COMMANDS_RUN.tsv`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair/agent1_ab_strict_cash_stock_repair_closeout.md`

Closeout must include standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

Use `GREEN` only if strict gate is green or every remaining strict failure is explicitly proven unrelated and accepted by a durable launch-readiness rule. Use `YELLOW` for retained blocker. Use `RED` for unsafe mutation or production drift.
