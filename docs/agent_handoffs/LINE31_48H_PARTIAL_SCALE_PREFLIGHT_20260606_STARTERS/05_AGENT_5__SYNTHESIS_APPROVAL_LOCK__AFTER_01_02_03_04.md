# Agent 5 — Synthesis Approval Lock After Agents 1-4

Before executing, read:
1. `~/AGENTS.md`
2. `~/Docs/Autonomous_business/AGENTS.md`
3. `~/Docs/Business_3/Facebook_ads/AGENTS.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-06_line31_48h_partial_scale_preflight/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_48H_PARTIAL_SCALE_PREFLIGHT_20260606_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. These dependency closeouts:
   - `~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_48h_partial_scale_preflight/agent1_meta_state_metrics_closeout.md`
   - `~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_48h_partial_scale_preflight/agent2_line31_order_truth_closeout.md`
   - `~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_48h_partial_scale_preflight/agent3_ab_stock_cash_guard_closeout.md`
   - `~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_48h_partial_scale_preflight/agent4_website_api_factory_closeout.md`
7. This starter prompt.

## Assignment

Synthesize Agents 1-4 into a decision-grade preflight packet and produce the exact owner approval phrase if, and only if, evidence supports preparing a 25k controlled scale.

Workdirs:
- Primary: `~/Docs/Autonomous_business`
- Read-only companion: `~/Docs/Business_3/Facebook_ads`

## Allowed

- Read dependency closeouts and evidence.
- Create local synthesis evidence under `~/Docs/Autonomous_business/exports/validation/line31_48h_partial_scale_preflight_20260606/agent5_synthesis_approval_lock/`.
- Write final closeout.

## Forbidden

No Meta writes, budget changes, ad creation, campaign/adset/ad state changes, website deploys, Kaspi/WebUI/API writes, production DB/workbook writes, scheduler/source-pointer changes, stock/price/cash/PO/supplier actions, owner publication, or internal Kaspi campaign changes.

## Required Synthesis

Create:
- Gate table for Meta, orders, stock, cash/PO, website, API factory.
- SHA256 evidence lock over the key closeouts and any generated preflight summary.
- Exact proposed approval phrase if appropriate.
- Rollback plan:
  - restore ad set `120245481997290641` to `daily_budget=3093`, or
  - pause exact LINE31 campaign/adset/ads if owner chooses hard stop after failure.

Use `daily_budget=5155` as the proposed 25k target, based on `25,000 KZT / 485 KZT/USD * 100`.

## Gate

`GREEN_25K_APPROVAL_READY` only if all required gates are green and the exact approval phrase is ready.

`YELLOW_25K_APPROVAL_READY_WITH_TRACKING_OR_CASH_CAVEAT` if Meta/order/stock support 25k but website or cash freshness remains caveated.

`YELLOW_HOLD_15K_RECOMMENDED` if evidence is insufficient but no immediate stop is required.

`RED_STOP_OR_REVERT_REQUIRED` if current LINE31 campaign/landing/order/stock/cash evidence indicates unsafe continuation.

## Closeout

Write:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_48h_partial_scale_preflight/agent5_synthesis_approval_lock_closeout.md`

Include:
- `Gate: <GREEN/YELLOW/RED>`
- Full gate classification.
- Evidence lock path and SHA256.
- Approval phrase if allowed, otherwise say exactly why not.
- Explicit no-write attestation.
