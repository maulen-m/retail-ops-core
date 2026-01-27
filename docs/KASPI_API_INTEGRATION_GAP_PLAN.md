# Kaspi API Integration Gap Plan (2026-01-27)

## Purpose

Document the remaining gaps between the official Kaspi API Q&A docs and the current workflow, and propose a low‑risk integration path that preserves current stability.

See also: `docs/api_docs/api_gap_opprotunity_examples.md` (examples of value unlocked).

## Inputs

Reviewed formatted docs in `docs/api_docs/formatted/` (Q1, Q2, Q4–Q11).

## Gaps vs current workflow

### Missing endpoints (read/write)

- `GET /orderentries/{id}` (Q8) — line‑item detail: unitType, weight, basePrice, deliveryCost, entryNumber, minAllowedWeight, category, isImeiRequired.
- `GET /orderentries/{id}/product` (Q7) — masterproduct details per line.
- `GET /masterproducts/{id}/merchantProduct` (Q11) — seller product code/name/brand.
- `GET /pointofservices/{id}` (Q9) — warehouse address + geo.
- `PUT /orderPartialCancel/{orderId}` (Q10) — partial cancel / adjust weight or quantity.

### Partial coverage

- Q2 filter by `code` exists via `get_order()` only (not exposed as a list filter in `list_orders()` for bulk workflows).

### Order attributes not stored

- `pickupPointId`, `isKaspiDelivery`
- `customer.id`, `customer.name` (only first/last/phone stored today)

### Line‑item data missing

Currently we store only order‑level records in `fact_orders_kaspi`. Line‑item fields (unitType, minAllowedWeight, weight, basePrice, deliveryCost, entryNumber, category per line, isImeiRequired per line) are not persisted. This also means `totalPrice` is used as a proxy for unit price with quantity=1, which misrepresents multi‑line orders.

## Low‑risk integration plan

1) **Add read‑only endpoints** in `KaspiAPIClient` for Q7/Q8/Q9/Q11. Keep current sync unchanged.
2) **Add cache tables (dim style)** to reduce repeated calls:
   - `dim_point_of_service` (pointofservices id → displayName/address/geo)
   - `dim_masterproduct` (masterproduct id → name/category/manufacturer)
   - `dim_merchantproduct` (masterproduct id → merchant code/name/brand)
3) **Create line‑item table** `fact_order_entries_kaspi` for order‑entry records:
   - order_entry_id, order_id, qty, base_price, total_price, weight, unit_type, delivery_cost, entry_number, category, is_imei_required, masterproduct_id, point_of_service_id, etc.
   - Keep `fact_orders_kaspi` unchanged to avoid breaking existing dashboards.
4) **Optional enrichment stage**, gated by CLI flag or env var (default OFF):
   - Fetch entries only for new/changed orders (or last N days).
   - Fail‑open (log + continue) to avoid breaking sync runs.
   - Rate‑limit and cache to avoid API load spikes.
5) **SKU mapping fallback** (safe):
   - Use current SKU extraction first.
   - If missing, use `merchantProduct.code` or `merchantProduct.name`.
   - Record unmapped cases in missing‑master‑data report.

## Safety / rollout guardrails

- New functionality defaults to OFF (feature flag).
- Store cache tables to reduce repeated calls.
- Fail‑open: if enrichment fails, continue with base order data.
- Incremental rollout by store (e.g., UNIVERSAL first).

## Suggested implementation touchpoints

- `core/integrations/kaspi_api_client.py` (add endpoints)
- `core/sync/order_sync_engine.py` (optional enrichment step + new fields)
- New migration script for `fact_order_entries_kaspi` + dim caches
- `docs/KASPI_API_INTEGRATION.md` (add link + summary)

## Open decisions

- Feature flag name and default value
- Cache invalidation strategy for masterproduct/point‑of‑service
- Whether to backfill historical order entries or only new orders
