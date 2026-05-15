# Agent 2 - Ads Source Refresh Analyst

Mode: read-only analyst.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-refresh-owner-review-wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-refresh-owner-review-wave/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_8.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_4_c3_ads_marketing_directapi_truth_closeout.md`
8. `~/Docs/Web_automation/Docs/agent_handoffs/AUTONOMOUS_BUSINESS_KASPI_MARKETING_DIRECT_API_HANDOFF_20260503/00_AB_KASPI_MARKETING_DIRECT_API_HANDOFF.md`
9. This assigned starter prompt.

## Mission

Find the safest, most efficient way to refresh required ads truth so these current blockers can be resolved:

- empty `ads_source_refresh_runs`;
- empty `ads_campaign_product_daily`;
- `ADS_REFRESH_MISSING`;
- `ADS_COVERAGE_MISSING`;
- stale Facebook/Meta source root;
- required Kaspi internal ads stores `ACMEWEAR` and `STOREB`.

## Allowed Work

You may read AB repo files, DB schema/data through read-only SQLite, Web_automation handoff files, local Web_automation scripts/docs, and Facebook_ads docs/source-contract files.

You must not run live browser automation, live DirectAPI calls, live ads writes, or modify Web_automation/Facebook_ads/AB files.

You must not read or print secret values. If credentials are required for a future refresh, report only env variable names or account labels.

## Required Analysis

Determine:

- the exact local evidence and scripts available for Kaspi Marketing DirectAPI read refresh;
- whether Web_automation already has fresh enough artifacts for ACMEWEAR and STOREB;
- how STOREB through Universal switcher must be represented in AB;
- how to populate or stage `ads_source_refresh_runs` and `ads_campaign_product_daily`;
- how to import or point Meta/Facebook evidence without treating missing spend as zero;
- which steps Agent 6 can perform locally, and which require a live source-refresh lane.

## Required Output

Write a concise, source-backed closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files/scripts/tables inspected;
- exact recommended Agent 6 or future ads-agent command sequence;
- required store/account scope;
- expected DB/source effects;
- validation gates;
- blockers;
- `OWNER_ATTENTION_REQUIRED` only if human owner action is truly required, with exact paths and plain-English steps.

Do not read sibling agent reports before writing your own first-pass findings.

ASSIGNED CLOSEOUT: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_2_ads_source_refresh_closeout.md`
