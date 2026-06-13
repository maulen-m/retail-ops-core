# Green Path Phase 2 Ads Scope Backfill Production Apply

Gate: GREEN for ads source truth.

Date: 2026-06-13

## Scope

This lane repaired the remaining ads source-truth blockers by:

- making the ACMEWEAR post-2026-05-04 active scope explicit as `advertised_products_only`;
- capturing missing STOREB May 19-20 read-only source evidence;
- replaying the ads campaign product daily materializer with refresh-only rows enabled for source-backed campaign/day coverage;
- preserving the June 13 `ACMEWEAR/LINE-31-TS` source gap as an explicit narrow quarantine instead of silently treating it as zero.

No campaign, bid, budget, Meta, Kaspi merchant, Telegram, LaunchAgent, workbook, price, stock, customer, or operator-message writes were performed.

## Evidence

- STOREB May 19-20 source capture: `exports/validation/orchestrator_ads_storeb_0519_0520_capture_20260613/storeb_20260519_20260520_owner_login/agent814_storeb_live_capture_owner_login/source/kaspi_marketing.sqlite`
- STOREB source DB SHA-256: `8da473319b455b5fa7f4771641917fd93ce28f50eca59f18f6f32a4bf48d30a7`
- Copied DB proof root: `exports/validation/orchestrator_ads_scope_backfill_prod_candidate_20260613/`
- Production evidence root: `exports/validation/orchestrator_ads_scope_backfill_prod_apply_20260613/`
- Pre-write backup: `exports/validation/orchestrator_ads_scope_backfill_prod_apply_20260613/backups/app_before_ads_scope_backfill_prod_apply_20260613.db`
- Materializer backup: `exports/validation/orchestrator_ads_scope_backfill_prod_apply_20260613/apply/backups/app_2026-06-13_234828.db`
- C3 backup: `exports/validation/orchestrator_ads_scope_backfill_prod_apply_20260613/c3_backups/app_before_agent8_c3_policy_materialization_20260613_234904.db`

## Production Write Summary

Materializer command used `ENABLE_C3_ADS_SOURCE_WRITE=1` and `ALLOW_PRODUCTION_C3_ADS_SOURCE_WRITE=1`.

Summary:

- `mapped_rows`: `250`
- `mapped_source_rows`: `259`
- `refresh_only_rows`: `49`
- `refresh_rows`: `49`
- `source_rows`: `382`
- `unmapped_rows`: `74`
- `source_issues`: `[]`
- `storeb_product_code_mappings_total`: `10`
- `storeb_product_code_mappings_mapped`: `2`
- `storeb_product_code_mappings_blocked`: `8`

Table counts after materializer:

- `ads_source_refresh_runs`: `606`
- `ads_campaign_product_daily`: `2959`
- `meta_external_ads_spend_daily`: `1`

## Validation

Copied DB:

- Ads sidecar readiness: `PASS`
- Ads offer-universe coverage: `PASS`
- Ads spend reality: `PASS`
- Operational integration ads findings: `0`
- C3 copied replay: `ads_source_truth PASS`

Production DB:

- Integrity check: `ok`
- Ads sidecar readiness: `PASS`
- Ads offer-universe coverage: `PASS`
- Ads spend reality: `PASS`
- C3 run id: `orchestrator_ads_scope_backfill_prod_apply_20260613`
- C3 gate shape: `PASS=7`, `BLOCKED=2`
- `ads_source_truth`: `PASS`
- Retained blockers: `source_freshness` and `stock_source_truth`, both stock-related
- Daily ops paused after write: `exports/automation_control/2026-06-13/20260613_235133_verify_daily-ops`, `0/10 loaded`
- DB guard: passed

## Rollback

Use the pre-write backup if the whole ads scope/backfill production write must be reverted:

```bash
sqlite3 db/app.db ".restore 'exports/validation/orchestrator_ads_scope_backfill_prod_apply_20260613/backups/app_before_ads_scope_backfill_prod_apply_20260613.db'"
```

After rollback, rerun C3 policy materialization and the three ads validators before any owner-facing publication.
