# PO_LINE61_REAL_SHORTAGE_PRODUCTION_SAFE_V1

Status: active production-safe shortage classification.

Classification id: `PO_ACCEPTED_REAL_SHORTAGE_LINE61_2026_05_OWNER_CONFIRMED`

Accepted at: `2026-06-01`

Supersedes: `docs/contracts/mvos_source_contracts/PO_LINE61_REAL_SHORTAGE_COPIED_TEMP_V1.md`

## Purpose

This contract preserves the PO-4.0 Line61 shortage as durable inbound truth. The `23` unit delta is a real accepted shortage, not a workbook typo and not sellable stock.

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

## Validator Contract

The inbound consistency validator may classify only these exact rows as accepted production-safe shortage truth:

- `cargo_vs_inbounds` for `PO-4.0` / `CL_NEW-CLO2_MEN_SUIT-61_BLACK`: expected actual received `92`, observed cargo `115`, delta `23`;
- `totals_vs_inbounds` for `PO-4.0` / `*PART_TOTAL*`: expected actual-received basis `1902`, observed ordered/cargo basis `1925`, delta `23`.

Classification behavior:

- keep both rows visible in validator JSON and human output;
- set `production_authority=true` only for the shortage classification itself;
- clear the inbound sheet consistency gate when no unknown mismatches remain;
- keep `clears_po_money_gate=false`;
- do not count the short units as received, sellable, reserved, or on-hand stock;
- do not authorize workbook mutation, production DB mutation, supplier payment, PO commitment, stock offer mutation, price mutation, or owner publication.

## Stoplines

- Do not hide the shortage.
- Do not treat the `23` units as a typo.
- Do not use this classification to clear unrelated PO money, dashboard, COGS, stock, or publication blockers.
