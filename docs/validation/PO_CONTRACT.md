# PO Contract (V1)

Purpose: single owner of PO output comparison rules + tolerances.
Scope: size-aware PO engine outputs and PO dashboard invariants.

Source of truth:
- Formulas: `docs/inventory/Master_Inventory_Rules_v8.md`
- Schema: `docs/inventory/Sales_Data_Model_V16.md`
- Initial tolerances: `docs/inventory/Automation_Handoff_V16.md` (Section 6)

## Tolerances (machine-readable)
D_30_pct: 1
SS_total_pct: 1
ROIC_pct: 2
STATUS: exact
ORDER_QTY: exact

## Golden fixtures (deterministic)
- Input cases: `tests/fixtures/po_golden/po_contract_cases.json`
- Expected outputs + hashes: `tests/fixtures/po_golden/po_contract_expected.json`

## Metrics compared
- **D_30 (d_sku)**: relative tolerance D_30_pct
- **SS_total (ss_total_sku)**: relative tolerance SS_total_pct
- **ROIC (roic_monthly)**: relative tolerance ROIC_pct
- **Status flags**: exact match (`roic_action`, `should_order`)
- **Order quantities**: exact match (`total_qty`, `allocations`)

## Deterministic hash contract
- Canonical JSON: sorted keys, floats rounded to 6 decimals
- Excludes timestamps (`created_at`)
- Hash algorithm: SHA-256

## Update protocol
1) Update `docs/inventory/Master_Inventory_Rules_v8.md` first.
2) Regenerate fixtures + expected hashes if outputs legitimately change.
3) Update this doc only if tolerances or contract scope changes.
