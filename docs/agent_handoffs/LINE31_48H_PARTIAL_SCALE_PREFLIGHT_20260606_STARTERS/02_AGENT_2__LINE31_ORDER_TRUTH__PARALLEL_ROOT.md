# Agent 2 — LINE31 Order Truth Refresh

Before executing, read:
1. `~/AGENTS.md`
2. `~/Docs/Business_3/Facebook_ads/AGENTS.md`
3. `~/Docs/Business_3/Facebook_ads/docs/00_CORE/00_START_HERE.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-06_line31_48h_partial_scale_preflight/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_48H_PARTIAL_SCALE_PREFLIGHT_20260606_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. This starter prompt.

## Assignment

Refresh ACMEWEAR LINE31 live order truth for the LINE31 countrywide launch window and classify whether the `7` owner-confirmed contextual Meta IG order signal remains valid for a 25k approval path.

Workdir:
- `~/Docs/Business_3/Facebook_ads`

## Allowed

- Read-only Kaspi live-order API sync for ACMEWEAR.
- Local evidence under `exports/validation/line31_48h_partial_scale_preflight_20260606/agent2_line31_order_truth/`.
- Closeout writing.

## Forbidden

No Kaspi/WebUI/API writes, CRM writes, Meta writes, website deploys, DB/workbook writes, scheduler/source-pointer changes, price/stock/cash/PO/supplier actions, owner publication, or internal Kaspi campaign changes.

## Commands To Prefer

Run:

```bash
python3 scripts/sync_live_orders_acmewear.py --start-date 2026-06-04 --end-date 2026-06-06
```

Then inspect the generated LINE31 mapped rows under `exports/10_DERIVED/orders_live/2026-06-04`, `2026-06-05`, and `2026-06-06`.

If validation helpers are available, run the focused live-order validation. Keep PII out of closeout.

## Gate

`GREEN` only if LINE31 order rows still support at least the known `7` contextual isolated-window rows or show continuing signal, with no abnormal cancellations/returns.

`YELLOW` if rows are present but attribution remains contextual or source freshness is incomplete.

`RED` if orders disappear, mapping breaks, cancellation/return spike appears, or a write attempt occurs.

## Closeout

Write:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_48h_partial_scale_preflight/agent2_line31_order_truth_closeout.md`

Include:
- `Gate: <GREEN/YELLOW/RED>`
- Commands run.
- Evidence paths.
- LINE31 order counts by date and stage.
- Sanitized color/size summary.
- Explicit statement that attribution is contextual, not deterministic Meta purchase attribution.
- Explicit no-write attestation.
