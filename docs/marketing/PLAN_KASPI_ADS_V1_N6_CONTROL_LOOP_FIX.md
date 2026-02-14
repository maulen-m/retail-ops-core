# PLAN_KASPI_ADS_V1_N6_CONTROL_LOOP_FIX

## Problem fixed (N4 replay defect)
- N4 showed restore/rollback decisions using stale `campaign_product_daily_current.bid_cpc=300` while live bid was already `200`.
- Result: restore repeated `200` instead of returning to pre-canary bid.

## N6 fix summary
1. Deterministic current-bid source of truth in `scripts/kaspi_ads_bid_manager.py`:
   - Priority 1: latest `hourly_snapshot.bid_cpc` per `(campaign_id, sku_key)`
   - Priority 2: latest `bid_change_log.new_bid` where `success=1`
   - Priority 3: latest `campaign_product_daily_current.bid_cpc`
2. Restore correctness:
   - For schedule rules named with `restore`, target bid is restored from last successful change history (`old_bid`) when current bid equals that change's `new_bid`.
   - This restores pre-canary bid even if daily current is stale.
3. Daily facts from hourly telemetry:
   - `scripts/kaspi_ads_build_hourly_profile.py` now maintains `hourly_delta_daily_fact` keyed by:
     - `(date, merchant_id, campaign_id, sku_key)`
   - Aggregates are idempotent (upsert) and include:
     - `bid_cpc` (latest hourly bid for key/day)
     - `views`, `clicks`, `cost`, `gmv`, `orders_total`, `hour_rows`
4. Elasticity source update:
   - `scripts/kaspi_ads_elasticity.py` now reads telemetry daily facts from `hourly_delta_daily_fact`.
   - If both tables exist, telemetry facts override overlapping rows from `campaign_product_daily_current`.
   - This unblocks Universal/Line52 analysis when daily current table has gaps.

## Why this prevents repeat
- Restore and rollback no longer depend on daily table freshness.
- Hourly telemetry is always the first truth layer for current bid state.
- If hourly data is unavailable, change-log history still reflects last applied bid before daily fallback.

## Operator runbook updates (effective immediately)
1. Before canary restore/rollback windows, ensure hourly pipeline has run and `hourly_snapshot` is fresh.
2. Build/update daily facts before elasticity:
   - `python3 scripts/kaspi_ads_build_hourly_profile.py --ads-db <WT_ADS_DB>`
3. For restore validation, inspect latest `bid_change_log`:
   - Expect restore entry `old_bid=<reduced_bid>` and `new_bid=<pre_canary_bid>`.
4. Keep write safety unchanged:
   - live writes only when `ENABLE_KASPI_ADS_WRITE=1` and `--apply` are both set.

## Test coverage added
- Restore uses hourly bid truth and restores pre-canary bid from history.
- Fallback order is enforced: hourly snapshot -> bid_change_log -> daily current.
- Daily fact aggregation is idempotent and sum-correct.
- Elasticity works from telemetry daily facts only and prefers telemetry facts over stale daily rows.
