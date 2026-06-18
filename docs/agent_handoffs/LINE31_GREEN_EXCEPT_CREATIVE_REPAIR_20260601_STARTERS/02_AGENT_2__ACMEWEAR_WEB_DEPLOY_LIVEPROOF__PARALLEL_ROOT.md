# Agent 2 Starter - acmewear_web_v2 Isolated Deploy And Live Proof

You are Agent 2. Your lane makes LINE31 tracking live-proof green if it can be done safely.

## Bootstrap Context

Before executing, read:

1. `~/Docs/acmewear_web_v2/AGENTS.md`
2. `~/Docs/acmewear_web_v2/workspace/landing_build/package.json`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-01_line31_green_except_creative_repair/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_20260601_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_20260601_STARTERS/02_AGENT_2__ACMEWEAR_WEB_DEPLOY_LIVEPROOF__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent2_acmewear_web_tracking_qa_closeout.md`

## Scope

Allowed:

- isolate reviewed LINE31 tracking changes in `acmewear_web_v2`;
- run full local website validation;
- deploy to `acmewear.pro` only if the deploy candidate is proven to contain only reviewed LINE31 tracking changes and required existing runtime assets;
- run fresh live proof after deploy.

Forbidden:

- deploy unrelated dirty worktree changes;
- Meta publish;
- Kaspi/WebUI/API/CRM mutation;
- price/stock/cash/PO/supplier changes;
- internal Kaspi isolation.

## Task

Make tracking gate green:

- inspect current dirty worktree and identify the exact Agent 2 LINE31 tracking patch;
- create an isolated deploy candidate or prove the current build is safe;
- run repo validations;
- if safe, deploy only the reviewed LINE31 tracking changes;
- live-prove on `https://acmewear.pro`:
  - `PageView`
  - `ViewContent`
  - `ColorSelect`
  - `QualifiedVisit`
  - `KaspiClick`
  - `HighIntentKaspiClick`
  - `/go/:color` server `KaspiRedirect`
  - UTM preservation including `utm_id` and `utm_placement`
  - no fake ecommerce events.

If isolation cannot be proven, do not deploy. Close `YELLOW` with exact diff blockers.

## Required Outputs

Evidence folder:

`~/Docs/acmewear_web_v2/docs/90_REPORTS/line31_green_except_creative_repair_20260601/`

Required files:

- `deploy_candidate_diff_audit.md`
- `deploy_or_no_deploy_decision.md`
- `live_tracking_proof.json`
- `live_tracking_proof.md`
- `COMMANDS_RUN.tsv`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair/agent2_acmewear_web_deploy_liveproof_closeout.md`

Closeout must include standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

Use `GREEN` only if the tracking change is live-deployed and live-proof passed, or if live already matches the reviewed build and proof passed. Use `YELLOW` if deploy isolation cannot be proven. Use `RED` for unsafe deploy or fake ecommerce.
