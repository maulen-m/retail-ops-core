# Profit After Ads Contract

Purpose: publish `profit_after_ads` only when ads sidecar source contract is green.

## Requirements
- Ads source must pass `core.ads.sidecar_contract.validate_ads_source`.
- If ads source is unavailable/stale/future-skewed, ads metrics are `N/A` and `profit_after_ads` is `N/A`.
- Numeric `profit_after_ads` publication requires `ads.status == available`.

## Builder

```bash
python3 scripts/build_profit_after_ads.py --as-of 2026-02-21 --days 7
```

## Integration
`generate_business_insides.py` uses this contract through `compute_sales_metrics` and surfaces ads status/reason in Data Quality.
