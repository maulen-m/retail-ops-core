# Universal Assemble X-Merchant-Uid Experiment

## Problem
Universal store assemble requests return HTTP success but orders remain in
`KASPI_DELIVERY / ACCEPTED_BY_MERCHANT / assembled=false`, so waybills are
missing until manual assembly in Kaspi Seller UI.

## Environment
- Date: 2026-01-19 (diagnostics timestamp 20260119_163554)
- Store: UNIVERSAL (control: ACMEWEAR)
- API base: `https://kaspi.kz/shop/api/v2/`
- Client commit: `d7a112b`

## Client change
We added optional support for:
```
X-Merchant-Uid: <VALUE>
```
Header usage is OFF by default and can be enabled via:
- `KASPI_SEND_MERCHANT_UID=1`
- `KASPI_MERCHANT_UID_OVERRIDE=<VALUE>` (or per-store config/env)

No tokens are logged; request headers in evidence are redacted for `Authorization`
and `X-Auth-Token`.

## Experiment design
A/B for the same sample orders:

1) Run without `X-Merchant-Uid`
2) Run with `X-Merchant-Uid`

Orders are selected from **pending assembly** for the target date.

Script:
```
python scripts/debug_kaspi_merchant_uid.py \
  --store UNIVERSAL \
  --date 2026-01-15 \
  --merchant-uid <VALUE> \
  --control-store ACMEWEAR
```

## Evidence files
Stored under `exports/diagnostics/`:
- `xmerchantuid_20260119_163554_requests.jsonl`
- `xmerchantuid_20260119_163554_results.csv`
- `xmerchantuid_20260119_163554_summary.md`

## Results
- Sample size:
  - Universal: 10 orders (pending assembly, 2026-01-19)
  - AcmeWear: 4 orders (pending assembly, 2026-01-19)
- Assemble success (assembled/status/waybill observed):
  - Universal without header: 1 / 10
  - Universal with header: 4 / 10
  - AcmeWear without header: 1 / 4
  - AcmeWear with header: 4 / 4
- HTTP status distribution:
  - Universal without header: 204×8, 200×2
  - Universal with header: 201×8, 200×2
  - AcmeWear without header: 201×4
  - AcmeWear with header: 201×4
- Response headers (request-id/correlation-id):
  - No request-id style header captured in responses (assemble_request_id empty in CSV).

## Ask to Kaspi
1) Confirm required format/value for `X-Merchant-Uid`.
2) Explain why API returns HTTP success but does not transition state for Universal.
3) Use provided timestamps + order codes + request IDs to locate server-side logs.
