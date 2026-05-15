# Web Automation Ads Adoption Discovery Synthesis

Generated: `2026-05-10T22:03:20+0500`

Status: `READONLY_DISCOVERY_COMPLETE_ADAPTER_REVIEW_NEEDED`

Gate: `YELLOW_SOURCE_CONTRACT_REVIEW_BEFORE_ADOPTION`

## Executive Decision

Yes, Web_automation has reusable ads fetch, storage, heartbeat, freshness, and gap-report patterns that can materially improve the Autonomous Business ads freshness path. No, we should not wire it directly into AB yet.

The most efficient safe path is:

1. Preserve CodeCaptain's mandatory Phase `5.5` operator-acceptance gate for Cash Risk Daily.
2. Build a design-only AB/Web ads source-contract review pack from this discovery.
3. After CodeCaptain/operator approval, run a separate explicitly authorized Web_automation live-readonly proof or consume a reviewed fresh Web_automation capture packet.
4. Only then build a copied/temp-DB AB adapter proof and rerun `ads_sidecar_readiness` plus `ads_offer_universe_coverage`.

## Inputs Read

CodeCaptain sequence reevaluation answer:

`~/Docs/Oracle/Autonomous_business/2026-05-10/203425_TASK-000_codecaptain-business-decision-system-sequence-reevaluation/answer/Code_Captain_10.05.2026_21_29_24.md`

Discovery control:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/WEB_AUTOMATION_ADS_ADOPTION_DISCOVERY_CONTROL_20260510_215225.md`

Tmux manifest:

`~/Docs/Autonomous_business/runs/tmux_orchestration/web_ads_adoption_readonly_20260510_215225/orchestration_manifest.json`

Agent closeouts:

- Agent754 `GREEN`: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_754_web_ads_fetch_storage_inventory_closeout.md`
- Agent755 `GREEN`: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_755_web_ads_freshness_watchers_inventory_closeout.md`
- Agent756 `YELLOW`: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_756_ab_ads_adoption_mapper_closeout.md`

## What The Agents Found

Agent754 found a concrete reusable Web_automation ads capture/storage surface:

- CLI shape: `./web-auto --json kaspi-marketing fetch-campaigns`.
- Normalized outputs: `campaign_daily_current.csv`, `campaign_product_daily_current.csv`, `summary.json`, raw payload JSON, and local SQLite.
- SQLite tables: `campaign_daily_current`, `campaign_daily_history`, `campaign_product_daily_current`, `campaign_product_daily_history`.
- Proven source identity fields: `date`, `merchant_id`, `store_code`, `campaign_id`, product identifiers, `record_timestamp`, `ingested_at`, and `run_id` in history.
- STOREB identity is already modeled as business store `STOREB` via Universal access path, which matches the AB rule that business identity and access identity must stay separate.

Agent755 found reusable freshness/watchdog patterns:

- `watch-health` and `heartbeat` produce machine-readable source status.
- Source state distinguishes missing/stale/partial from fresh instead of hiding it.
- `allow-stale` can make a command nonfatal, but stale status remains visible.
- Scheduled checkpoint modes split `plan`, `dry-live`, and `live-readonly`.
- Gap/backfill patterns can become an AB exception queue for missing `(date, campaign_id)` ads evidence.

Agent756 mapped the AB adoption boundary:

- Current AB mapping coverage is not the main blocker.
- Current proof has `ADS_SOURCE_STALE` with `age_hours=859.25` and `max_age_hours=36.0`.
- AB validators expect AB canonical tables such as `ads_campaign_product_daily` and `ads_source_refresh_runs`; Web_automation tables cannot be treated as a silent path swap.
- The correct adoption shape is an explicit adapter contract, copied/temp-DB proof, and validator replay.

## Current Ads Truth

The current Cash Risk Daily proof can remain review-only. It is not ads-fresh owner-publication proof.

Important distinction:

- Coverage is currently clean enough for the copied-DB review surface.
- Freshness is not clean enough for ads-dependent claims.
- `ADS_SOURCE_STALE`, `23`, and `252` must remain visible.

Blocked while stale:

