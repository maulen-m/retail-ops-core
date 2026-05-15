# OWNER_PNL_PUBLICATION_CONTRACT

## Purpose
Define fail-closed publication rules for owner-facing monthly PnL surfaces.

This contract exists to prevent capital decisions on false-green profitability.

## Canonical Inputs
- `view_sales_line_truth` / `view_sales_daily_truth` (DB operational truth)
- `exports/sales_archive_statusdate_mapped/*/ArchiveSales_ALL_STORES_statusdate_mapped.csv` (status-date archive parity source)
- `docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md` (candidate WebUI archive promotion contract)
- `docs/validation/WEBUI_CRM_CHRONOLOGY_AUTHORITY_CONTRACT.md` (fallback chronology anchor when WebUI day parity is not authority-backed)
- `ads_campaign_product_daily` + `ads_source_refresh_runs` through `core/ads/canonical_truth.py` (canonical ads truth, refresh range, and mapping coverage)

## Publication Surface
- `exports/owner_pnl/<as_of>/OWNER_PNL.json`
- `exports/owner_pnl/<as_of>/OWNER_PNL.md`
- `exports/owner_pnl/<as_of>/OWNER_PNL_ASCII.txt`

Required row fields:
- `sale_month`
- `decision_grade` (boolean)
- `statusdate_coverage_pct`
- `net_rev_kzt`
- `cogs_kzt`
- `ads_kzt`
- `profit_after_ads_kzt`
- `opex_kzt`
- `profit_after_ads_and_opex_kzt`
- `locked_reason` (when values are locked)

## Decision-Grade Rule
A month is publishable (`decision_grade=true`) only when:
1. all month/store parity rows are decision-grade per `SALES_ECONOMICS_TRUTH_CONTRACT`,
2. monthly economics parity is PASS,
3. ads readiness is PASS (`validate_ads_sidecar_readiness --strict`),
4. when `truth_source=webui_archive`, the WebUI archive promotion contract is green for the proving window,
5. when the active chronology contract is `CRM_REMAINS_CHRONOLOGY_AUTHORITY`, workbook chronology anchor validation is also PASS.

If any condition is false, profitability values must be locked (`N/A`) and `locked_reason` must be set.

## OPEX Readiness Rule
OPEX readiness is validated by `scripts/validate_opex_readiness.py`.

`profit_after_ads_and_opex_kzt` is publishable only when:
- month is decision-grade,
- ads readiness is PASS,
- opex readiness is PASS.

If OPEX readiness is not PASS, `profit_after_ads_and_opex_kzt` and `opex_kzt` must be locked (`N/A`).

## Ads Readiness Rule
Ads readiness is PASS only when:
- canonical ads tables exist and are readable,
- `ads_campaign_product_daily` covers the publication as-of date,
- `ads_source_refresh_runs` has successful refresh coverage for the publication window,
- mapping coverage is >= `AB_ADS_MAPPING_MIN_COVERAGE_PCT` when spend >= `AB_ADS_MAPPING_MIN_TOTAL_COST_KZT`.

## Fail-Closed Behavior
- `build_owner_pnl_report.py --strict` exits non-zero when:
  - parity is FAIL, or
  - ads readiness is FAIL, or
  - canonical ads tables are missing, or
  - `truth_source=webui_archive` and required WebUI promotion artifacts are red/missing, or
  - `truth_source=webui_archive` and workbook chronology anchor evidence is required but red/missing.
- `build_owner_pnl_report.py --strict --require-opex-for-net-publication` exits non-zero when:
  - opex readiness is FAIL, or
  - OPEX table is missing.

## Change Protocol
1. Formula changes: update `docs/inventory/Master_Inventory_Rules_v9.md` first.
2. Then update `docs/validation/SALES_ECONOMICS_TRUTH_CONTRACT.md`.
3. Then update this contract and code/tests.
