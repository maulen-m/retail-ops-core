# LINE31 Meta 30-Minute Rescue Handoff

Gate: YELLOW_RESCUE_READY_APPROVAL_GATED

Purpose: recover the LINE31 countrywide Meta launch fast without hiding the two live blockers:

- Ad set `120245481997290641` is paused but still has unsafe `daily_budget=15000`, observed by owner as `$150/day`.
- Three LINE31 ads are not source-verified created/live.

Current source-backed facts:

- Campaign: `120245481137650641`
- Ad set: `120245481997290641`
- Safety pause evidence: `~/Docs/Autonomous_business/exports/validation/line31_meta_partial_shell_safety_pause_20260603_201456/manifest.json`
- Budget stopline: `~/Docs/Autonomous_business/exports/validation/line31_meta_budget_currency_stopline_20260603_195144/manifest.json`
- Currency-safe preflight lock: `~/Docs/Business_3/Facebook_ads/exports/validation/line31_meta_publish_preflight_20260603_budget_currency_repair_plan_fx485/preflight_evidence_lock.json`
- Currency-safe preflight SHA-256: `58c31f4a79cf71d8431810b874cfe594e615cfdb58de119a4f6297029670114e`
- Target repaired daily budget: `3093` Meta minor units, meaning `30.93 USD/day` at `485 KZT/USD`, for owner intent `15000 KZT/day`.
- Final mapping: `~/Docs/Autonomous_business/exports/validation/line31_meta_publish_bridge_20260603_183005/final_creative_asset_mapping_3ads_owner_approved.json`

## Parallel Agents

Agent 1, Budget Repair Controller:

- Verify current campaign/adset state read-only.
- Verify paused state and current `daily_budget`.
- If and only if exact owner budget repair approval is present, repair only the paused adset budget to `3093` and keep campaign/adset paused.
- Close out GREEN only if source-backed post-write verification proves paused + budget `3093`.

Agent 2, Three-Ad Creation Controller:

- Prepare the fastest viable path to create exactly three ads from the owner-approved mapping.
- Prefer Meta API only if app-mode blocker is solved; otherwise use Chrome/Ads Manager UI fallback if exact owner approval exists.
- Do not change campaign/adset budget, targeting, or unrelated objects.
- Close out GREEN only if exactly three LINE31 ads are source-verified under the target adset.

Agent 3, Final Launch Verification And Activation Controller:

- Monitor Agent 1 and Agent 2 closeouts.
- If both are GREEN and exact final activation approval exists, activate only campaign, adset, and exactly three created ads.
- Run post-launch read-only Meta + website tracking + redirect QA verification.
- Close out GREEN only if campaign/adset/three ads are active, budget is `3093`, and post-launch QA evidence is local.

## Required Owner Approval Phrases

Budget repair, exact current plan:

```text
I approve LINE31_META_PAUSED_ADSET_BUDGET_REPAIR_ONLY: update only adset 120245481997290641 while it remains paused, changing daily_budget from 15000 to 3093 Meta minor units (30.93 USD/day) based on owner-accepted FX 485 KZT/USD for the owner-approved 15,000 KZT/day intent. Keep campaign 120245481137650641 and adset 120245481997290641 PAUSED. Do not create ads, change campaign/adset targeting/state beyond keeping paused, change Kaspi/WebUI/API, website, price, stock, cash, supplier, PO, DB/workbook, scheduler/source-pointer, owner-publication, or internal Kaspi campaigns.
```

Create exactly three ads, paused shell only:

```text
I approve LINE31_META_CREATE_EXACT_THREE_ADS_ONLY_UNDER_PAUSED_SAFE_SHELL: create exactly three LINE31 ads under campaign 120245481137650641 and adset 120245481997290641 using the owner-approved mapping ~/Docs/Autonomous_business/exports/validation/line31_meta_publish_bridge_20260603_183005/final_creative_asset_mapping_3ads_owner_approved.json, landing URL https://acmewear.pro/line31, and the three local creative videos/thumbnails in that mapping. Campaign and adset must remain PAUSED after ad creation unless a later final activation approval is provided. Do not change budget, targeting, bid strategy, campaign/adset state, Kaspi/WebUI/API, website, price, stock, cash, supplier, PO, DB/workbook, scheduler/source-pointer, owner-publication, or internal Kaspi campaigns.
```

Final activation only after repaired budget and three ads are verified:

```text
I approve LINE31_META_FINAL_ACTIVATE_ONLY_AFTER_BUDGET_AND_3ADS_VERIFIED: after local evidence proves adset 120245481997290641 has daily_budget 3093 and exactly three LINE31 ads exist under it from the owner-approved mapping, activate only campaign 120245481137650641, adset 120245481997290641, and those exact three LINE31 ads. Do not change budget, targeting, bid strategy, creative, landing URL, Kaspi/WebUI/API, website, price, stock, cash, supplier, PO, DB/workbook, scheduler/source-pointer, owner-publication, or internal Kaspi campaigns.
```

## Stop Rules

- If exact approval is absent, write a YELLOW closeout with the missing approval phrase and do not write externally.
- If budget is not repaired to `3093`, do not create or activate ads.
- If app-mode blocks API creative creation, switch to UI fallback planning, but still require exact approval before UI writes.
- Do not call launch complete until three ads are source-verified active with repaired budget and post-launch QA evidence.
