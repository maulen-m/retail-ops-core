# Agent 1 — Meta State And Metrics Preflight

Before executing, read:
1. `~/AGENTS.md`
2. `~/Docs/Business_3/Facebook_ads/AGENTS.md`
3. `~/Docs/Business_3/Facebook_ads/docs/00_CORE/00_START_HERE.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-06_line31_48h_partial_scale_preflight/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_48H_PARTIAL_SCALE_PREFLIGHT_20260606_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. This starter prompt.

## Assignment

Run read-only Meta state and metrics checks for LINE31 countrywide campaign.

Workdir:
- `~/Docs/Business_3/Facebook_ads`

Expected LINE31 objects:
- Campaign: `120245481137650641`
- Ad set: `120245481997290641`
- Ads: `120245488532270641`, `120245492808390641`, `120245492808400641`
- Current budget before proposed change: `3093`
- Expected status: `ACTIVE`

## Allowed

- Read-only Meta API checks.
- Local evidence under `exports/validation/line31_48h_partial_scale_preflight_20260606/agent1_meta_state_metrics/`.
- Closeout writing.

## Forbidden

No Meta writes, budget changes, campaign/adset/ad state changes, creative changes, targeting changes, website deploys, Kaspi/WebUI/API mutations, DB/workbook writes, stock/price/cash/PO/supplier actions, scheduler/source-pointer changes, internal Kaspi campaign changes, or owner publication.

## Commands To Prefer

Run:

```bash
python3 scripts/snapshot_line31_current_meta_state.py --expected-status ACTIVE --json --output-root exports/validation/line31_48h_partial_scale_preflight_20260606/agent1_meta_state_metrics
python3 scripts/preflight_meta_api_primary.py --live-readonly --campaign-limit 20 --json --output-root exports/validation/line31_48h_partial_scale_preflight_20260606/agent1_meta_state_metrics
```

If available, refresh current LINE31 ad-level insights for `2026-06-04..2026-06-06` using repo-native scripts only. Do not invent a custom Meta write path.

## Gate

`GREEN` only if exact LINE31 objects are active, budget is still `3093`, landing/copy/CTA/placement guards remain consistent with prior launch state, and read-only Meta API is usable.

`YELLOW` if read-only data is incomplete/rate-limited but no drift is proven.

`RED` if any unapproved Meta object drift, status drift, budget drift, wrong URL/copy/CTA, or write attempt is observed.

## Closeout

Write:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_48h_partial_scale_preflight/agent1_meta_state_metrics_closeout.md`

Include:
- `Gate: <GREEN/YELLOW/RED>`
- Commands run.
- Evidence paths.
- Exact current budget/status/readback summary.
- Whether Agent 5 may use your evidence for the 25k approval lock.
- Explicit no-write attestation.
