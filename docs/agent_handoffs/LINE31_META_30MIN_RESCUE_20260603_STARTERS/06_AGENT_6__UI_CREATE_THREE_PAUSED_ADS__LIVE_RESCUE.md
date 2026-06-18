You are Agent 6 for the LINE31 Meta 30-minute rescue.

Read:
- `~/Docs/Autonomous_business/AGENTS.md`
- `~/Docs/Autonomous_business/docs/00_START_HERE.md`
- `~/Docs/Autonomous_business/exports/validation/line31_meta_30min_rescue_appmode_ui_prep_20260603_203600/ui_fallback_checklist.md`
- `~/Docs/Autonomous_business/exports/validation/line31_meta_rescue_live_budget_repair_20260603_approval_pasted/manifest.json`
- `~/Docs/Autonomous_business/exports/validation/line31_meta_rescue_live_three_paused_ads_20260603_approval_pasted/manifest.json`

Owner approval evidence is now present at:
`~/Docs/Autonomous_business/exports/validation/line31_meta_rescue_live_budget_repair_20260603_approval_pasted/OWNER_PASTED_EXACT_RESCUE_APPROVALS.txt`

Your objective:
Create exactly three LINE31 ads under the existing paused Meta shell using Ads Manager UI fallback only, because the API creative route is blocked by app development mode.

Scope:
- Campaign: `120245481137650641`
- Adset: `120245481997290641`
- Required repaired adset budget before any ad creation: `$30.93/day` display or `daily_budget=3093` source proof.
- Required state before ad creation: campaign PAUSED/OFF, adset PAUSED/OFF.
- Create exactly these three ads, and leave them paused/off:
  - `AD | LINE31 | line31_cw_ann_vse_eshe_v1 | RU | 20260603`
  - `AD | LINE31 | line31_cw_ann_dumala_v1 | RU | 20260603`
  - `AD | LINE31 | line31_cw_mulena_madina_v1 | RU | 20260603`
- Use exact video/thumbnail/landing URL rows from `ui_fallback_checklist.md`.

Hard stoplines:
- If Ads Manager still shows `$150.00/day` after reload/wait, stop YELLOW. Do not create ads.
- If you cannot verify you are scoped to account `1517999585924947`, campaign `120245481137650641`, and adset `120245481997290641`, stop YELLOW.
- If UI requires changing budget, targeting, bid strategy, campaign/adset state, website, Kaspi/WebUI/API, price, stock, cash, supplier, PO, DB/workbook, scheduler/source-pointer, owner-publication, or internal Kaspi campaigns, stop YELLOW.
- Do not activate campaign/adset/ads. Final activation is for the orchestrator only after independent verification.
- Do not use Meta API to create ad creatives; it is blocked by app development mode. You may use read-only API verification after cooldown if available, but UI/screenshot evidence is acceptable if API is rate-limited.
- Do not blind-click. If UI automation tooling is unavailable or unclear, stop YELLOW with evidence.

Write closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-03_line31_meta_30min_rescue/agent6_ui_create_three_paused_ads_closeout.md`

Closeout must include standalone line `Gate: GREEN` only if all three paused ads are created and verified under the target adset while budget remains `$30.93/day`/`3093` and campaign/adset remain paused.

Use `Gate: YELLOW` for UI unavailable, API/rate-limit verification incomplete, budget display still stale/unsafe, or partial creation. Use `Gate: RED` only for an unsafe/unapproved mutation.

After closeout, do not ping manually; just leave the pane idle.
