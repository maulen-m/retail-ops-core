# Ads Effective Cost Policy

Purpose: apply transparent multipliers to ads spend before profit-after-ads publication.

## Activation
Set `AB_ADS_EFFECTIVE_COST_MODE=1` to enable policy-adjusted ads cost.

Policy file resolution:
1. `AB_ADS_EFFECTIVE_COST_POLICY_PATH`
2. `config/kaspi_ads_cost_adjustments.yaml`

## Contract
- If effective-cost mode is enabled and policy file is missing/invalid, ads status becomes `unavailable` and profit-after-ads outputs are `N/A`.
- Multipliers are applied by date with this precedence:
  - start with `default_multiplier`
  - apply matching `date_overrides` rows in order

## Schema
```yaml
default_multiplier: 1.0
date_overrides:
  - start_date: 2026-02-01
    end_date: 2026-02-15
    multiplier: 1.15
```

Use this policy only for analytics; it does not mutate raw ads sidecar storage.
