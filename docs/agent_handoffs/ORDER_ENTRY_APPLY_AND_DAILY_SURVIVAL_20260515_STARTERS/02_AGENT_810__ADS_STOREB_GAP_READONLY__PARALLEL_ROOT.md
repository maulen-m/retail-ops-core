# Agent810 - Ads/STOREB Gap Read-Only Analyst

Gate target: `GREEN` if you produce a read-only ads/STOREB status packet that separates spend coverage, source freshness, STOREB business identity, and owner-publication readiness without mutating anything.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_order_entry_apply_and_daily_survival_parallel/PLAN.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/DAILY_SURVIVAL_BRIEF_V1_20260511_141731.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_codecaptain-storeb-readiness-packet-patch/agent802_storeb_evidence_boundary_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_codecaptain-storeb-readiness-packet-patch/agent803_preflight_command_boundary_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_codecaptain-storeb-readiness-packet-patch/agent801_packet_patch_execution_closeout.md`
8. `~/Docs/Oracle/Web_automation/2026-05-14/112524_LINE61_LINE51_parent_performance_reeval_FLAT20/Answer/15.05.2026_08_51_00_Code Captain_Pt-2.md`
9. this starter prompt

Sibling agents 809 and 811 are parallel. Do not wait for them.

## Assignment

Build the ads/STOREB part of the next Daily Survival / MVOS blocker packet.

Write evidence only under:

`~/Docs/Autonomous_business/exports/validation/order_entry_apply_and_daily_survival_parallel/20260515_085748/agent810_ads_storeb_gap/`

Required output:

`~/Docs/Autonomous_business/exports/validation/order_entry_apply_and_daily_survival_parallel/20260515_085748/agent810_ads_storeb_gap/ADS_STOREB_GAP_STATUS.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_order_entry_apply_and_daily_survival_parallel/agent810_ads_storeb_gap_closeout.md`

## Required Content

- Current ads/source-freshness gate status from existing local evidence.
- Which parts are already proven versus which remain source-gapped.
- Explicit separation of STOREB business-store identity from Universal access/login identity.
- Whether current evidence supports owner publication, profit-after-ads, or only review-only internal use.
- Minimum next safe action to move ads/source freshness toward green after the DB-only order-entry repair.

## Boundaries

Read-only only. Do not refresh live ads, mutate Web_automation, mutate production DB, mutate source pointers, upload anything, change ads/bids/budgets/prices/stock, write external systems, or publish owner-facing content.

Do not run scheduler controls or `manage_business_automation.py verify`.

Gate: GREEN
