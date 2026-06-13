# Green Path Phase 2 Ads LINE-31-TS Quarantine

Gate: GREEN for the `ACMEWEAR/LINE-31-TS` sold-offer coverage sub-gap.

## Scope

- Date: `2026-06-13`
- Store: `ACMEWEAR`
- Sold row: `order_id=956184861`, `sku_key=LINE-31-TS`, `net_rev_kzt=9179.0`
- Source refresh: `ads_source_refresh_runs.run_id=agent12-ads-source-acmewear-2026-06-13`
- Production DB mutation: none

## Change

- Updated `docs/validation/ADS_SOURCE_GAP_QUARANTINE_CONTRACT.md` with the exact approved tuple.
- Updated `config/ads_source_gap_quarantine.yaml` with the same tuple.
- Added a regression guard that requires repo quarantine config rows to be exact, non-blank, non-wildcard tuples.

## Evidence

- Pre-change ads offer coverage failed with `failing_month_store_pairs=1`, `spend_reality_fail_pairs=0`, `unmapped_positive_spend_ads=0`.
- Source readback showed `ads_campaign_product_daily` had zero `LINE-31-TS` rows for `2026-06-13` / `ACMEWEAR`.
- Source run readback showed `agent12-ads-source-acmewear-2026-06-13` was `SUCCESS`, `product_rows_total=4`, and notes included `no_fake_zero_spend=true`.
- Post-change ads coverage report: `exports/validation/ads_beli31ts_quarantine_20260613/ads_offer_universe_report.json`
- Post-change spend reality report: `exports/validation/ads_beli31ts_spend_reality_quarantine_20260613/ads_spend_reality_report.json`

## Validation

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_validate_ads_offer_universe_coverage.py tests/test_validate_ads_spend_reality.py` -> `18 passed`
- `.venv/bin/python scripts/validate_ads_offer_universe_coverage.py --db-path db/app.db --as-of 2026-06-13 --start 2026-06-13 --end 2026-06-13 --strict --output-dir exports/validation/ads_beli31ts_quarantine_20260613` -> `status=PASS`
- `.venv/bin/python scripts/validate_ads_spend_reality.py --db-path db/app.db --as-of 2026-06-13 --start 2026-06-13 --end 2026-06-13 --strict --gap-quarantine-config config/ads_source_gap_quarantine.yaml --output-dir exports/validation/ads_beli31ts_spend_reality_quarantine_20260613` -> `status=PASS`
- `.venv/bin/python scripts/validate_ads_sidecar_readiness.py --db db/app.db --as-of 2026-06-13 --readiness-mode live --strict` -> `status=PASS`
- `scripts/check_no_db_tracked.sh` -> `DB guard OK`

## Retained Blockers

- `src_ab_db_stock_truth` remains `STALE`.
- `src_facebook_ads_external_ads` remains `BLOCKED`.
- C3 gates still block on `ads_source_truth`, `source_freshness`, and `stock_source_truth`.
