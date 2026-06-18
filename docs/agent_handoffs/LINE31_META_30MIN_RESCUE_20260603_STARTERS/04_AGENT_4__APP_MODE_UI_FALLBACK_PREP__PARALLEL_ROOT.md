# Agent 4 - LINE31 App-Mode And UI Fallback Prep

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_META_30MIN_RESCUE_20260603_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Autonomous_business/exports/validation/line31_meta_api_live_partial_blocker_20260603_194405/manifest.json`
5. This assigned starter prompt.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-03_line31_meta_30min_rescue/agent4_app_mode_ui_fallback_prep_closeout.md`

Task:

1. Inspect the app development-mode blocker evidence and determine whether the API path is currently eligible.
2. If API still blocked, prepare the fastest Chrome/Ads Manager UI fallback checklist for exactly three LINE31 ads under campaign `120245481137650641` and adset `120245481997290641`.
3. Do read-only Chrome/Ads Manager navigation only if available and safe; do not click any final create/update/save/publish controls.
4. Produce exact UI field checklist: campaign/adset, creative IDs, local video paths, thumbnails, ad names, landing URLs, CTA, status after creation.
5. Write local evidence under `~/Docs/Autonomous_business/exports/validation/line31_meta_30min_rescue_appmode_ui_prep_<timestamp>`.

Gate rules:

- GREEN if a source-backed API-eligible path or UI fallback checklist is ready with no live writes.
- YELLOW if access/tooling blocks UI/API preparation.
- RED if any external write was performed.

Do not create ads, repair budget, activate anything, change targeting, change bid strategy, deploy website, touch Kaspi/WebUI/API, price, stock, cash, supplier, PO, DB/workbook, scheduler/source-pointer, owner publication, or internal Kaspi campaigns.
