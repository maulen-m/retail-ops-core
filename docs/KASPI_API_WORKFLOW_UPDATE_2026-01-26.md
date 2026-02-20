# Kaspi API Workflow Update — 2026-01-26

## What changed
- API client now supports and uses: `deliveryType`, `signatureRequired`, and `include[orders]=user` filters.
- Order sync stores a wider set of API attributes into `fact_orders_kaspi` (delivery/payment metadata, planned/actual dates, and customer fields).
- New migration script: `scripts/migrate_014_kaspi_api_fields.py`.

## New fields captured (fact_orders_kaspi)
- Status details: `kaspi_status_detail`
- Planning & actuals: `planned_delivery_date`, `courier_transmission_planning_date`, `courier_transmission_date`, `actual_shipment_date`
- Delivery/payment: `delivery_mode`, `payment_mode`, `signature_required`, `credit_term`, `pre_order`
- Bank & reservation dates: `approved_by_bank_date`, `reservation_date`
- Delivery economics: `delivery_cost`, `delivery_cost_for_seller`, `delivery_address`
- Compliance / logistics: `is_imei_required`, `express`, `returned_to_warehouse`
- Product metadata: `category`
- Customer: `customer_first_name`, `customer_last_name`, `customer_phone`

## How to use it
- **Operational filters**: For exports like on‑delivery, the API request now filters by delivery type and signature requirement before processing.
- **Customer contact**: Customer phone is now stored in DB for downstream CRM checks (when returned by API).
- **Delivery analytics**: Planned vs actual dates enable SLA measurement and carrier delay tracking.
- **Returns risk**: `returned_to_warehouse` and `express` allow profiling risky or high-cost flows.
- **Cashflow timing**: `approved_by_bank_date` and `reservation_date` can help refine payment timing models.

## Follow‑ups (optional)
- Add ETL transforms for delivery SLA reporting.
- Build dashboards for overdue handovers (planned vs courierTransmissionDate).
- Expand customer data normalization into CRM if needed.

## Files touched
- `core/integrations/kaspi_api_client.py`
- `core/sync/order_sync_engine.py`
- `scripts/export_api_orders.py`
- `scripts/export_on_delivery_orders.py`
- `scripts/export_on_delivery_with_econ.py`
- `scripts/migrate_014_kaspi_api_fields.py`
- `docs/KASPI_API_INTEGRATION.md`
