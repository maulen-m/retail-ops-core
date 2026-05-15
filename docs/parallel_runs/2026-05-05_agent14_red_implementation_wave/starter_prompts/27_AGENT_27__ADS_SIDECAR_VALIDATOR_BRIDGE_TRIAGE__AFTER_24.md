# Agent 27 - Ads Sidecar Validator Bridge Triage

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_27_ads_sidecar_validator_bridge_triage_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_24.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_24_combined_temp_proof_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_23_ads_mapping_enrichment_temp_proof_closeout.md`
7. this starter prompt

## Mission

Read-only code/validator triage for the ads sidecar bridge problem.

Agent 24 proved `ads_campaign_product_daily` materialization is useful, but strict offer-universe and spend-reality validators still fail because they read older `ads_spend_sidecar_daily_sku` surfaces. Determine the smallest safe bridge so validators and financial publication consume one canonical ads truth without recomputing business math in dashboards.

## Write Boundary

Allowed writes:

- assigned closeout;
- evidence files under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_27_evidence/`.

Forbidden:

- production DB writes;
- code changes;
- external-system writes;
- ad-platform writes.

## Required Work

1. Inspect ads-related validators and materializers.
2. Identify which tables each validator reads:
   - `ads_campaign_product_daily`;
   - `ads_source_refresh_runs`;
   - `ads_spend_sidecar_daily`;
   - `ads_spend_sidecar_daily_sku`;
   - any legacy sidecar table.
3. Determine whether the right fix is:
   - change validators to read `ads_campaign_product_daily`;
   - materialize a bridge into `ads_spend_sidecar_daily_sku`;
   - create a canonical view;
   - keep both with explicit source hierarchy.
4. Define tests that must be written before any implementation.
5. Draft exact next implementation prompt if safe.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact commands run;
- code surfaces inspected;
- recommended bridge architecture;
- tests required;
- exact next implementation prompt if safe.
