# Agent 4 — Website Traceability And API Factory No-Write Readiness

Before executing, read:
1. `~/AGENTS.md`
2. `~/Docs/Business_3/Facebook_ads/AGENTS.md`
3. `~/Docs/Business_3/Facebook_ads/docs/00_CORE/00_START_HERE.md`
4. `~/Docs/Business_3/Facebook_ads/docs/10_CONTRACTS/WEBSITE_SOURCE_PRIORITY_CONTRACT.md` if present
5. `~/Docs/Business_3/Facebook_ads/docs/10_CONTRACTS/META_API_PRIMARY_AND_WRITE_GATE_CONTRACT.md` if present
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-06_line31_48h_partial_scale_preflight/PLAN.md`
7. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_48H_PARTIAL_SCALE_PREFLIGHT_20260606_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
8. This starter prompt.

## Assignment

Classify website traceability and Meta API factory readiness for the expert-proposed next stage.

Workdir:
- `~/Docs/Business_3/Facebook_ads`

## Allowed

- Read-only Cloudflare/website event sync attempts.
- Read-only/log-backed capture evidence.
- Meta API primary read-only preflight and non-mutating smoke/preflight checks only.
- Local evidence under `exports/validation/line31_48h_partial_scale_preflight_20260606/agent4_website_api_factory/`.
- Closeout writing.

## Forbidden

No website deploy, no Meta write, no adcreative/campaign/adset/ad creation, no budget/status/targeting changes, no Kaspi/WebUI/API mutations, no DB/workbook writes, no scheduler/source-pointer changes, no stock/price/cash/PO/supplier actions, no owner publication.

## Commands To Prefer

Run:

```bash
python3 scripts/sync_website_events_cloudflare.py --start-date 2026-06-04 --end-date 2026-06-06
python3 scripts/capture_website_signal_logs.py --duration-seconds 300 --output-day 2026-06-06
python3 scripts/preflight_meta_api_primary.py --live-readonly --campaign-limit 20 --json --output-root exports/validation/line31_48h_partial_scale_preflight_20260606/agent4_website_api_factory
python3 scripts/preflight_meta_app_mode_adcreative_smoke.py --help
```

Do not run an adcreative smoke write. Help/preflight inspection only unless the command has an explicit no-write/dry-run mode.

## Gate

`GREEN` only if website has durable `live_cloudflare` or stable nonzero `live_logbacked` rows and API factory no-write/readiness checks are clean.

`YELLOW` if website remains incomplete but route/QA is not broken, or API factory remains write-gated/not proven.

`RED` if website route/redirect is broken, source is fixture/stale/pending only, Cloudflare/log capture proves unusable for live truth, API auth is broken, or any write attempt occurs.

## Closeout

Write:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_48h_partial_scale_preflight/agent4_website_api_factory_closeout.md`

Include:
- `Gate: <GREEN/YELLOW/RED>`
- Commands run.
- Evidence paths.
- Website source classification.
- API factory readiness classification.
- Whether website/API gates block `25k`, `30k+`, or new creative cell.
- Explicit no-write attestation.
