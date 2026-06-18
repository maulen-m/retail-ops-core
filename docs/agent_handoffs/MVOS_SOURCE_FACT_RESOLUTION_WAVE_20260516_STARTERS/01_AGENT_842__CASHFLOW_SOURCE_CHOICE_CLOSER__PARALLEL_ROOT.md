# Agent842 - Cashflow Source-Choice Closer

You are Agent842 in the May 16 MVOS source-fact resolution wave.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-16_mvos_source_fact_resolution_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_RESOLUTION_WAVE_20260516_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_RESOLUTION_WAVE_20260516_STARTERS/01_AGENT_842__CASHFLOW_SOURCE_CHOICE_CLOSER__PARALLEL_ROOT.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-16/113013_TASK-000_mvos-current-16c2-partial-proof-codecaptain-clean-repo-refresh/Answer/Code Captain_16.05.2026_12_10_42.md`
8. `~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent836_cashflow_compact_sku_bank/CASHFLOW_COMPACT_SKU_BANK_SOURCE_PACKET.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_fact_implementation/agent836_cashflow_compact_sku_bank_closeout.md`

## Assignment

Resolve the cashflow source-choice blocker without writing production state.

Output must answer:

- What are the exact 8 compact-SKU rows still missing accepted unit-cost truth?
- Which candidate source choices exist: owner override parent carry-forward, Web_automation v6/min-floor, Web_automation v7 fallback, another exact source, or deterministic exclusion?
- Which route is recommended for copied-temp proof?
- Is `src_bank_manual_ingest` still stale, and what is the minimum safe freshness route?
- What exact owner question remains, if any?

## Write Scope

You may write only:

- `~/Docs/Autonomous_business/exports/validation/mvos_source_fact_resolution_wave/20260516_121753/agent842_cashflow_source_choice_closer/`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_resolution_wave/agent842_cashflow_source_choice_closer_closeout.md`

Do not edit repo source files, `.claude/*`, production DB, workbook, scheduler, config, Web_automation, or external systems.

## Stoplines

Stop `RED` if you would need a production write, workbook write, external write, bank write, cash movement, or owner publication to answer.

Stop `YELLOW` if the route requires an owner source choice.

Never treat missing COGS as zero.

## Closeout

Write the closeout first. Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- commands run;
- evidence paths;
- exact recommended route;
- exact owner question if required;
- explicit non-authorization statement.
