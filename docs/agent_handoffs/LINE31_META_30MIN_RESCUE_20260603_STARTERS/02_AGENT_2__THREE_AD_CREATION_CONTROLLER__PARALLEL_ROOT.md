# Agent 2 - LINE31 Three-Ad Creation Controller

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_META_30MIN_RESCUE_20260603_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Autonomous_business/exports/validation/line31_meta_publish_bridge_20260603_183005/final_creative_asset_mapping_3ads_owner_approved.json`
5. This assigned starter prompt.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-03_line31_meta_30min_rescue/agent2_three_ad_creation_controller_closeout.md`

Task:

1. Prepare exact three-ad creation route using the owner-approved mapping.
2. Inspect whether Meta API app-mode blocker is resolved. If not resolved, prefer Chrome/Ads Manager UI fallback.
3. Check whether exact owner approval for `LINE31_META_CREATE_EXACT_THREE_ADS_ONLY_UNDER_PAUSED_SAFE_SHELL` is present.
4. If approval is absent, do not write. Produce YELLOW closeout with exact missing approval and the prepared route.
5. If approval is present and budget Agent 1 evidence proves adset daily_budget `3093`, create exactly three ads under campaign `120245481137650641` and adset `120245481997290641`.
6. Campaign and adset must remain PAUSED after ad creation unless final activation approval exists and Agent 3 owns activation.
7. Verify exactly three LINE31 ads exist under the target adset and match the three creative IDs/landing URLs.
8. Write local evidence under `~/Docs/Autonomous_business/exports/validation/line31_meta_30min_rescue_three_ads_<timestamp>`.

Gate rules:

- GREEN only if exactly three LINE31 ads were owner-approved, created, and source-verified under the target adset with no unrelated changes.
- YELLOW if approval is absent, budget is not repaired, app/API/UI blocks creation, or verification is incomplete.
- RED if unrelated objects changed or more/fewer than three target ads were created.

Do not repair budget, activate campaign/adset/ads, change targeting, change bid strategy, deploy website, touch Kaspi/WebUI/API, price, stock, cash, supplier, PO, DB/workbook, scheduler/source-pointer, owner publication, or internal Kaspi campaigns.
