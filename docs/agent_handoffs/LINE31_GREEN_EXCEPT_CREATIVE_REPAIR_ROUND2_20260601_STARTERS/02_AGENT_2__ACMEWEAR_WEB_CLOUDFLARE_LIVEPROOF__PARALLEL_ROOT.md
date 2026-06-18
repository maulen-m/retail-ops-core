# Agent 2 Starter - acmewear_web_v2 Cloudflare Deploy And Live Proof

You are Agent 2. Your lane clears the acmewear.pro production website tracking blocker for LINE31 launch-readiness.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-01_line31_green_except_creative_repair_round2/PLAN.md`
3. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_ROUND2_20260601_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_ROUND2_20260601_STARTERS/02_AGENT_2__ACMEWEAR_WEB_CLOUDFLARE_LIVEPROOF__PARALLEL_ROOT.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair/agent2_acmewear_web_deploy_liveproof_closeout.md`
6. `~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_repair_20260601/final_synthesis/FINAL_GREEN_EXCEPT_CREATIVE_MATRIX.md`
7. `~/Docs/acmewear_web_v2/AGENTS.md` if present
8. `~/Docs/acmewear_web_v2/docs/90_REPORTS/line31_green_except_creative_repair_20260601/deploy_or_no_deploy_decision.md`
9. `~/Docs/acmewear_web_v2/docs/90_REPORTS/line31_green_except_creative_repair_20260601/live_tracking_proof.md`

## Objective

Deploy the already-validated narrow LINE31 tracking patch to acmewear.pro and prove production live tracking is green.

## Current Known Blocker

Prior Agent 2 local validations and Wrangler dry-runs passed, but production deploy and version upload failed before upload with Cloudflare auth error `10000`.

Fresh live proof then remained yellow because acmewear.pro still missed `utm_placement` and `utm_id` in:

- root runtime config;
- `/go/:color` redirects;
- fallback `/go/ivory-white-starry-black` route.

## Authorized Surface

You may:

- refresh or replace local non-interactive Wrangler/Cloudflare auth context if available to this machine;
- use browser/Chrome auth flow if required for Wrangler login, without leaking secrets;
- deploy only the already-reviewed LINE31 tracking patch to acmewear.pro;
- rerun local and production live-proof validation;
- write local evidence and closeout files.

You may not:

- publish Meta campaigns;
- create or change Meta custom conversions;
- mutate Kaspi/WebUI/API/CRM;
- change prices, stock offers, internal LINE31 Kaspi campaigns, seller-bonus, cash, PO, supplier/payment state, or Autonomous_business production DB/workbook;
- broaden the website change beyond the LINE31 tracking/UTM preservation patch already validated in the prior lane.

## Required Work

1. Inspect the prior evidence and current `acmewear_web_v2` worktree. Do not revert unrelated user/agent changes.
2. Rerun the already-passing local checks as needed:
   - `scripts/check_source_immutable.sh`
   - `scripts/prechange_gate.sh`
   - `npm run validate:offer-map`
   - `npm run validate:redirect-map`
   - `npm run validate:wrangler-config`
   - `npm run check`
   - `npm run build`
   - `npm run smoke:astro-v1`
   - `npm run smoke:runtime`
   - `npm run check:static-cache-contract`
   - `node scripts/probe_line31_tracking_qa.mjs`
3. Fix Cloudflare auth if possible without exposing secrets. If auth cannot be repaired non-interactively or with a safe browser login, stop YELLOW with exact human action required.
4. Deploy only the LINE31 tracking patch. Do not deploy unrelated broad changes unless you can prove they are already production-equivalent or inert.
5. Rerun production live proof. Required green proof:
   - `PageView`, `ViewContent`, `ColorSelect`, `QualifiedVisit`, `KaspiClick`, `HighIntentKaspiClick` store correctly;
   - fake `Purchase` remains rejected;
   - browser-spoofed `KaspiRedirect` remains rejected;
   - invalid `/go/not-a-real-color` remains rejected;
   - `utm_placement` and `utm_id` are preserved in root runtime config and `/go/:color` redirects.

## Required Evidence Folder

`~/Docs/acmewear_web_v2/docs/90_REPORTS/line31_green_except_creative_repair_round2_20260601/`

Required files:

- `cloudflare_auth_repair_or_status.md`
- `deploy_decision.md`
- `live_tracking_proof.json`
- `live_tracking_proof.md`
- `COMMANDS_RUN.tsv`

## Assigned Closeout

`~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair_round2/agent2_acmewear_web_cloudflare_liveproof_closeout.md`

The closeout must include standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

Use `GREEN` only if production acmewear.pro live proof is green after deploy.
