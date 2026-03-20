# Ads Source Gap Quarantine Contract

## Purpose
- Allow a narrow, explicit quarantine for a proven missing external-marketing source row.
- Prevent broad suppression of unrelated ads coverage failures.
- Keep every quarantine keyed to an exact sold-order lineage tuple.

## Allowed Scope
- A quarantine must match all of:
  - `order_id`
  - `sale_date`
  - `store_code`
  - `sku_key`
- If any field differs, the quarantine does not apply.
- Quarantine removes the exact sold row from ads coverage expectation. It does not fabricate ads spend.

## Current Approved Quarantine
- `order_id=776936815`
- `sale_date=2026-01-09`
- `store_code=ACMEWEAR`
- `sku_key=CL_NEW-CLO2_MEN_HUS_GREEN`
- reason: refreshed Jan-Feb 2026 marketing source has no HUS evidence in `campaign_product_daily_current` or `campaign_product_daily_history`

## Evidence Standard
- The source refresh for the relevant period/store must be fresh and successful.
- Recovery attempts must show no matching source evidence.
- The affected row count must stay narrow and explicit.

## Change Management
- Update this contract first.
- Then update `config/ads_source_gap_quarantine.yaml`.
- Then update tests and validators.
- Broad store/month quarantine is not allowed.
