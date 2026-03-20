# SHIPPED_TRUTH_CRM_WAYBILL_CONTRACT

## Purpose
Prevent shipped-order undercount/false-green regressions by locking one shipped truth definition and enforcing deterministic API↔CRM↔Waybill cross-checks.

## Canonical Shipped Definitions
- `shipped_secondary`:
  - order has non-empty `courierTransmissionDate` (Kaspi API `kaspiDelivery.courierTransmissionDate`) for that day.
  - includes orders that may later become cancelled/returned.
- `shipped_primary` (decision-grade):
  - `shipped_secondary` **minus** orders whose final lifecycle is cancelled/returned.
  - practical rule: `courierTransmissionDate` exists and final status is not `CANCELLED`/`RETURNED`.

## Required API Fetch Logic (Historical + Daily)
- For shipped parity checks, API fetch MUST include both states:
  - `KASPI_DELIVERY`
  - `ARCHIVE`
- If list-order state buckets miss a CRM-expected shipped order, validator must run order-code detail fallback (`get_order`) and classify by `courierTransmissionDate` + final status.
- For historical ranges, fetch must be windowed to Kaspi API limits (`<=14` days per `creationDate` span).
- `KASPI_DELIVERY`-only shipped counting is explicitly forbidden for historical parity checks.
- Reason: many shipped orders move to archive quickly; filtering only `KASPI_DELIVERY` causes undercount.

## CRM + Waybill Cross-Check Contract
Per day/store:
- Build `crm_all_day_set`: CRM rows where planned shipping date equals day.
- Build `crm_expected_ship_set`: `crm_all_day_set` excluding cancelled/returned rows.
  - for orders present in API shipped universe (`api_secondary_set`), API final cancellation status is authoritative.
  - for orders outside API shipped universe, DB status is preferred with CRM status text fallback.
  - rows still `NEW/ACCEPTED` without shipped marker are excluded from `crm_expected_ship_set` (treated as not-yet-shipped).
- Build `waybill_day_set`: PDF order IDs from `excel_ui/Archive/input_<day>_*/waybills` (latest run for that day).
  - supplement with current cache `excel_ui/ActiveOrders/waybills` to avoid false missing flags from archive-copy lag.
  - if PDF is still missing, validator may resolve coverage via API detail fallback when a same-day order has non-empty waybill URL/number.
- Build cancel-drift sets on shipped-universe only:
  - `api_cancelled_shipped_set = api_secondary_set - api_primary_set`
  - `crm_cancelled_shipped_set = (crm_all_day_set - crm_expected_ship_set) ∩ api_secondary_set`
  - planned-day cancellations not present in `api_secondary_set` are excluded from drift math.
- Compare:
  - `api_primary_set` ↔ `crm_expected_ship_set` (hard parity on completed days)
  - apply adjacent-day normalization before hard mismatch: if an order appears in the opposite set within `±1` day (`--date-shift-tolerance-days`), classify as `SHIFTED` (reported, not hard mismatch)
  - `crm_expected_ship_set` coverage in `waybill_day_set` (hard parity on completed days when archive run exists)
  - `|api_cancelled_shipped_set|` vs `|crm_cancelled_shipped_set|` drift (hard threshold on completed days)

## Thresholds / Margins
- Primary mismatch threshold: default `0.0%` (no mismatch).
- Waybill missing threshold: default `2.0%`.
- Cancellation drift alert (`API cancelled shipped count` vs `CRM cancelled shipped count`): `2.0%`.
- API creation-date lookback for shipped parity fetch: default `120` days (`--api-creation-lookback-days`), to avoid undercount from overdue shipments created long before ship day.

## Day Completeness Rule
- Completed days: hard-fail applies.
- Volatility window: last `14` days are provisional by default (`--volatility-days`), to avoid false-red while returns/cancellations settle.
- Today: always provisional unless explicitly overridden.

## Validator
- Script: `scripts/validate_shipped_truth_crm_waybill.py`
- Command example:

```bash
python3 scripts/validate_shipped_truth_crm_waybill.py \
  --since 2024-06-06 \
  --until 2026-03-02 \
  --strict
```

## Fail-Closed Conditions
- Any completed day/store where `api_primary` and `crm_expected_ship_set` mismatch above threshold.
- Any completed day/store with waybill coverage gap above threshold (when day archive folder exists).
- Any completed day/store where API and CRM cancellation counts drift above threshold.
- Any run that computes shipped truth from `KASPI_DELIVERY` only.
- Any run without configured API tokens for all stores (`KASPI_TOKEN_*`), when strict validation is requested.
