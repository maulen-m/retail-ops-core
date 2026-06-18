# Agent849 - STOREB Ads Mapping Repair

You are Agent849 in the May 16 MVOS source-fact repair round 2.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-16_mvos_source_fact_repair_round2/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_REPAIR_ROUND2_20260516_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_REPAIR_ROUND2_20260516_STARTERS/02_AGENT_849__STOREB_ADS_MAPPING_REPAIR__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_resolution_wave/agent844_storeb_ads_mapping_closer_closeout.md`
8. `~/Docs/Autonomous_business/exports/validation/mvos_source_fact_resolution_wave/20260516_121753/agent844_storeb_ads_mapping_closer/AGENT844_BLOCKED_POSITIVE_SPEND_ROWS.csv`
9. `~/Docs/Autonomous_business/exports/validation/mvos_source_fact_resolution_wave/20260516_121753/agent844_storeb_ads_mapping_closer/AGENT844_ACCEPTED_OBSERVED_CONVERSIONS.csv`

## Assignment

Repair or keep blocked the four positive-spend STOREB ads product codes from Agent844:

- `11122298b`
- `11391205b`
- `11391711b`
- `11956144b`

You may read `~/Docs/Web_automation` read-only for local strategy, experiments, schedules, offer prices, ads costs, and mapping context. You may use existing local Autonomous_business evidence. If local evidence is insufficient and existing repo read-only API methods are available, you may use read-only fetches only; do not mutate external systems.

You must:

- preserve `11120372b` and `11942309b` as observed-conversion-only accepted rows unless stronger evidence is found;
- produce a product-code mapping matrix for all six Agent844 rows;
- prove blocked positive spend remains positive spend and is not zeroed;
- identify any exact owner/CodeCaptain decision still required.

## Write Scope

You may write only:

- `~/Docs/Autonomous_business/exports/validation/mvos_source_fact_repair_round2/20260516_154410/agent849_storeb_ads_mapping_repair/`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_repair_round2/agent849_storeb_ads_mapping_repair_closeout.md`

Do not edit Autonomous_business source files, `.claude/*`, production DB, workbook, scheduler, config, Web_automation, ad platforms, or external systems.

## Stoplines

Stop `RED` if ad-platform writes, production DB writes, workbook writes, Web_automation mutation, or external writes are required.

Stop `YELLOW` if any positive-spend row still needs owner/source acceptance.

Never treat unmapped positive-spend rows as zero spend.

## Closeout

Write the closeout first. Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- evidence paths;
- accepted rows;
- blocked rows and positive-spend total;
- commands run;
- exact owner/source question if any;
- explicit non-authorization statement.
