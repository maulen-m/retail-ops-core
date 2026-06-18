# Agent 10 - Ads Retained Spend And Offer Coverage Route

Parallel group: `phase3_root`
Assigned gate: read-only/copied-temp only
Closeout path: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase3_retained_blocker_deepening/agent10_ads_retained_spend_closeout.md`
Evidence root: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase3_retained_blocker_deepening/agent10_evidence/`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE3_RETAINED_BLOCKER_DEEPENING_20260522_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE3_RETAINED_BLOCKER_DEEPENING_20260522_STARTERS/10_AGENT_10__ADS_RETAINED_SPEND__PARALLEL_ROOT.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-21_mvos_phase2_owner_confirmed_blocker_closure/PHASE2_ORCHESTRATOR_REVIEW.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase2_owner_confirmed_blocker_closure/agent7_serialized_copied_temp_integrator_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase2_owner_confirmed_blocker_closure/agent7_evidence/RETAINED_BLOCKER_BOARD.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9173_ads_packet_v1_adapter_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent881_storeb_ads_mapping_source_decision_closeout.md`

## Mission

Deepen retained blockers `R010` and `R011` without zeroing spend:

- STOREB has `10` retained positive-spend rows totaling `3837.32 KZT`;
- STOREB current mapping authority is `0` SKU-level rows;
- ACMEWEAR has one missing sold offer `CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK`;
- ads spend reality and offer-universe coverage still fail.

Use local evidence and repo data only. Do not perform live ad-platform, Kaspi, WebUI, or API writes/fetches.

## Required Work

1. Create the evidence root.
2. Capture start boundary:
   - protected-surface `git status --short`;
   - SHA for `db/app.db` and Agent 7 copied DB if read;
   - `./scripts/check_no_db_tracked.sh`.
3. Read Agent 7 ads outputs:
   - `commands/88_validate_ads_sidecar_readiness.stdout.txt`
   - `commands/89_validate_ads_spend_reality.stdout.txt`
   - `commands/90_validate_ads_offer_universe_coverage.stdout.txt`
   - `ads_materializer_apply_with_gate/storeb_product_code_mapping.csv`
   - `ads_materializer_apply_with_gate/ads_campaign_product_daily_unmapped.csv`
   - `validator_outputs/ads_offer_universe_coverage/ads_missing_sold_offers.csv`
4. Read prior Agent 9173 and Agent 881 closeouts enough to avoid repeating solved work.
5. Determine whether any retained STOREB spend rows can be mapped from local exact source evidence. If not, keep them retained.
6. Determine why ACMEWEAR `CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK` is missing from ads offer coverage:
   - missing ads packet row;
   - missing sales/offers bridge;
   - sidecar scope issue;
   - real zero-spend/no-campaign case;
   - unresolved local evidence.
7. Produce a compact CSV/TSV evidence table under your evidence root listing each retained ads row/offer and proposed next route.

## Forbidden

- No ad-platform writes.
- No ad spend, bid, campaign, budget, or status changes.
- No production DB writes.
- No source-pointer writes.
- No Web_automation writes.
- No live external fetch unless a later explicit owner approval grants it.
- No zeroing unmapped spend.

## Closeout Requirements

Write the closeout at the assigned path. Include:

- standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact STOREB retained spend classification;
- exact ACMEWEAR missing-offer classification;
- evidence paths;
- whether more local-only work can close the blocker;
- whether live read-only source refresh or human clarification would be required later;
- protected-surface boundary result.
