# PLAN_SALES_TRUTH_INTEGRITY_REPAIR_EXTERNAL_ORACLE_2026-02-27

## Purpose
Repair sales truth integrity using external ArchiveOrders oracle data at the canonical DB/view layer (not report-layer overlays).

## Phases
1. Adapter: normalize ArchiveOrders exports into deterministic delivered-line reference artifacts.
2. Strict parity gate: compare published truth views vs external reference by day/store aggregates and order-id sets.
3. Upstream repair path: gated DB sync into `fact_sales_external_ref` with backup + rollback.
4. Governance wiring: enforce parity in `system_doctor --strict` and H5 proving contract when configured.

## Contracts
- `docs/validation/SALES_TRUTH_EXTERNAL_REFERENCE_CONTRACT.md`
- Canonical truth remains:
  - `view_sales_line_truth`
  - `view_sales_daily_truth`

## Implemented Gates
- `python3 scripts/validate_sales_truth_external_reference.py --strict` (explicit source)
- `python3 scripts/validate_sales_truth_external_reference.py --strict-if-configured` (doctor integration)

## Stop-Line
- Any aggregate mismatch (units/revenue/orders) by day+store.
- Any order-id set mismatch (`missing_in_db` or `extra_in_db`).
- Any unresolved warehouse-to-store mapping in strict mode.

## Rollback
If DB sync was applied:
1. Restore backup created by `scripts/build_kaspi_etl_sales_reference.py --apply`.
2. Re-run:
   - `python3 scripts/validate_sales_truth_external_reference.py --strict ...`
   - `python3 scripts/generate_business_insides.py --as-of <day>`
