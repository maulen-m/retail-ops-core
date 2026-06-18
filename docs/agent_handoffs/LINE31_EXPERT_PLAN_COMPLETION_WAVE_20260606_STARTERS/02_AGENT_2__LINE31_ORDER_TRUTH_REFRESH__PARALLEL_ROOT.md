# Agent 2 - LINE31 Order Truth Refresh

Before executing, read:
1. `~/AGENTS.md`
2. `~/Docs/Business_3/Facebook_ads/AGENTS.md`
3. `~/Docs/Autonomous_business/AGENTS.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-06_line31_expert_plan_completion_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_EXPERT_PLAN_COMPLETION_WAVE_20260606_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. This assigned starter prompt.

Workdir:

`~/Docs/Business_3/Facebook_ads`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_expert_plan_completion_wave/agent2_line31_order_truth_refresh_closeout.md`

Assigned evidence root:

`~/Docs/Business_3/Facebook_ads/exports/validation/line31_expert_plan_completion_20260606/agent2_line31_order_truth_refresh`

## Task

Refresh ACMEWEAR LINE31 live order truth for the launch window through the current time on 2026-06-06. Keep this as Kaspi/order truth, not deterministic Meta attribution.

Verify:

- LINE31 orders by date from 2026-06-04 through 2026-06-06.
- Status/cancellation/return abnormalities.
- Whether the owner/user-confirmed five real Meta-driven marketplace orders remain compatible with source-backed order rows.
- Whether the earlier seven contextual/isolated-window LINE31 rows remain valid context.
- Color/size summary without leaking PII.

Prefer repo-native command if still valid:

```bash
python3 scripts/sync_live_orders_acmewear.py --start-date 2026-06-04 --end-date 2026-06-06
```

Use local outputs under `exports/10_DERIVED/orders_live/` and write any summaries under your assigned evidence root. If the current date has moved by runtime, include 2026-06-06 as the as-of date and state timestamp.

## Forbidden

No Kaspi/WebUI/API writes, CRM writes, Meta writes, website deploys, DB/workbook writes, scheduler/source-pointer changes, price/stock/cash/PO/supplier actions, owner publication, or internal Kaspi campaign changes.

## Gate

`GREEN` if LINE31 order rows refresh cleanly and show no abnormal cancellation/return issue.

`YELLOW` if order truth is source-backed but attribution remains contextual or some status freshness is incomplete.

`RED` if LINE31 rows disappear unexpectedly, mapping breaks, cancellation/return spike appears, or a forbidden write occurs.

## Closeout Requirements

Include `Gate: <GREEN/YELLOW/RED>`, commands, evidence paths, date-by-date LINE31 order/status counts, sanitized color/size summary, contextual-attribution caveat, and no-write attestation.
