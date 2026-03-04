# OWNER_PNL_PUBLICATION_CONTRACT

## Purpose
Define fail-closed publication rules for owner-facing monthly PnL surfaces.

This contract exists to prevent capital decisions on false-green profitability.

## Canonical Inputs
- `view_sales_line_truth` / `view_sales_daily_truth` (DB operational truth)
- `exports/sales_archive_statusdate_mapped/*/ArchiveSales_ALL_STORES_statusdate_mapped.csv` (status-date archive parity source)
- `ads_spend_sidecar_daily` + `core/ads/sidecar_contract.py` (ads freshness + mapping coverage)

## Publication Surface
- `exports/owner_pnl/<as_of>/OWNER_PNL.json`
- `exports/owner_pnl/<as_of>/OWNER_PNL.md`

Required row fields:
- `sale_month`
- `decision_grade` (boolean)
- `statusdate_coverage_pct`
- `net_rev_kzt`
- `cogs_kzt`
- `ads_kzt`
- `profit_after_ads_kzt`
- `locked_reason` (when values are locked)

## Decision-Grade Rule
A month is publishable (`decision_grade=true`) only when:
1. all month/store parity rows are decision-grade per `SALES_ECONOMICS_TRUTH_CONTRACT`,
2. monthly economics parity is PASS,
3. ads readiness is PASS (`validate_ads_sidecar_readiness --strict`).

If any condition is false, profitability values must be locked (`N/A`) and `locked_reason` must be set.

## Ads Readiness Rule
Ads readiness is PASS only when:
- ads source DB is fresh (`AB_ADS_DB_MAX_AGE_HOURS`),
- ads sidecar table exists and is readable,
- mapping coverage is >= `AB_ADS_MAPPING_MIN_COVERAGE_PCT` when spend >= `AB_ADS_MAPPING_MIN_TOTAL_COST_KZT`.

## Fail-Closed Behavior
- `build_owner_pnl_report.py --strict` exits non-zero when:
  - parity is FAIL, or
  - ads readiness is FAIL, or
  - ads sidecar table is missing.

## Change Protocol
1. Formula changes: update `docs/inventory/Master_Inventory_Rules_v8.md` first.
2. Then update `docs/validation/SALES_ECONOMICS_TRUTH_CONTRACT.md`.
3. Then update this contract and code/tests.
