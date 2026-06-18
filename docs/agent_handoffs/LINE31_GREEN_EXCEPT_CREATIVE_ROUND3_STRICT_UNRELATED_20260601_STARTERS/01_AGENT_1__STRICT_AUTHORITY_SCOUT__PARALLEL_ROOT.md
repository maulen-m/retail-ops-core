# Agent 1 Starter - Strict Blocker Authority Scout

You are Agent 1. Your lane is read-only analysis for the remaining Autonomous Business strict blockers.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-01_line31_green_except_creative_round3_strict_unrelated_repair/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_ROUND3_STRICT_UNRELATED_20260601_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_ROUND3_STRICT_UNRELATED_20260601_STARTERS/01_AGENT_1__STRICT_AUTHORITY_SCOUT__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair_round2/agent1_strict_gate_repair_closeout.md`
7. `~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_repair_round2_20260601/final_synthesis/FINAL_GREEN_EXCEPT_CREATIVE_MATRIX.md`

## Objective

Find the smallest safe authority route for:

- orders `938256969`, `940453925`, `941824782` missing `INVENTORY_ON_DELIVERY_COST`;
- order `909054064` / `SUIT-31-TS_3XL` unresolved production COGS;
- stock snapshot freshness warning in `validate_po_dashboard_invariants.py`.

## Owner Facts

- SHR payment #18 `7000 CNY` counts as paid and supplier-paid.
- `Cash_Balances` in `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx` is current for cash/payment timing.
- Protected reserve is `800000 KZT`.
- LINE31 stock must use exact April leftovers plus PO1-A arrival rebuild.

## Rules

- Read-only only. Do not modify repo files, DB, workbook, source pointers, scheduler, external systems, prices, stock offers, cash, PO, or ads.
- You may create local evidence under your assigned evidence folder and write your closeout.
- Do not treat copied-temp-only COGS as production authority unless you can identify a current durable owner-approved production authority route.
- Do not invent COGS or zero missing balances.

## Required Work

1. Capture current failing outputs:
   - `python3 scripts/validate_params.py --strict`
   - `python3 scripts/validate_on_delivery_freeze.py --until 2026-05-31`
   - `python3 scripts/validate_cogs_integrity.py --as-of 2026-05-31`
   - `python3 scripts/validate_profit_publication_integrity.py --as-of 2026-05-31`
   - `python3 scripts/validate_po_dashboard_invariants.py`
2. Inspect DB rows and source evidence for the four order IDs above.
3. Inspect existing COGS/source contracts for compact child SKUs:
   - `LINE-31-TS`
   - `SUIT-31-LS`
   - `SUIT-31-TS`
4. Decide whether Agent 3 can safely make a production repair, or must close retained YELLOW / request CodeCaptain.
5. Provide exact SQL/code/doc repair recommendation if safe.

## Required Evidence Folder

`~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_round3_strict_unrelated_repair_20260601/agent1_strict_authority_scout/`

## Assigned Closeout

`~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_round3_strict_unrelated_repair/agent1_strict_authority_scout_closeout.md`

Closeout must include standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

Use `GREEN` only if you found a safe, durable production-authority route for Agent 3. Use `YELLOW` if authority remains insufficient but evidence is complete.
