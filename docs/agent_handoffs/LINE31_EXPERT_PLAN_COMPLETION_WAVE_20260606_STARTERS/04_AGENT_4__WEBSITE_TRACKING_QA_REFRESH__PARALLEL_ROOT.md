# Agent 4 - Website Tracking And Route QA Refresh

Before executing, read:
1. `~/AGENTS.md`
2. `~/Docs/acmewear_web_v2/AGENTS.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-06_line31_expert_plan_completion_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_EXPERT_PLAN_COMPLETION_WAVE_20260606_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/acmewear_web_v2/docs/90_REPORTS/line31_black_card_image_incident_route_hotfix_20260606_152352/POSTDEPLOY_LIVE_CLOSEOUT.md`
6. This assigned starter prompt.

Workdir:

`~/Docs/acmewear_web_v2`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_expert_plan_completion_wave/agent4_website_tracking_qa_refresh_closeout.md`

Assigned evidence root:

`~/Docs/acmewear_web_v2/docs/90_REPORTS/line31_expert_plan_completion_tracking_qa_20260606`

## Task

Refresh live website/redirect/tracking QA after the LINE31 black-card incident hotfix. Keep website event truth and redirect truth separate from Meta and Kaspi truth.

Verify:

- `https://acmewear.pro/line31` live route.
- Primary/default/final/sticky CTA routes to `/go/ivory-white-starry-black`.
- Starry black is demoted/overridden during incident handling.
- Redirect QA works for `/go/:color`.
- `/api/signal` synthetic live QA works if repo contract permits it.
- Log-backed/latest website tracking evidence is current.
- Cloudflare Analytics Engine SQL 403, if still present, is explicitly classified as retained blocker rather than hidden.

Prefer:

```bash
node scripts/probe_line31_tracking_qa.mjs --base-url https://acmewear.pro --allow-live-signal-writes --evidence-dir docs/90_REPORTS/line31_expert_plan_completion_tracking_qa_20260606/live_tracking_qa
```

Run `scripts/lint_docs.sh` only if you add or edit markdown in this repo.

## Forbidden

No website deploy, no Meta writes, no Kaspi/WebUI/API writes, no campaign changes, no price/stock/cash/PO/supplier actions, no DB/workbook writes, no scheduler/source-pointer changes, and no owner publication.

## Gate

`GREEN` if live route/redirect/tracking QA passes and the current hotfix routing is verified.

`YELLOW` if route QA passes but Cloudflare SQL or durable analytics remains soft-pass/log-backed only.

`RED` if live route is broken, CTA routes black incorrectly during incident, tracking fails entirely, or a forbidden write occurs.

## Closeout Requirements

Include `Gate: <GREEN/YELLOW/RED>`, commands, evidence paths, live route assertions, tracking/redirect truth summary, retained Cloudflare blocker if any, and no-write/deploy attestation.
