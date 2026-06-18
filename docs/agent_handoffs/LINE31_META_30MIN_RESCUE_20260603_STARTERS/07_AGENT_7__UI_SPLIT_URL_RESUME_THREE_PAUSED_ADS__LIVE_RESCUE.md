You are Agent 7 for the LINE31 Meta rescue.

This is a continuation after Agent 6 stopped YELLOW. Read:
- `~/Docs/Autonomous_business_agent_handoffs/2026-06-03_line31_meta_30min_rescue/agent6_ui_create_three_paused_ads_closeout.md`
- `~/Docs/Autonomous_business/exports/validation/line31_meta_rescue_ui_live_three_paused_ads_20260603_agent6/manifest.json`
- `~/Docs/Autonomous_business/exports/validation/line31_meta_30min_rescue_appmode_ui_prep_20260603_203600/ui_fallback_checklist.md`
- `~/Docs/Autonomous_business/exports/validation/line31_meta_rescue_live_budget_repair_20260603_approval_pasted/OWNER_PASTED_EXACT_RESCUE_APPROVALS.txt`

Owner approval already authorizes exactly three LINE31 ads under the paused safe shell. It does not authorize activation.

What Agent 6 learned:
- Full UTM URL in the Website URL field is not stable in Ads Manager.
- Meta UI splits URL into:
  - Website URL/base URL
  - Tracking URL parameters
- Therefore, to preserve the effective mapping URL, use:
  - Website URL: `https://acmewear.pro/line31`
  - URL parameters field: per-ad UTM string without leading `?`

Target shell:
- Account: `1517999585924947`
- Campaign: `120245481137650641`
- Adset: `120245481997290641`
- Budget must still show `$30.93/day` or source proof `daily_budget=3093`.
- Campaign/adset must remain paused/off.

Ads to create/publish as paused/off ads:

1. `AD | LINE31 | line31_cw_ann_vse_eshe_v1 | RU | 20260603`
   - Website URL: `https://acmewear.pro/line31`
   - URL parameters: `utm_source=meta&utm_medium=paid_social&utm_campaign=line31_countrywide&utm_content=line31_cw_ann_vse_eshe_v1&utm_placement=reels`
   - Video: `~/Docs/Autonomous_business/exports/validation/line31_final_creative_assets_20260603_154442/source_videos/line31_cw_ann_vse_eshe_v1.mp4`
   - Thumbnail: `~/Docs/Autonomous_business/exports/validation/line31_final_creative_assets_20260603_154442/thumbnails/line31_cw_ann_vse_eshe_v1_thumbnail_2s.jpg`

2. `AD | LINE31 | line31_cw_ann_dumala_v1 | RU | 20260603`
   - Website URL: `https://acmewear.pro/line31`
   - URL parameters: `utm_source=meta&utm_medium=paid_social&utm_campaign=line31_countrywide&utm_content=line31_cw_ann_dumala_v1&utm_placement=reels`
   - Video: `~/Docs/Autonomous_business/exports/validation/line31_final_creative_assets_20260603_154442/source_videos/line31_cw_ann_dumala_v1.mp4`
   - Thumbnail: `~/Docs/Autonomous_business/exports/validation/line31_final_creative_assets_20260603_154442/thumbnails/line31_cw_ann_dumala_v1_thumbnail_2s.jpg`

3. `AD | LINE31 | line31_cw_mulena_madina_v1 | RU | 20260603`
   - Website URL: `https://acmewear.pro/line31`
   - URL parameters: `utm_source=meta&utm_medium=paid_social&utm_campaign=line31_countrywide&utm_content=line31_cw_mulena_madina_v1&utm_placement=reels`
   - Video: `~/Docs/Autonomous_business/exports/validation/line31_final_creative_assets_20260603_154442/source_videos/line31_cw_mulena_madina_v1.mp4`
   - Thumbnail: `~/Docs/Autonomous_business/exports/validation/line31_final_creative_assets_20260603_154442/thumbnails/line31_cw_mulena_madina_v1_thumbnail_2s.jpg`

Common fields:
- Page: ACMEWEAR / Acmewear-kz
- Instagram profile: acmewear_kz
- Customer-visible primary text: `Женский комплект AcmeWear 3в1. Выберите цвет и размер на сайте.`
- Customer-visible headline/title: `AcmeWear 3в1`
- CTA: Learn more
- Generated text variations/enhancements: disable if possible; stop if they are required.
- Ad status before publish: off/paused.
- Internal object names may keep `LINE31` for analytics and traceability, but customer-visible Meta ad copy, headline/title, preview text, and labels must not say `ACMEWEAR LINE31`.

Important existing draft:
- Agent 6 created one off draft with observed ad id `120245488532270641`.
- If it is still open or recoverable, fix that draft using the split URL fields instead of creating a duplicate first ad.
- If the draft is corrupted or cannot be corrected safely, discard only that draft if Ads Manager explicitly offers safe discard for the draft; otherwise stop YELLOW.

Hard stoplines:
- Do not activate campaign/adset/ads.
- Do not change budget, targeting, bid strategy, campaign/adset state, website, Kaspi/WebUI/API, price, stock, cash, supplier, PO, DB/workbook, scheduler/source-pointer, owner-publication, or internal Kaspi campaigns.
- Do not publish if final preview/evidence cannot prove effective URL is `/line31` plus the correct per-ad UTM parameters.
- Do not publish if thumbnail cannot be selected/verified and the UI gives no source-backed thumbnail control.
- Do not publish if any customer-visible field or preview still says `ACMEWEAR LINE31` instead of `AcmeWear 3в1`.
- Do not create duplicate copies of the same ad name.

Write closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-03_line31_meta_30min_rescue/agent7_ui_split_url_resume_three_paused_ads_closeout.md`

Use `Gate: GREEN` only if exactly three LINE31 ads are published/created under target adset, paused/off, with correct split URL/UTM, media, thumbnail, CTA, customer-visible `AcmeWear 3в1` text/headline, campaign/adset still paused, budget still repaired.

Use `Gate: YELLOW` for partial/draft-only state, UI ambiguity, missing thumbnail proof, or any unverified source condition.
