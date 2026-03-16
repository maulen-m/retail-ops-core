# SHR Payment Unblock Execution Status

Date: `2026-03-12`
Scope: deterministic treasury unblock execution for `SHR` before `2026-03-20 00:00`
Current status: `SHR_PAYMENT_BLOCKED`

## Executive summary

The unblock execution did not clear the blocker.

The treasury answer is still:

- maximum safe actual `SHR` payment before `2026-03-20 00:00` = `0 KZT`

That remains true for two deterministic reasons:

1. there is still no fresh account-level liquid cash snapshot newer than `2026-03-02 14:41 GMT+5`
2. there is still no exact dated payable truth for the live unpaid `SHR` parts:
   - `PO-5.1`
   - `PO-5.2`
   - `PO-6.0a`
   - `PO-6.0b`

## What was refreshed successfully

The execution did confirm the current live unpaid `SHR` part universe and the canonical unpaid total for this decision:

- `PO-5.1 = 2,516,280.00 KZT`
- `PO-5.2 = 9,305,790.00 KZT`
- `PO-6.0a = 234,000.00 KZT`
- `PO-6.0b = 911,040.00 KZT`
- canonical live unpaid total = `12,967,110.00 KZT`

It also restated the stale-artifact mismatch correctly:

- stale `PO_PAYMENT_STATUS.md` total = `10,665,512.50 KZT`
- live unpaid `po_part` total = `12,967,110.00 KZT`
- net mismatch = `2,301,597.50 KZT`

The right decision basis remains the live unpaid `po_part` total, not the older PO-payment artifact.

## Exact blocker state

### 1. Fresh cash truth is still missing

The latest actual balance anchor still available in repo truth is:

- `2026-03-02 14:41 GMT+5`

Latest liquid cash equivalent at that timestamp:

- `463,955.68 KZT`

Standalone required surplus buffer:

- `500,000.00 KZT`

That means the latest actual liquid cash truth is already below the required standalone buffer before any `SHR` payment is considered.

### 2. Exact `SHR` due dates are still missing

Current `po_header` truth still has no usable payment dates for the live unpaid `SHR` exposure:

- `payment_date_cny = null`
- `payment_date_cargo = null`

for the parent POs that own the unpaid parts:

- `PO-5`
- `PO-6`

There is still no exact part-grain dated schedule through `2026-03-20` for:

- `PO-5.1`
- `PO-5.2`
- `PO-6.0a`
- `PO-6.0b`

### 3. Actual deadline cash path is still not buildable

Because both the fresh balance anchor and exact dated obligations are missing, the deadline cash path through `2026-03-20` cannot be rebuilt from actual truth.

Model and proxy rows still exist for planning, but they do not authorize payment.

## What fully clears the blocker

The blocker is fully cleared only when all of the following exist together:

1. one fresh account-level liquid cash snapshot captured now
2. one short balance reconciliation note tied to that timestamp
3. one exact dated part-grain payable schedule through `2026-03-20` for:
   - `PO-5.1`
   - `PO-5.2`
   - `PO-6.0a`
   - `PO-6.0b`
4. one canonical unpaid `SHR` total note using the live `po_part` basis
5. one refreshed day-by-day deadline cash path rebuilt from that truth set

Only after those five pieces exist can treasury recompute:

- base tranche
- conservative tranche
- actual decision-safe tranche

## Immediate next action

Capture a fresh account-level balance snapshot now, then attach exact dated payable truth for `PO-5.1`, `PO-5.2`, `PO-6.0a`, and `PO-6.0b`; until both exist, keep `SHR_PAYMENT_BLOCKED`.
