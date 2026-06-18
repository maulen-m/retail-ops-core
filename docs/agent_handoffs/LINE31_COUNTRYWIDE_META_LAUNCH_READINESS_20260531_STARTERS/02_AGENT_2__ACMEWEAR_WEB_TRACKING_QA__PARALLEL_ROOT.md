# Agent 2 Starter - acmewear_web_v2 LINE31 Tracking QA

You are Agent 2. Your lane verifies and, if needed, locally patches tracking QA for LINE31 countrywide traffic. No website deploy is authorized.

## Bootstrap Context

Before executing, read:

1. `~/Docs/acmewear_web_v2/AGENTS.md`
2. `~/Docs/acmewear_web_v2/workspace/landing_build/package.json`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-31_line31_countrywide_meta_launch_readiness/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/02_AGENT_2__ACMEWEAR_WEB_TRACKING_QA__PARALLEL_ROOT.md`

## Source Inputs

Read:

1. `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531/LANDING_TRACKING_SPEC.csv`
2. `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531/ATTRIBUTION_AND_ISOLATION_POLICY.md`
3. `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531/LAUNCH_GATES_AND_MONITORING_RULES.md`
4. `~/Docs/acmewear_web_v2/workspace/landing_build/docs/10_CONTRACTS/WEB_SIGNAL_CONTRACT.md` if present
5. `~/Docs/acmewear_web_v2/workspace/landing_build/docs/20_REGISTRY/LIVE_OFFER_MAP.json` if present

## Scope

Allowed writes:

- repo-local docs/scripts/tests/source changes in `~/Docs/acmewear_web_v2` only when they prepare local tracking QA and do not deploy;
- generated evidence under `~/Docs/acmewear_web_v2/docs/90_REPORTS/line31_countrywide_meta_launch_readiness_20260531/`;
- assigned closeout under the shared handoff folder.

Forbidden:

- Cloudflare/Wrangler deploy;
- production route/source-pointer changes outside local repo files;
- fake ecommerce events: `Purchase`, `AddToCart`, `InitiateCheckout`, `AddPaymentInfo`;
- bypassing `/go/:color`;
- Meta/Kaspi/WebUI/API/CRM/campaign/price/stock/cash/PO writes.

## Task

Verify the landing and redirect tracking path:

- `Meta/IG -> acmewear.pro -> /go/:color -> Kaspi`;
- `PageView`, `ViewContent`, `ColorSelect`, `QualifiedVisit`, `KaspiClick`, `HighIntentKaspiClick`, and server-side `KaspiRedirect`;
- selected-color truth and destination-route truth, including fallback routes;
- UTM preservation and safe payload behavior;
- `/api/signal` fail-closed behavior for disallowed host/origin cases;
- no raw PII or raw click IDs in owner-facing outputs.

If an existing smoke test already covers a point, cite it and run it. If a small local test or probe is missing, add it under the repo's test/script conventions without deploying.

## Required Outputs

Write these under your local evidence folder:

- `line31_tracking_qa_report.md`
- `line31_route_probe_results.json`
- `line31_event_schema_gap_table.csv`
- `line31_no_fake_ecommerce_assertions.md`
- `COMMANDS_RUN.tsv`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent2_acmewear_web_tracking_qa_closeout.md`

The closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact files created/changed;
- validation commands run;
- explicit confirmation that no deploy or external write was performed.

Use `GREEN` only if all required tracking probes/tests pass locally. Use `YELLOW` if tracking is mostly ready but a deploy/fresh-live proof/creative input remains. Use `RED` for fake ecommerce, route bypass, deploy attempt, or unsafe signal behavior.
