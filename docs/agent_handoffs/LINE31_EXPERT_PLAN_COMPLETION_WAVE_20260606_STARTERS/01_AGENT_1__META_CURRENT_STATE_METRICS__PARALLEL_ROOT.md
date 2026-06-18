# Agent 1 - Meta Current State And Metrics

Before executing, read:
1. `~/AGENTS.md`
2. `~/Docs/Business_3/Facebook_ads/AGENTS.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-06_line31_expert_plan_completion_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_EXPERT_PLAN_COMPLETION_WAVE_20260606_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. This assigned starter prompt.

Workdir:

`~/Docs/Business_3/Facebook_ads`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_expert_plan_completion_wave/agent1_meta_current_state_metrics_closeout.md`

Assigned evidence root:

`~/Docs/Business_3/Facebook_ads/exports/validation/line31_expert_plan_completion_20260606/agent1_meta_current_state_metrics`

## Task

Refresh current LINE31 Meta state and per-ad metrics after the owner manual budget change to `5500` Meta minor units.

Verify:

- campaign `120245481137650641`
- ad set `120245481997290641`
- ads `120245492808400641`, `120245488532270641`, `120245492808390641`
- status of campaign/adset/ads
- daily budget readback, expected current owner-confirmed value `5500`
- landing URL `https://acmewear.pro/line31`
- CTA `ORDER_NOW`
- current per-ad metrics available from Meta API
- whether the current $55 budget already means the expert's 25k-ish controlled scale is active

Prefer repo-native commands:

```bash
python3 scripts/snapshot_line31_current_meta_state.py --expected-status ACTIVE --output-root exports/validation/line31_expert_plan_completion_20260606/agent1_meta_current_state_metrics --run-id current_state --json
python3 scripts/preflight_meta_api_primary.py --live-readonly --campaign-limit 20 --output-root exports/validation/line31_expert_plan_completion_20260606/agent1_meta_current_state_metrics --action-summary "LINE31 expert-plan completion current read-only Meta API proof" --json
```

If additional read-only insights scripts exist, use them, but keep LINE31 campaign ids explicit and avoid generic campaign rows unless ids match.

## Forbidden

No Meta writes, no campaign/adset/ad/budget/status/targeting changes, no website deploys, no Kaspi/WebUI/API writes, no DB/workbook writes, no cash/PO/stock/price/supplier actions.

## Gate

`GREEN` if all expected LINE31 objects are present, active, current budget is source-backed, exactly three target ads exist, and no unexpected drift is found.

`YELLOW` if metrics are partial, rate-limited, or settings need owner/orchestrator review but no drift occurred.

`RED` if object count/status/budget/URL/CTA drift is dangerous or any forbidden write occurs.

## Closeout Requirements

Include `Gate: <GREEN/YELLOW/RED>`, commands, evidence paths, current settings, current metrics summary, explicit old-vs-current budget note, and no-write attestation.
