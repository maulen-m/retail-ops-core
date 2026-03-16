# SHR Payment Blocker Full Unblock Plan

Date: `2026-03-12`
Scope: deterministic treasury clearance for `SHR` payment before `2026-03-20 00:00`
Current status: `SHR_PAYMENT_BLOCKED`

## Executive summary

The blocker is still real and still deterministic.

No safe `SHR` payment can be authorized yet because:

1. the latest actual liquid-cash snapshot available in repo truth is still `2026-03-02 14:41 GMT+5`
2. that snapshot totals only `463,955.68 KZT`, already below the required standalone `500,000 KZT` surplus buffer
3. exact due dates are still missing for the live unpaid `SHR` parts:
   - `PO-5.1`
   - `PO-5.2`
   - `PO-6.0a`
   - `PO-6.0b`
4. the deadline cash path cannot be rebuilt from actual truth until both fresh balances and exact dated obligations exist

The current decision-safe tranche therefore remains:

- `0 KZT`

## What fully fixes the blocker

The blocker is fully cleared only when all four truth gaps below are closed.

### 1. Refresh actual liquid cash now

Required output:

- one fresh account-level balance snapshot, timestamped later than the current decision time
- one row per liquid account
- one total liquid cash equivalent in KZT

Minimum account scope:

- `UNIVERSAL.kaspi_gold`
- `UNIVERSAL.kaspi_pay`
- `UNIVERSAL.bcc`
- `UNIVERSAL.freedom`
- `UNIVERSAL.cash_kzt`
- `UNIVERSAL.cash_usd`
- `UNIVERSAL.cash_rub`
- `UNIVERSAL.binance_usdt`
- `STOREB.kaspi_gold`
- `STOREB.kaspi_pay`

Acceptance rule:

- if fresh total liquid cash is still below `500,000 KZT`, the answer stays `0 KZT` immediately

### 2. Produce exact dated `SHR` payable truth at part grain

Required output:

- one schedule through `2026-03-20` with these columns:
  - `po_part_id`
  - `po_id`
  - `due_date`
  - `due_amount_kzt`
  - `truth_source`
  - `source_updated_at`

Required rows:

- `PO-5.1`
- `PO-5.2`
- `PO-6.0a`
- `PO-6.0b`

Accepted truth:

- supplier-confirmed due date
- operator-approved dated payable schedule recorded into the receiving-side truth chain
- transfer-ledger-linked dated obligation that can be matched directly to the live unpaid part balance

Not accepted:

- null dates
- `SUPP_A` proxy schedule
- PO-level remainder guesses that cannot allocate to parts

Acceptance rule:

- every unpaid live `SHR` part due before `2026-03-20` must have an exact dated amount

### 3. Lock one canonical unpaid `SHR` total

Current arithmetic:

- live unpaid `SHR` parts in `po_part`: `12,967,110.00 KZT`
- stale `PO_PAYMENT_STATUS.md` total: `10,665,512.50 KZT`
- net mismatch: `2,301,597.50 KZT`

What the mismatch means:

- the stale PO-payment artifact still carries old PO-level FX-linked balances
- it also includes obligations outside the current unpaid part decision set, especially `PO-4` and `Line52_PO-9`
- the live `po_part` view is the correct basis for the current unpaid part universe, but it still lacks dated due truth

Required output:

- one short reconciliation note stating the canonical treasury decision total

Canonical total to use once dated truth is added:

- `12,967,110.00 KZT`

### 4. Rebuild the deadline cash path from refreshed truth

Once steps 1 to 3 are done, rebuild the path through `2026-03-20` using:

- refreshed actual liquid cash anchor
- exact OPEX commitments
- contract base floor
- contract conservative floor
- extra `500,000 KZT` surplus buffer
- exact dated `SHR` part obligations

Required outputs:

- one day-by-day close-cash table through `2026-03-20`
- base tranche
- conservative tranche
- actual decision-safe tranche

Decision formula:

- `base tranche = min_close_base_path - (base_floor + 500,000)`
- `conservative tranche = min_close_conservative_path - (conservative_floor + 500,000)`
- `actual decision-safe tranche = min(actual fresh-cash path after exact obligations) - required threshold`
- clamp negative results to `0`

## Smallest truthful unblock sequence

1. Capture a fresh balance snapshot now across all liquid accounts.
2. Publish a short balance reconciliation note tied to that timestamp.
3. Obtain exact due dates and amounts for `PO-5.1`, `PO-5.2`, `PO-6.0a`, and `PO-6.0b`.
4. Publish one canonical `SHR` unpaid total note using the live `po_part` basis.
5. Rebuild the deadline cash path with those exact obligations.
6. Recompute base, conservative, and actual decision-safe tranches.
7. Authorize payment only if the actual decision-safe tranche is positive.

## Fastest way to clear it in practice

The fastest honest route is:

1. treasury operator captures fresh balances immediately
2. purchasing / supplier owner provides explicit dated settlement plan for `PO-5` and `PO-6`
3. finance reconciles those dates to the live unpaid part amounts
4. treasury reruns the tranche calculation once the dated schedule is exact

If any one of those pieces is still missing, the blocker is not cleared.

## What will not clear the blocker

- using the stale `2026-03-02` balance anchor
- treating model cashflow rows as actual cash truth
- adopting the `SUPP_A` proxy as final `SHR` due truth
- ignoring the extra `500,000 KZT` surplus requirement
- paying against PO-level remainder math without part-level dated obligations

## Full-clear acceptance criteria

The blocker is fully fixed only when all of the following are true:

- a fresh actual balance snapshot exists now
- that fresh snapshot is auditable by account
- exact due dates exist for all four unpaid live `SHR` parts through `2026-03-20`
- one canonical unpaid `SHR` total is documented
- the deadline cash path is recomputed from refreshed truth
- the actual decision-safe tranche is greater than `0 KZT`

Until then, the correct treasury state remains:

- `SHR_PAYMENT_BLOCKED`
