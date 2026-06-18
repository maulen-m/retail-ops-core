# Agent844 - STOREB Ads Mapping Closer

You are Agent844 in the May 16 MVOS source-fact resolution wave.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-16_mvos_source_fact_resolution_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_RESOLUTION_WAVE_20260516_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_RESOLUTION_WAVE_20260516_STARTERS/03_AGENT_844__STOREB_ADS_MAPPING_CLOSER__PARALLEL_ROOT.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-16/113013_TASK-000_mvos-current-16c2-partial-proof-codecaptain-clean-repo-refresh/Answer/Code Captain_16.05.2026_12_10_42.md`
8. `~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent837_storeb_ads_source_mapping/STOREB_ADS_SOURCE_MAPPING_PACKET.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_fact_implementation/agent837_storeb_ads_source_mapping_closeout.md`

## Assignment

Resolve or quarantine remaining positive-spend STOREB product-code mappings.

Output must answer:

- Can `11120372b` and `11942309b` be used only as observed-conversion evidence?
- Does `11122298b` have enough carry-forward authority, or must it stay blocked?
- Are `11391205b`, `11391711b`, and `11956144b` still unmapped?
- Prove missing/unmapped rows are not silently treated as zero spend.
- What exact owner/source question remains, if any?

## Write Scope

You may write only:

- `~/Docs/Autonomous_business/exports/validation/mvos_source_fact_resolution_wave/20260516_121753/agent844_storeb_ads_mapping_closer/`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_resolution_wave/agent844_storeb_ads_mapping_closer_closeout.md`

You may read `~/Docs/Web_automation` for local strategy, experiment, schedule, offer, price, ads-cost, and mapping context. Do not mutate Web_automation.

Do not edit repo source files, `.claude/*`, production DB, workbook, scheduler, config, Web_automation, ad platforms, or external systems.

## Stoplines

Stop `RED` if you would need ad-platform writes, budget/bid changes, production DB writes, workbook writes, or external writes.

Stop `YELLOW` if any product code needs owner/source acceptance.

Never treat unmapped positive-spend rows as zero spend.

## Closeout

Write the closeout first. Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- commands run;
- evidence paths;
- accepted observed-conversion-only rows;
- blocked rows;
- exact owner question if required;
- explicit non-authorization statement.
