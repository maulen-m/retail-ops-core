# LINE31 Expert Plan Completion Wave - 2026-06-06

Canonical objective:

Complete the external expert plan verification after the LINE31 countrywide Meta launch, the owner manual budget change to 5500 Meta minor units, the Meta app-public WebUI completion, and the LINE31 black-card incident website hotfix.

External expert answer:

`~/Docs/Oracle/oracle_packs/Instagram_funnel_packs/line31_countrywide_48h_second_take_scale_traceability_oracle_pack__20260606_1221_GMT5/Answer/Strategy_expert_06.06.2026_13_11_13.md`

Approval boundary:

The owner approved `LINE31_EXPERT_PLAN_COMPLETION_WAVE_20260606_ONE_TAKE` in chat. The approval authorizes read-only/source-refresh/local-evidence work across `Business_3/Facebook_ads`, `Autonomous_business`, `acmewear_web_v2`, and related local evidence folders. It also authorizes one bounded Meta API live-write smoke only if fresh preflight passes first: create exactly one unattached non-delivering adcreative smoke object, read it back, confirm no ad object was created, and record evidence.

This approval does not authorize creating/updating campaigns, ad sets, ads, budgets, statuses, targeting, landing URLs, delivery creatives, website deploys, Kaspi/WebUI/API writes, CRM writes, price changes, stock changes, cash movement, supplier payment, PO commitment, production DB/workbook writes, scheduler/source-pointer changes, owner publication, internal Kaspi campaign changes, or unrelated external action.

Known current facts to verify, not assume:

- LINE31 Meta campaign id: `120245481137650641`
- LINE31 Meta ad set id: `120245481997290641`
- LINE31 ads: `120245492808400641`, `120245488532270641`, `120245492808390641`
- Owner manually set current ad set daily budget to `5500` Meta minor units at `2026-06-06_15_23_52`.
- The old 25k approval path that expected `3093 -> 5155` is stale and must not be reused.
- The LINE31 black-card incident hotfix was deployed after approval and should route primary/default/final/sticky CTA to `/go/ivory-white-starry-black`.
- Meta app `Ads_ACMEWEAR` was published/public by WebUI, but the smoke lane must still prove API create eligibility.

## Agent Plan

Run Agents 1-5 in parallel. Run Agent 6 only after the orchestrator reviews Agents 1-5 closeouts.

1. Agent 1 - Meta current state and metrics readback.
2. Agent 2 - LINE31 order/status/cancellation truth refresh.
3. Agent 3 - LINE31 stock/cash/PO guard refresh.
4. Agent 4 - Website tracking and route QA refresh.
5. Agent 5 - Meta API factory guard reconciliation and one bounded adcreative smoke if fresh preflight passes.
6. Agent 6 - Synthesis and decision packet.

## Gate Rules

Use `Gate: GREEN` only for a lane whose own evidence and validators pass.

Use `Gate: YELLOW` for retained blockers, stale source windows, soft-pass traceability, unproven API factory, or missing owner/current cash confirmation.

Use `Gate: RED` for boundary violation, accidental external write outside approval, unexplained campaign/adset/ad drift, failed smoke that creates an ad object, or production DB/workbook mutation.

The wave can complete as overall `YELLOW` if the only remaining blockers are honest retained blockers. Do not force GREEN.
