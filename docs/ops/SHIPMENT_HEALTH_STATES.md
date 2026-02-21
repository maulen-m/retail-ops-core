# Shipment Health States

Purpose: classify shipping/waybill runs deterministically and prevent silent partial success.

## Health codes

### `ship_orders_api.py`
- `ok`: shipped orders with no skips/errors. Exit `0`.
- `no_pending`: nothing pending. Exit `0`.
- `partial`: mixed shipped/skipped and no explicit API error. Exit `1`.
- `api_error`: one or more shipping errors. Exit `1`.

### `download_waybills_api.py`
- `ok`: downloaded/existing waybills and no errors/missing/invalid PDF. Exit `0`.
- `no_targets`: no target waybills. Exit `0`.
- `delayed`: all targets missing waybill URL. Exit `1`.
- `partial`: some downloaded but some missing. Exit `1`.
- `invalid_pdf`: payload validation failed. Exit `1`.
- `api_error`: API call/path error. Exit `1`.

## Contract
Classification is centralized in `core/ops/shipment_health.py` and must be used by shipping/waybill entrypoints.
