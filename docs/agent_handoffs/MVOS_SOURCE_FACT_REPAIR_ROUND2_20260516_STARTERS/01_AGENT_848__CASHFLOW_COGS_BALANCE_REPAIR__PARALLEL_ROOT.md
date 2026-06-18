# Agent848 - Cashflow COGS And Balance Repair

You are Agent848 in the May 16 MVOS source-fact repair round 2.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-16_mvos_source_fact_repair_round2/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_REPAIR_ROUND2_20260516_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_REPAIR_ROUND2_20260516_STARTERS/01_AGENT_848__CASHFLOW_COGS_BALANCE_REPAIR__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_resolution_wave/agent842_cashflow_source_choice_closer_closeout.md`
8. `~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent836_cashflow_compact_sku_bank/CASHFLOW_COMPACT_SKU_BANK_SOURCE_PACKET.md`

## Assignment

Convert the newly supplied owner truth into a copied-temp-only cashflow repair packet.

Owner-approved COGS truth for copied-temp only:

- `LINE-31-TS=6006.76 KZT` from `CL_OC_MEN_LINE51_WHITE`
- `SUIT-21-TS=5567.22 KZT` from `CL_NEW-CLO2_MEN_SUIT-61_BLACK`
- `SUIT-31-LS=5567.22 KZT` from `CL_NEW-CLO2_MEN_SUIT-61_BLACK`
- `SUIT-31-TS=5567.22 KZT` from `CL_NEW-CLO2_MEN_SUIT-61_BLACK`
- include cancelled order `912293165`

Manual balance source:

`~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`

Use sheet `Cash_Balances`, latest snapshot `16.05.2026 15:18:00`, and preserve the separate owner-stated reserve deposit of `1,500,000 KZT` as untouched reserve buffer.

You must:

- read the workbook read-only;
- hash the workbook;
- extract the latest `Cash_Balances` snapshot and totals;
- write a local evidence packet with COGS decisions and balance/reserve basis;
- decide whether Agent842's copied-temp cashflow blocker is now repaired;
- never write production DB, config, bank source files, or workbooks.

## Write Scope

You may write only:

- `~/Docs/Autonomous_business/exports/validation/mvos_source_fact_repair_round2/20260516_154410/agent848_cashflow_cogs_balance_repair/`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_repair_round2/agent848_cashflow_cogs_balance_repair_closeout.md`

## Stoplines

Stop `RED` if production DB/config/workbook mutation, bank write, cash movement, or external write is required.

Stop `YELLOW` if the owner truth is insufficient to support copied-temp cashflow proof.

Never treat missing COGS as zero.

## Closeout

Write the closeout first. Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- workbook hash and snapshot timestamp;
- extracted balance totals and `1,500,000 KZT` reserve-buffer handling;
- exact COGS source decisions;
- evidence paths;
- commands run;
- explicit non-authorization statement.
