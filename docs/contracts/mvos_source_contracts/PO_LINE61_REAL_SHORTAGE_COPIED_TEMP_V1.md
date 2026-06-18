# PO_LINE61_REAL_SHORTAGE_COPIED_TEMP_V1

Status: active copied-temp contract.

Classification id: `PO_ACCEPTED_REAL_SHORTAGE_LINE61_2026_05_OWNER_CONFIRMED`

Accepted at: `2026-05-18T21:23:26+05:00`

Accepted by: CodeCaptain `2026-05-18 21:23:26` review, with owner-confirmed Line61 shortage truth from `2026-05-18T18:27:14+05:00`.

Supersedes: `PO4_LINE61_ACTUAL_RECEIVED_SHORTAGE_OWNER_CONFIRMED_20260518`.

## Purpose

This contract preserves PO-4.0 Line61 shortage truth in copied-temp MVOS proof. The `23` unit delta is a real shortage, not a workbook typo and not missing sellable stock.

## Accepted Facts

| Fact | Value |
| --- | --- |
| PO | `PO-4.0` |
| Product | `CL_NEW-CLO2_MEN_SUIT-61_BLACK` |
| Ordered/cargo units | `115` |
| Actual received units | `92` |
| Short units | `23` |
| XL shortage | `7` |
| 2XL shortage | `5` |
| 3XL shortage | `6` |
| 4XL shortage | `5` |
| Part total ordered/cargo basis | `1925` |
| Part total actual-received basis | `1902` |
| Part total delta | `23` |

## Scope

Allowed scope:

- copied validation DB only;
- `production_authority=false`;
- copied-temp PO, stock, dashboard, and money-gate reasoning;
- retained-blocker board proof;
- validator or proof-adapter behavior that separates ordered/cargo, actual received, shortage, inbound, current stock, and sellable stock.

Forbidden scope:

- workbook mutation;
- production `db/app.db` mutation;
- PO commitment;
- supplier payment;
- stock mutation;
- treating short units as sellable stock;
- treating the shortage as a typo;
- hiding PO money/dashboard failures.

## Validator Contract

Validators and proof adapters must treat these as separate quantities:

- ordered/cargo units;
- actual received units;
- shortage units;
- current sellable stock;
- inbound units;
- reserved or blocked units.

The real `23` unit shortage may explain the `1902` vs `1925` part-total delta, but it does not by itself make the PO money gate green. Source-backed May 18 stock truth and remaining PO validator requirements must still pass.

The narrow accepted-shortage classification may be attached only when both exact validator rows are present:

- `cargo_vs_inbounds` for `PO-4.0` / `CL_NEW-CLO2_MEN_SUIT-61_BLACK`: expected actual received `92`, observed cargo `115`, delta `23`;
- `totals_vs_inbounds` for `PO-4.0` / `*PART_TOTAL*`: expected actual-received basis `1902`, observed ordered/cargo basis `1925`, delta `23`.

Classification behavior:

- remove these exact rows from any "unknown mismatch" bucket;
- keep the inbound consistency validator non-green while the retained accepted shortage is visible;
- keep `inbound_sheet_consistency`, `single_truth_system`, `cogs_integrity`, and `single_truth_alignment` money-gate failures visible unless independently fixed;
- do not authorize workbook, production DB, PO commitment, supplier payment, stock, or price mutation.

## Required Validation

The next proof wave must run:

```bash
python3 scripts/validate_po_money_gate.py --db <copied-db> --as-of 2026-05-18 --json
python3 scripts/validate_po_dashboard_invariants.py --db <copied-db>
```

Expected proof behavior:

- the Line61 shortage is represented as real shortage, not received stock;
- PO money-gate failures remain visible unless the validator contract and source-backed stock truth actually clear them;
- the `9` high-stock exception blockers remain visible.

## Stoplines

- Do not mutate the workbook.
- Do not count the `23` short units as received or sellable stock.
- Do not commit PO or supplier payment.
- Do not claim production PO green from copied-temp reasoning.
- Do not use stock simulation as stock source freshness.
