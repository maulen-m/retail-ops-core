# SHR Payment Blocker Full Clearance

Date: `2026-03-12`
Scope: deterministic treasury decision support for `SHR` before `2026-03-20 00:00`
Status: `BLOCKED`

## Executive summary

The blocker is not a single missing number. It is a four-part truth gap:

1. The latest account-level liquid cash anchor is stale and already below the required standalone `500,000 KZT` surplus buffer.
2. The `SHR` payable schedule has no exact due dates in current `po_header` truth.
3. `SHR` exposure is not fully reconciled across the PO-payment artifact and live `po_part` truth.
4. The current deadline cash path is modelled, not refreshed from a new actual-balance anchor plus exact `SHR` due dates.

Because of that, the current decision-safe maximum payment remains `0 KZT`.

## Exact blocker causes

### 1. Fresh liquid cash truth is missing

- Latest explicit account snapshot found: `2026-03-02 14:41 GMT+5`
- Latest liquid cash equivalent from that snapshot: `463,955.68 KZT`
- Required standalone surplus buffer: `500,000.00 KZT`
- Result: the most recent actual balance truth is already below the required buffer before any `SHR` payment.

This alone is enough to block an actual payment decision. Even if the model forecast looks positive later, the question asks for what is actually safe, not what a stale forecast would permit.

### 2. `SHR` due-date truth is missing

Current `po_header` rows for `SHR` show:

- `payment_date_cny = null`
- `payment_date_cargo = null`

for:

- `PO-4`
- `PO-4.1`
- `PO-4.2`
- `PO-4.3`
- `PO-5`
- `PO-6`
- `Line52_PO-9`

The live unpaid exposure sits at part grain in `po_part`:

- `PO-5.1 = 2,516,280.00 KZT`
- `PO-5.2 = 9,305,790.00 KZT`
- `PO-6.0a = 234,000.00 KZT`
- `PO-6.0b = 911,040.00 KZT`

but there is no exact dated payable truth for those parts before `2026-03-20`.

### 3. Exposure truth is inconsistent

Two current views disagree:

- `PO_PAYMENT_STATUS.md` unpaid positive balance total: `10,665,512.50 KZT`
- live `po_part` unpaid base total for `SHR`: `12,967,110.00 KZT`

Gap: `2,301,597.50 KZT`

Until that difference is explained, the treasury question is not stable enough for an exact payment authorization.

### 4. Commitment and deadline path truth is not decision-safe

The current deadline cash path through `2026-03-20` depends on:

- `FORECAST_MODEL` calendar rows
- inferred `SUPP_A` proxy timing in `po_payment_plan.csv`
- stale PO-level commitment rows that still mention already-paid `PO-4.*`

That is adequate for exploratory planning, but not for a deterministic treasury release.

## What fully fixes the blocker

The blocker is fully cleared only when all four layers below are completed.

### A. Refresh actual liquid cash truth now

Required output:

- one fresh account-level balance snapshot with timestamp newer than the decision time
- full liquid cash by account in KZT equivalent
- no hidden carry-forward from the `2026-03-02` snapshot

Minimum artifact set:

- refreshed manual balance snapshot or statement-backed balance artifact
- refreshed cash reconciliation note tying the snapshot to the current cash truth workflow

Pass condition:

- latest actual total is known now, by account, and auditable

Fail condition:

- if the newest balance anchor is still below `500,000 KZT`, the answer remains `0 KZT` immediately

### B. Produce explicit `SHR` due-date truth

Required output:

- one dated payable schedule through `2026-03-20` for:
  - `PO-5.1`
  - `PO-5.2`
  - `PO-6.0a`
  - `PO-6.0b`

Minimum columns:

- `po_part_id`
- `po_id`
- `due_date`
- `due_amount_kzt`
- `truth_source`
- `source_updated_at`

Accepted truth sources:

- explicit supplier-confirmed payable date
- operator-approved payable schedule captured into the receiving-side truth chain
- transfer-ledger-linked dated obligation if it directly ties to the live unpaid part balance

Not acceptable:

- null due dates
- supplier-code proxies like `SUPP_A`
- PO-level guesswork that cannot allocate amounts to the live unpaid parts

Pass condition:

- every unpaid `SHR` part due before `2026-03-20` is dated and amount-matched

Fail condition:

- any unpaid part without exact due-date truth keeps the decision blocked

### C. Reconcile the exposure mismatch

Required output:

- one reconciliation artifact explaining the `2,301,597.50 KZT` gap between `PO_PAYMENT_STATUS.md` and live `po_part`

Questions that must be answered explicitly:

- Is the artifact missing part-level rows?
- Is one source base-only while the other mixes base plus other obligations?
- Are legacy POs like `Line52_PO-9` included in one view but excluded in another?
- Are FX conversions or cutoff times causing the difference?

Pass condition:

- one canonical `SHR` unpaid total is established for this decision window

Fail condition:

- if multiple unreconciled totals remain in circulation, do not authorize payment

### D. Rebuild the deadline cash path from truth, not proxy timing

Once A, B, and C are done, recompute the deadline cash path using:

- refreshed actual liquid cash anchor
- exact OPEX commitments
- contract cash floors
- exact dated `SHR` obligations through `2026-03-20`

Required outputs:

- refreshed day-by-day cash path to `2026-03-20`
- base tranche
- conservative tranche
- actual decision-safe tranche

Decision formula:

- `actual decision-safe tranche = min_daily_close_actual_path - (required_cash_floor + 500,000 buffer)`
- if negative, clamp to `0`

## Smallest safe implementation plan

1. Capture a fresh balance snapshot now across all liquid accounts.
2. Produce a short balance reconciliation artifact tied to that snapshot.
3. Build a part-level `SHR` due schedule through `2026-03-20`.
4. Reconcile `PO_PAYMENT_STATUS.md` against live `po_part` and publish one canonical unpaid total.
5. Regenerate the deadline cash path using the refreshed balance anchor plus the dated `SHR` schedule.
6. Recompute the base, conservative, and actual decision-safe tranches.
7. Authorize payment only if the actual decision-safe tranche is positive after preserving all OPEX, contract floors, and the extra `500,000 KZT` buffer.

## What should not be done

- Do not pay against the stale `2026-03-02` balance anchor.
- Do not treat the `SUPP_A` proxy schedule as authoritative `SHR` due-date truth.
- Do not ignore the `10.67m` vs `12.97m` exposure mismatch.
- Do not widen buffers or drop the extra `500,000 KZT` requirement to force a non-zero answer.

## Full-unblock completion criteria

The blocker is fully cleared only when all of the following are true:

- fresh actual liquid cash by account is captured and auditable
- exact `SHR` due dates through `2026-03-20` exist at a usable grain
- current `SHR` unpaid exposure has one reconciled canonical total
- refreshed cash path is recomputed from that truth set
- resulting actual decision-safe tranche is non-negative and explicitly derived

Until then, the correct treasury answer remains:

- maximum safe actual `SHR` payment before `2026-03-20 00:00` = `0 KZT`
