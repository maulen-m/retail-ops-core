# Day Complete Contract (Phase 6)

Purpose: single owner of “day complete” definition for operational data readiness.
Scope: Kaspi orders that are eligible to ship on or before the cutoff date.

Source of truth:
- Orders table: `fact_orders_kaspi` (db/app.db)
- Daily SOP: `docs/DAILY_SOP.md` (MY_SIZE required before shipping)

## Definition (machine-actionable)
A day is **complete** for `cutoff_date` when **all** eligible orders meet the size requirement.

### Eligible orders (must have size)
An order is eligible when ALL are true:
- `planned_shipment_date` is not null
- `planned_shipment_date` <= `cutoff_date`
- Status indicates shipment readiness or completion
- Order has a line item identifier (`sku_id` or `kaspi_offer_name` present)

Status rule (either):
- `internal_status` in {`READY`, `SHIPPED`, `COMPLETED`}
- OR `kaspi_status` in {`KASPI_DELIVERY`, `DELIVERY`, `COMPLETED`, `ARCHIVE`,
  `Ожидает передачи курьеру`, `Доставляется`, `Завершен`}

### Size requirement (must be present)
For each eligible order, at least one of these must be non-empty:
- `assigned_size`
- `my_size`

If both are empty, the order is a violation.

## Validator output (required)
The validator must report:
- `cutoff_date`
- `eligible_orders` count
- `violations` count
- List of violating orders: `order_id`, `sku_id`, `store_code`, `planned_shipment_date`, `internal_status`, `kaspi_status`

## Provisional mode (operational rule)
If day_complete is **red**:
- Dashboard generation is allowed.
- Exports/writes are blocked (supplier export, capital-impacting outputs).
- Console must print: `PROVISIONAL: sizes pending; exports blocked.`

## Gate behavior
- `scripts/validate_day_complete.py` exits non-zero on any violation.
- `scripts/run_end_of_day.py --verbose` must show pass/fail explicitly.

## Update protocol
1) If status logic changes, update this contract first.
2) Keep validator output deterministic and explicit.
3) No silent overrides of violations.
