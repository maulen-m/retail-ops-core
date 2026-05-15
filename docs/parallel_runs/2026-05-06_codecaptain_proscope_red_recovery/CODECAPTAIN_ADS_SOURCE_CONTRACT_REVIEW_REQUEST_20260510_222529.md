# CodeCaptain Ads Source Contract Review Request

Generated: `2026-05-10T22:25:29+0500`

Status: `READY_FOR_CODECAPTAIN_REVIEW`

Gate: `REVIEW_ONLY_SOURCE_CONTRACT_REQUEST`

## Question

Review the proposed AB/Web ads source-contract path for improving `ADS_SOURCE_STALE` coverage using existing `~/Docs/Web_automation` read-only Kaspi Marketing fetch/storage/freshness patterns.

Return exactly one decision token:

- `GREEN_ACCEPT_ADS_SOURCE_CONTRACT_REVIEW_ONLY`
- `YELLOW_AMEND_ADS_SOURCE_CONTRACT_BEFORE_LIVE_READONLY`
- `RED_DO_NOT_USE_WEB_ADS_ADOPTION_PATH`

This review must not authorize live fetches, browser login, scheduler automation, production DB/workbook mutation, Web_automation writes, owner publication, external writes, cash movement, PO commitment, ad spend, price/stock changes, production apply, or owner approval requests.

## Current Sequence State

Phase `5.5` operator acceptance is now recorded:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CASH_RISK_DAILY_OPERATOR_ACCEPTANCE_PHASE_5_5_20260510_222529.md`

Current grade:

`6.8 / 10`

Current authority:

`review_only`

Remaining blockers:

- `ADS_SOURCE_STALE`
- `ads_source_contract_not_reviewed`
- `owner_publication_readiness_delta_not_yet_reviewed`
- `owner_publication_scheduler_production_external_writes_require_separate_authorization`

## Current Ads Problem

The current Cash Risk Daily proof is acceptable for review-only operator use because ads-dependent decisions remain blocked. It is not ads-fresh owner-publication proof.

Current ads facts:

- `ADS_SOURCE_STALE` remains visible.
- `ads_source_fresh` passed only in tolerated review mode with details `mode=live reason=stale age_hours=859.25 max_age_hours=36.0`.
- Current mapping coverage is clean in the copied proof, but source freshness is not clean.
- `23` product-identity quarantine rows and `252` header-only source-gap rows remain visible and must not be weakened.

## Discovery Evidence

Read-only tmux discovery wave:

- Agent754 `GREEN`: Web_automation fetch/storage inventory.
- Agent755 `GREEN`: Web_automation freshness/watchers/checkpoints inventory.
- Agent756 `YELLOW`: AB adoption mapper; requires source-contract review before adoption.

Discovery synthesis:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/WEB_AUTOMATION_ADS_ADOPTION_DISCOVERY_SYNTHESIS_20260510_220320.md`

## Proposed Contract

Input must be a reviewed Web_automation capture packet or SQLite snapshot. It must include:

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

The contract must preserve store identity:

- AB-facing business identity stays `STOREB` for STOREB.
- Universal access path must be recorded separately as `access_store_code`.
- Web_automation credentials, storage state, cookies, and browser profiles must not be copied into AB or Oracle packs.

AB adapter output must stay in a copied/temp DB evidence lane and project into:

- `ads_campaign_product_daily(date, store_code, sku_key, cost_kzt, source_run_id, coverage_status)`
- `ads_source_refresh_runs(run_id, merchant_id, store_code, date_start, date_end, finished_at, status, campaign_days_total, product_rows_total)`

Required validator replay:

- `ads_sidecar_readiness`
- `ads_offer_universe_coverage`

Required status behavior:

- `ADS_SOURCE_STALE` clears only when a reviewed source-fresh packet satisfies AB max-age policy.
- Stale or missing ads rows become machine-readable gaps, not zero spend.
- `allow-stale` behavior may only affect command severity; it must never rewrite freshness truth.
- `23` product-identity quarantine and `252` header-only source-gap warnings remain visible.

## Review Questions

1. Is this source-contract safe enough to become the next design-only ads freshness path?
2. Are the required Web_automation input fields sufficient for AB validator trust?
3. Are the AB adapter output tables and validator replay gates sufficient?
4. What amendments are required before any live-readonly Web_automation proof?
5. Does the contract preserve the distinction between clean mapping coverage and stale source freshness?

## Non-Authorization Boundary

Even if this contract is accepted, the next step is only a separately approved live-readonly proof or copied-packet proof. Acceptance does not authorize:

- live Kaspi Marketing fetch
- browser login
- `.env`, cookie, storage state, or browser profile reads for packaging
- Web_automation writes
- production `db/app.db` writes
- protected workbook writes
- scheduler, LaunchAgent, or plist mutation
- owner publication
- owner send
- owner approval request
- external-system writes
- ad-platform mutation
- cash movement
- supplier payment
- PO commitment
- ad spend
- price or stock change
- treating Web_automation current tables as production authority without a reviewed packet

## Requested Output

Return exactly one decision token and then list:

- required amendments, if any;
- minimum allowed next lane;
- evidence that must be included in the next proof;
- stoplines that must remain visible.