- ad spend
- profit-after-ads claims
- ads-dependent owner publication
- scheduler enablement
- production DB/workbook mutation
- external writes
- source-missing-as-zero treatment

## Adoption Options

Option `1` - Recommended now: source-contract review pack.

Build a compact AB/Web ads adapter contract for CodeCaptain review. It should define allowed Web_automation input artifacts, schema, freshness rules, store identity handling, copied/temp-DB output targets, validator replay commands, gap queue shape, and non-authorized actions.

Why this is best:

- Lowest blast radius.
- Converts discovery into implementable architecture.
- Does not require secrets, browser login, live fetch, scheduler work, or DB/workbook mutation.
- Gives CodeCaptain a precise review target before implementation.

Option `2` - After approval: live-readonly Web_automation proof lane.

Run Web_automation's existing read-only Kaspi Marketing capture for the required stores/campaigns, produce a redacted reviewed capture packet, and then let AB consume the packet in copied/temp-DB proof.

Why not first:

- It touches credentials and live systems.
- It must be explicitly authorized.
- Fresh data alone is not enough until AB has a reviewed adapter contract.

Option `3` - After contract proof: AB adapter implementation.

Implement the adapter that reads a reviewed Web_automation packet or SQLite snapshot, materializes AB canonical ads evidence into a copied/temp DB, and reruns ads validators under contained evidence roots.

Why not first:

- The source-contract bridge is not reviewed yet.
- Direct implementation risks clearing `ADS_SOURCE_STALE` by path swap instead of evidence.

Option `4` - Do not adopt yet.

Keep Web_automation only as reference material and continue with operator acceptance/owner-publication readiness while leaving ads stale and blocked.

Why not recommended:

- Safe but leaves the core ads freshness issue unsolved.
- Web_automation already has enough reusable surface to justify a design-only contract.

## Recommended Next Tasks

The next most efficient tasks are:

1. Run Phase `5.5` operator acceptance or amendment of the Cash Risk Daily review surface.
2. In a separate review-only lane, package the AB/Web ads source-contract review for CodeCaptain.
3. If both are accepted, request explicit approval for a live-readonly Web_automation capture proof.
4. Use that proof to build a copied/temp-DB AB adapter evidence run and rerun ads validators.

## Proposed Adapter Contract

Input must be a reviewed Web_automation capture packet or SQLite snapshot with:

- `source_contract_version`
- `run_id`
- `captured_at`
- `finished_at`
- `date_start`
- `date_end`
- `business_store_code`
- `access_store_code`
- `campaign_ids`
- source DB path
- source DB SHA
- raw payload hash manifest
- row counts
- heartbeat status
- gap status

AB adapter output must stay in a copied/temp DB evidence lane and project into:

- `ads_campaign_product_daily(date, store_code, sku_key, cost_kzt, source_run_id, coverage_status)`
- `ads_source_refresh_runs(run_id, merchant_id, store_code, date_start, date_end, finished_at, status, campaign_days_total, product_rows_total)`

Required validator replay:

- `ads_sidecar_readiness`
- `ads_offer_universe_coverage`

Required status behavior:

- `ADS_SOURCE_STALE` clears only when the reviewed source-fresh packet satisfies AB max-age policy.
- Stale or missing ads rows become machine-readable gaps, not zero spend.
- `23` product-identity quarantine and `252` header-only source-gap warnings remain visible.

## Not Authorized

This synthesis does not authorize:

- live Kaspi Marketing fetch
- browser login
- reading `.env`, cookies, storage state, browser profiles, or secrets
- Web_automation writes
- production `db/app.db` write
- protected workbook write
- scheduler, LaunchAgent, or plist mutation
- owner publication
- owner send
- owner approval request
- external-system write
- ad-platform mutation
- cash movement
- PO commitment
- ad spend
- price or stock change
- treating Web_automation current tables as production authority without a reviewed packet

## Gate

Gate remains `YELLOW_SOURCE_CONTRACT_REVIEW_BEFORE_ADOPTION`.

Reason: the discovery proves reusable components and a clear adapter path, but actual adoption still requires a source-contract review and separate approval before any live-readonly proof or implementation.
