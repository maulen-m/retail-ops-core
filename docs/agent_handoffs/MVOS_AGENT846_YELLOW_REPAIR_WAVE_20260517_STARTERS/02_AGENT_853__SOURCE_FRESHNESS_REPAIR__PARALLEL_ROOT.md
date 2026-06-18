# Agent853 - Source Freshness Repair

You are Agent853 for the Autonomous_business MVOS Agent846 YELLOW repair wave.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_agent846_yellow_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT846_YELLOW_REPAIR_WAVE_20260517_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_post_codecaptain_webui/agent846_full_copied_temp_mvos_proof_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_repair_round2/agent848_cashflow_cogs_balance_repair_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_repair_round2/agent849_storeb_ads_mapping_repair_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_repair_round2/agent850_lifecycle_status_contract_repair_closeout.md`
10. `~/Docs/Oracle/Autonomous_business/2026-05-16/182945_TASK-000_mvos-repair-round2-agent846-codecaptain/Answer/Code Captain_17.05.2026_09_59_38.md`

## Assignment

Repair or precisely preserve Agent846 source freshness blockers:

- `src_ab_db_operational_truth=BLOCKED`
- `src_web_automation_kaspi_marketing_directapi=BLOCKED`
- `src_bank_manual_ingest=STALE`
- `src_facebook_ads_external_ads=STALE`
- `src_payment_evidence_root=STALE`

You may read `~/Docs/Autonomous_business`, `~/Docs/Web_automation`, `~/Docs/Business_3/Facebook_ads`, and existing local evidence. Live read-only source checks are allowed if needed and if they do not write externally.

## Write Scope

Read-only with respect to repo state. Write only:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent853_source_freshness_repair_evidence/`

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent853_source_freshness_repair_closeout.md`

## Not Authorized

Do not mutate production DB, workbooks, scheduler/LaunchAgent/cron state, source pointers, Web_automation, Kaspi/API, ad platforms, bank/cash, PO commitments, stock, prices, owner publication, or external systems.

## Required Work

1. Identify the exact source freshness rows/validators that block Agent846.
2. Map each blocker to an existing or live-read-only evidence route.
3. Build a copied-temp-only source freshness recommendation table for Agent859.
4. Mark each row as `GREEN_ROUTE`, `YELLOW_REVIEW`, or `KEEP_BLOCKED`.
5. Write the closeout with a standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

## Closeout Must Include

- source row by source row status;
- evidence paths and timestamps;
- whether Agent859 can materialize the source row in copied-temp proof;
- exact blockers that must remain blocked;
- explicit non-authorization statement for production apply or external writes.
