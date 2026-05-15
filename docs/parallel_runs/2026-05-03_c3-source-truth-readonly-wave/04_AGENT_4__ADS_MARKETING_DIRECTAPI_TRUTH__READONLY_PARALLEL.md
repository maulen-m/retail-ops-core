# Agent 4 - Ads, Marketing, And Kaspi DirectAPI Truth

Assigned closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_4_c3_ads_marketing_directapi_truth_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/ops/OPERATIONAL_DECISION_POLICY_V1.md`
7. `~/Docs/Autonomous_business/config/operational_decision_policy.yaml`
8. `~/Docs/Web_automation/Docs/agent_handoffs/AUTONOMOUS_BUSINESS_KASPI_MARKETING_DIRECT_API_HANDOFF_20260503/00_AB_KASPI_MARKETING_DIRECT_API_HANDOFF.md`
9. `~/Docs/Web_automation/Docs/agent_handoffs/AUTONOMOUS_BUSINESS_KASPI_MARKETING_DIRECT_API_HANDOFF_20260503/acmewear_child_bundle_campaign_registry.csv`
10. this assigned starter prompt.

## Mode

Read-only analyst. Do not edit repo files, `.claude/*`, DB, Web_automation files, env files, browser sessions, Kaspi Marketing UI, DirectAPI, ads platforms, or external systems. The only allowed write is your assigned closeout.

This prompt does not authorize live API/browser login or any DirectAPI call. Analyze local evidence and design the AB ingestion/control contract only.

## Mission

Define the C3 ads truth and Kaspi Marketing DirectAPI integration contract.

Cover:

- active Kaspi internal ads stores: ACMEWEAR and STOREB;
- STOREB access workaround via Universal marketing cabinet store switcher;
- missing ads data must block profit publication;
- new ACMEWEAR child-bundle campaign registry with 8 campaign IDs, budgets `12000`, bids `40`, states `Enabled`;
- campaign ID and product SKU as durable identity;
- separate parent LINE61, LINE51, and child-bundle lanes;
- required AB tables/sidecars for campaign registry, daily snapshots, action ledger, dry-run control plans, and post-verify rows;
- how external Meta/Instagram data from `~/Docs/Business_3/Facebook_ads` should be routed;
- stoplines before any future live DirectAPI control action.

## Required Closeout Content

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- Web_automation handoff paths read;
- parsed summary of the 8 campaign registry rows;
- proposed AB schema/contracts and Agent 7 tests;
- clear classification: read-only-ready, dry-run-ready, or live-write-ready. Wave 1 should not claim live-write-ready unless evidence is overwhelming and still requires owner approval;
- explicit confirmation that no Web_automation files, AB repo files, DB rows, env files, browser sessions, API calls, or ads settings were modified.
