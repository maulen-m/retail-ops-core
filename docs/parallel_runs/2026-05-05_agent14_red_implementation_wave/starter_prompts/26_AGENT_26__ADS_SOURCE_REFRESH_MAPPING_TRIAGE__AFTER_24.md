# Agent 26 - Ads Source Refresh And Mapping Triage

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_26_ads_source_refresh_mapping_triage_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_24.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_24_combined_temp_proof_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_24_evidence/residual_ads_blocker_detail.csv`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_24_evidence/storeb_product_code_mapping_summary.csv`
8. `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/WA2_STOREB_CLOSEOUT.md`
9. this starter prompt

## Mission

Read-only ads truth triage after Agent 24.

Focus blockers:

- `ADS_REFRESH_MISSING=166`;
- `ADS_COVERAGE_MISSING=395`;
- stale `src_web_automation_kaspi_marketing_directapi`;
- stale ACMEWEAR Meta/Facebook source policy.

Produce exact Web_automation read-only data-gathering prompts and exact mapping/enrichment requirements. Do not run live browser/API calls yourself from this lane.

## Write Boundary

Allowed writes:

- assigned closeout;
- evidence and starter prompt drafts under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_26_evidence/`.

Forbidden:

- production DB writes;
- code changes;
- Web_automation repo writes;
- live Kaspi Marketing calls;
- Meta/Facebook calls;
- ad-platform writes.

## Required Work

1. Summarize residual ads blockers by store, date span, SKU, and reason.
2. Define the exact ACMEWEAR read-only evidence request:
   - daily product evidence for remaining historical gaps;
   - refresh evidence for `2026-04-16..2026-05-04`;
   - LINE51/LINE61 daily-evidence requirements;
   - whether Meta/Facebook evidence is required for the same dates.
3. Define the exact STOREB read-only evidence request:
   - product report refresh for `2026-04-16..2026-05-04`;
   - product-code mapping evidence for the five blocked codes;
   - no fuzzy-name mapping.
4. Produce standalone Web_automation starter prompts if live data gathering is the next safe step.
5. State whether owner approval is required before those read-only runs.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact commands run;
- evidence files written;
- residual ads blocker table;
- exact Web_automation prompts and target output folders;
- what remains blocked even after read-only data gathering.
