# Web Automation Ads Data Gathering Starters

Created: `2026-05-05`

Purpose: launch Web_automation-domain execution agents to gather read-only Kaspi Marketing evidence for the Autonomous_business ads source refresh blocker.

## Parallel Metadata

- Parallel group: `web_automation_ads_data_gathering`
- Execution mode: both agents can start in parallel.
- Owner repo for execution: `~/Docs/Web_automation`
- Authority repo for downstream repair: `~/Docs/Autonomous_business`
- Web_automation agents must not write `~/Docs/Autonomous_business`, production `db/app.db`, Kaspi campaign state, bids, budgets, products, names, enablement, or merchant settings.

## Prompt Files

1. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_source_truth_blocker_unblock_wave2/web_automation_ads_data_gathering_starters/01_AGENT_WA_ACMEWEAR__KASPI_MARKETING_READONLY_DATA_GATHER__PARALLEL.md`
2. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_source_truth_blocker_unblock_wave2/web_automation_ads_data_gathering_starters/02_AGENT_WA_STOREB__UNIVERSAL_SWITCHER_KASPI_MARKETING_READONLY_DATA_GATHER__PARALLEL.md`

## Copy-Paste Launch Lines

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_source_truth_blocker_unblock_wave2/web_automation_ads_data_gathering_starters/01_AGENT_WA_ACMEWEAR__KASPI_MARKETING_READONLY_DATA_GATHER__PARALLEL.md
```

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_source_truth_blocker_unblock_wave2/web_automation_ads_data_gathering_starters/02_AGENT_WA_STOREB__UNIVERSAL_SWITCHER_KASPI_MARKETING_READONLY_DATA_GATHER__PARALLEL.md
```

## Why Web_automation Agents

Agent 11 proved the Autonomous_business repair path is clear but not green from local evidence:

- raw blockers remain `ADS_REFRESH_MISSING=4138` and `ADS_COVERAGE_MISSING=4138`;
- effective ads-required subset is `ACMEWEAR=797` and `STOREB=238`;
- current local evidence covers only `175` effective rows, all `ACMEWEAR`;
- `STOREB` active-window coverage is absent and must be refreshed from the correct marketing account identity.

The Web_automation repo owns the current read-only Kaspi Marketing fetcher and browser/session flow. These prompts ask it to produce source evidence only; Autonomous_business Agent 12 will do the importer/materializer work after this data exists.
