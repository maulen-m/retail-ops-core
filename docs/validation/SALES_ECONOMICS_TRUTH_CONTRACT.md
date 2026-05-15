# SALES_ECONOMICS_TRUTH_CONTRACT

## Purpose
Define one fail-closed contract for sales economics publication and parity checks.
This contract is the authority for:
- delivered-date basis used by monthly sales economics,
- formulas for Net Revenue / COGS / Profit,
- decision-grade vs provisional labeling.

## Canonical Hierarchy
1. `docs/inventory/Master_Inventory_Rules_v9.md` (canonical formulas/parameters)
2. This contract (`docs/validation/SALES_ECONOMICS_TRUTH_CONTRACT.md`)
3. DB truth views (`view_sales_line_truth`, `view_sales_daily_truth`)
4. Derived reports (`BUSINESS_INSIDES`, scorecards)

If code differs from v9 formulas, update `docs/inventory/Master_Inventory_Rules_v9.md` first, then this contract, then code/tests.

## Delivered Date Basis
- `transaction_date` for archive parity rows is resolved in this order:
  1. `status_change_date` (`Дата изменения статуса`) when present,
  2. `ui_override_status_date` when UI pack enrichment provides a stricter value,
  3. `creation_date_fallback` (`Дата поступления заказа`) only for legacy months before cutover.
- Cutover policy:
  - `statusdate_cutover = 2026-02-27`
  - For delivered rows with `transaction_date >= 2026-02-27`, `creation_date_fallback` is forbidden in strict mode.
  - Rationale:
    - Current locked archive evidence still contains non-zero legacy fallback rows for `STOREB` up to `2026-02-19`.
    - Those rows remain provisional until a full UI status-date refresh replaces them with authoritative `Дата изменения статуса`.

## Economics Formulas (Kaspi, v9)
Per unit:
- `NetRev = (SellPrice * (1 - CommissionRate) - NetDeliveryFee) * (1 - VATRate) - AdsCostUnit`
- `COGS = BaseCostCNY * CNY_KZT + WeightKG * DLV_RATE_USD_KG * USD_KZT`
- `Profit = NetRev - COGS`

Monthly totals:
- `Units_month = SUM(units)`
- `NetRev_month = SUM(NetRev_line)`
- `COGS_month = SUM(COGS_line)`
- `Profit_month = SUM(Profit_line)`

Rounding policy:
- Line-level values stored as numeric KZT in DB.
- Monthly comparisons use absolute KZT tolerance from parity script (`+1 KZT`) and percentage tolerance (`0.5%` default) for exceed checks.

## Decision-Grade Rules
A month/store pair is `decision_grade=true` only when all are true:
- month is closed (`month_end < as_of_until`),
- month is not pre-cutover (`month_end >= statusdate_cutover`),
- delivered rows for that month/store contain no `creation_date_fallback`.

Otherwise pair is `provisional` and must be reported as such.

## Parity Gate
`validate_monthly_economics_parity.py --strict` fails when:
- any decision-grade month/store has `db_units` or `db_net_rev_kzt` exceeding archive-derived totals by tolerance.

Artifacts required:
- `summary.json`
- `report.md`
- `monthly_db.csv`
- `monthly_archive.csv`
- `diffs_by_month.csv`

## Stop-the-line
- Any decision-grade month published with fallback transaction dates.
- Any decision-grade month where DB economics exceed archive-derived delivered totals beyond tolerance.
- Any publication of profit as decision-grade when required COGS/identity coverage gates are red.
