# Agent 3 — Autonomous_business Stock Cash PO Guard

Before executing, read:
1. `~/AGENTS.md`
2. `~/Docs/Autonomous_business/AGENTS.md`
3. `~/Docs/Autonomous_business/docs/current/LINE31_LAUNCH_CURRENT_STATUS.md` if present
4. `~/Docs/Autonomous_business/docs/current/LINE31_LAUNCH_CURRENT_STATUS.json` if present
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-06_line31_48h_partial_scale_preflight/PLAN.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_48H_PARTIAL_SCALE_PREFLIGHT_20260606_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
7. This starter prompt.

## Assignment

Refresh the LINE31 stock/cash/PO guard for a 48h controlled LINE31 countrywide Meta scale to about `25,000 KZT/day`.

Workdir:
- `~/Docs/Autonomous_business`

## Required Truth Rules

- Do not use Kaspi pricelist `PP*` stock as inventory truth.
- Use current LINE31 readiness/product-truth packet and LINE31 apply-ready stock split as source-backed stock context.
- Keep cash/PO freshness separate from stock truth.
- If cash source is stale or not owner-confirmed current, mark cash gate `YELLOW`, not `GREEN`.

## Allowed

- Read-only/local-only stock/cash/PO inspection.
- Local evidence under `exports/validation/line31_48h_partial_scale_preflight_20260606/agent3_ab_stock_cash_guard/`.
- Closeout writing.

## Forbidden

No production DB writes, workbook writes, scheduler/source-pointer changes, Kaspi/WebUI/API writes, Meta writes, website deploys, stock changes, price changes, cash movement, supplier payment, PO commitment, owner publication, or external writes.

## Commands To Prefer

Run read-only:

```bash
python3 scripts/audit_line31_active_goal_completion.py --json --allow-incomplete
python3 scripts/report_line31_next_inputs_status.py --json
python3 scripts/report_line31_next_launch_action.py --json
```

Inspect:
- `~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_current_synthesis_20260601_132153/CURRENT_LINE31_READINESS_FACTS.json`
- `~/Docs/Autonomous_business/exports/validation/product_truth_yellow_to_apply_ready_20260529_123827/line31_apply_ready_stock_split.csv`
- Latest relevant cash balance/cockpit evidence already recorded in repo/Oracle pack.

## Gate

`GREEN` only if LINE31 sellable stock and primary route stock remain safe, and cash/PO has current owner/source confirmation with no adverse blocker.

`YELLOW` if stock is safe but cash/PO freshness is stale or needs owner confirmation.

`RED` if LINE31 sellable stock/route stock is unsafe for a 48h 25k test, cash/PO evidence indicates risk, or any write attempt occurs.

## Closeout

Write:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_48h_partial_scale_preflight/agent3_ab_stock_cash_guard_closeout.md`

Include:
- `Gate: <GREEN/YELLOW/RED>`
- Commands run.
- Evidence paths.
- LINE31 total/sellable/available stock summary.
- Starry Black and early-order route stock observations if available.
- Cash/PO freshness classification.
- Explicit no-write attestation.
