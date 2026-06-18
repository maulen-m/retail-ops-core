# Agent855 - STOREB Ads 11956144b Repair

You are Agent855 for the Autonomous_business MVOS Agent846 YELLOW repair wave.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_agent846_yellow_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT846_YELLOW_REPAIR_WAVE_20260517_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_post_codecaptain_webui/agent846_full_copied_temp_mvos_proof_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_repair_round2/agent849_storeb_ads_mapping_repair_closeout.md`
8. `~/Docs/Oracle/Autonomous_business/2026-05-16/182945_TASK-000_mvos-repair-round2-agent846-codecaptain/Answer/Code Captain_17.05.2026_09_59_38.md`

## Assignment

Resolve or preserve the STOREB ads blocker:

```text
campaign/ad key 11956144b
positive spend gap 90.00 KZT
```

The row must not be zeroed or silently mapped. Find exact source truth if possible. The user explicitly confirmed that Web_automation stores strategy, experiment letters, schedules, product groups, offer prices, ad costs, and related context for ACMEWEAR/STOREB routes. You may read that repo and existing API method references. Read-only live ads/API fetch is allowed if needed, with no ad-platform writes.

## Write Scope

Read-only with respect to repo state. Write only:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent855_storeb_ads_11956144b_repair_evidence/`

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent855_storeb_ads_11956144b_repair_closeout.md`

## Not Authorized

Do not mutate production DB, Web_automation, workbooks, schedulers, Kaspi/API state, ad platforms, budgets, bids, owner publication, cash, PO, stock, or prices.

## Required Work

1. Locate every local reference to `11956144b`.
2. Compare it against accepted STOREB ad rows and duplicate-name risk from Agent849 and CodeCaptain.
3. If direct API/read-only source truth can identify product mapping, record the exact evidence.
4. If still ambiguous, keep it blocked with the exact next source needed.
5. Produce an Agent859-ready recommendation: `MAP_TO_<PRODUCT>`, `OBSERVED_ONLY`, or `KEEP_BLOCKED`.
6. Write the closeout with a standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

## Closeout Must Include

- exact mapping decision for `11956144b`;
- spend amount and source path/timestamp;
- duplicate-name risk result;
- whether Agent859 may materialize anything in copied-temp proof;
- explicit non-authorization statement for production apply or ad-platform writes.
