# STOREB Live-Readonly Capture Plan

Generated at: `2026-05-11T17:08:52+0500`

Decision: `LAUNCH_AGENT772_STOREB_LIVE_READONLY_CAPTURE_AND_COPIED_TEMP_REPLAY`

## Why One Agent

Use one execution agent. The task is narrow and has a fragile credential/session boundary, so a single focused agent is safer and faster than parallelizing the same live-readonly surface. Existing evidence already proved the gap; the remaining need is one bounded fresh capture plus one contained copied/temp replay.

## Authority Boundary

This plan is proof-only. It does not authorize owner publication, owner send, owner approval request, production DB write, protected workbook write, scheduler install/enablement, LaunchAgent/plist mutation, Web_automation write, browser-login automation, credential/session/cookie/storage-state export, external-system write, cash movement, supplier payment, PO commitment, ad spend, bid/budget/campaign mutation, price change, or stock change.

Agent772 may write only under its assigned Autonomous_business evidence root and assigned closeout path. Any DB mutation must be limited to a copied/temp DB inside the evidence root.

## Current Blocker

Current status from Agent771:

`STOREB_ADS_SOURCE_GAP_STILL_VISIBLE`

Missing STOREB source dates:

- `2026-05-05`
- `2026-05-06`
- `2026-05-07`
- `2026-05-08`
- `2026-05-09`
- `2026-05-10`
- `2026-05-11`

STOREB absence is not zero spend. ACMEWEAR freshness is not STOREB freshness. Universal access identity is not STOREB business identity.

## Agent772 Assignment

Assigned evidence root:

`~/Docs/Autonomous_business/exports/validation/storeb_live_readonly_capture/20260511_170852`

Assigned packet manifest, if created:

`~/Docs/Autonomous_business/exports/validation/storeb_live_readonly_capture/20260511_170852/agent772_packet/packet_manifest.json`

Assigned copied DB, if replay runs:

`~/Docs/Autonomous_business/exports/validation/storeb_live_readonly_capture/20260511_170852/agent772_replay/app_copy.sqlite`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/storeb_live_readonly_capture_20260511_170852_agent772_closeout.md`

Minimum work:

- refresh or capture STOREB ads source evidence for `2026-05-05..2026-05-11`;
- confirm selected business context as `ИП STORE-B`, `STORE-B`, or `STOREB`;
- preserve `business_store_code=STOREB`;
- record Universal/shared login only as `access_store_code=UNIVERSAL_SWITCHER_FOR_STOREB`;
- keep merchant/API id `1065684`, seller/store UID `30000002`, campaign `2609342`, and campaign name `Line52_storeb_26.2.2026` traceable when observed or inherited from reviewed Web_automation config;
- build an immutable `ads_web_source_packet.v1` packet under the evidence root;
- validate with `scripts/validate_ads_source_packet_contract.py --require-existing-files --strict --json`;
- copy production `db/app.db` only into the evidence root if and only if the packet strictly validates;
- replay only against the copied/temp DB;
- run ads sidecar readiness and ads offer-universe coverage validators against the copied/temp DB only, with outputs under the evidence root;
- preserve `product_identity_quarantine=23`, `header_only_source_gap=252`, validator-visible `249`, and combined `275` warning semantics;
- classify the STOREB result without converting missing rows into zero spend.

## Live-Readonly Capture Rules

Agent772 may use existing Web_automation read-only routes only if:

- no files are written inside `~/Docs/Web_automation`;
- outputs can be redirected or copied only into the assigned Autonomous_business evidence root;
- no browser-login automation is performed;
- no credential, cookie, token, session, storage-state, `.env`, browser profile, or secret material is exported, copied, revealed, hashed into public evidence, or packaged;
- no UI/API path mutates campaign, bid, budget, product, account, merchant, or targeting state.

If current authenticated access is unavailable without forbidden actions, Agent772 must stop `YELLOW` as `NO_SAFE_STOREB_LIVE_READONLY_AUTH_AVAILABLE`.

## Required Source References

Agent772 should read the current Web_automation method docs before capture:

- `~/Docs/Web_automation/Docs/kaspi_marketing_storeb_readonly_capture.md`
- `~/Docs/Web_automation/Docs/experiments/storeb_ads/storeb_bid_change_automation_plan.md`
- `~/Docs/Web_automation/config/experiments/storeb_ads_tracking.yaml`

## Acceptable Final Labels

Use exactly one if evidence supports it:

- `STOREB_ADS_SOURCE_FRESH_IN_COPIED_TEMP_REPLAY`
- `STOREB_ADS_SOURCE_BACKED_NO_SPEND_IN_COPIED_TEMP_REPLAY`
- `STOREB_ADS_MAPPING_BLOCKER_VISIBLE`
- `STOREB_ADS_SOURCE_GAP_STILL_VISIBLE`
- `NO_SAFE_STOREB_LIVE_READONLY_AUTH_AVAILABLE`

No label authorizes owner publication, production apply, scheduler execution, external writes, cash/PO/ad/price/stock actions, or owner approval requests.

## Stoplines

Stop immediately if any of these would be required:

- browser-login automation;
- credential, cookie, token, storage-state, browser-profile, `.env`, or session export/copy/reveal/packaging;
- writing inside `~/Docs/Web_automation`;
- writing production `db/app.db`;
- writing protected workbook files;
- scheduler, LaunchAgent, plist, launchctl, installer, or automation mutation;
- external-system write;
- ad spend, bid, budget, product, account, merchant, targeting, or campaign mutation;
- owner publication/send/approval request;
- treating missing STOREB rows as zero spend;
- treating Universal as STOREB business identity;
- treating copied/temp proof as production truth;
- hiding, clearing, downgrading, productizing, or using `23` / `252` warning cohorts as SKU, stock, COGS, profit, or profit-after-ads truth.

## Next Step After Agent772

After Agent772 closes, inspect the closeout and run the smallest relevant repo gates. If Agent772 is `GREEN`, the next lane can be CodeCaptain review of the STOREB proof and then owner-publication readiness delta review. If Agent772 is `YELLOW` or `RED`, keep Daily Survival Brief review-only mode and resolve the exact source/auth blocker first.
