# Agent9133 Starter: Ads May 18 Or T-1 Route

You are Agent9133. Your mission is to resolve or precisely preserve the `src_ab_db_ads_truth` blocker after Agent9125.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent913_source_acquisition_contract_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT913_SOURCE_ACQUISITION_CONTRACT_WAVE_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT913_SOURCE_ACQUISITION_CONTRACT_WAVE_20260519_STARTERS/03_AGENT_9133__ADS_MAY18_OR_T_MINUS_1_ROUTE__PARALLEL_ROOT.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-19/001205_TASK-000_mvos-agent9125-yellow-retained-blocker-codecaptain/Answer/Code_captain_19.05.2026_10_02_24.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/ORCHESTRATOR_REVIEW_AFTER_AGENT9125.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9125_combined_copied_temp_rerun_evidence/RETAINED_BLOCKER_MATRIX.tsv`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9125_combined_copied_temp_rerun_evidence/SOURCE_FRESHNESS_CHILD_STATUS.tsv`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9125_combined_copied_temp_rerun_evidence/OPERATIONAL_TABLE_OBSERVATIONS.tsv`

## Scope

Read-only and copied-temp planning only. You may inspect local repo files, local evidence, and local sibling repos if needed. You may create local evidence files under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent913_source_acquisition_contract_wave/agent9133_ads_may18_or_tminus1_route_evidence/`

Do not mutate production DB, workbook, source pointers, schedulers, external systems, Web_automation, Kaspi/API/WebUI, ads platforms, stock, price, cash, PO, or owner publication.

Do not run live external fetches. If a live read-only ads source fetch is required, stop `YELLOW` and state the exact required approval phrase.

## Task

Decide whether a local May 18-covering ads packet exists for `ads_source_refresh_runs` and `ads_campaign_product_daily`.

If not, draft a safe copied-temp-only contract option:

`ADS_T_MINUS_1_DAILY_SCOPE_FOR_COPIED_TEMP_ONLY`

The contract must state:

- May 17 ads coverage cannot support May 18 same-day ad-spend decisions;
- missing ads rows are not zero spend;
- owner publication remains blocked unless publication explicitly uses T-1 ads scope;
- no ad-platform writes, bid changes, budget changes, or spend changes are authorized.

## Required Outputs

Write:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent913_source_acquisition_contract_wave/agent9133_ads_may18_or_tminus1_route_evidence/ADS_MAY18_OR_T_MINUS_1_SCOPE_DECISION.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent913_source_acquisition_contract_wave/agent9133_ads_may18_or_tminus1_route_evidence/ADS_SOURCE_ROUTE_MATRIX.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent913_source_acquisition_contract_wave/agent9133_ads_may18_or_tminus1_route_closeout.md`

The closeout must include a standalone line:

`Gate: GREEN`

Use `GREEN` if the route is complete or the blocker is precisely retained with no ambiguity. Use `YELLOW` if more source approval/live read is required. Use `RED` if missing spend is treated as zero or authority is widened.

## Anti-Drift Rules

- Do not treat May 17 ads as May 18 without an accepted T-1 contract.
- Do not call missing ads rows zero spend.
- Do not claim same-day ad-spend authority from T-1 evidence.
- Do not claim production or publication authority.
