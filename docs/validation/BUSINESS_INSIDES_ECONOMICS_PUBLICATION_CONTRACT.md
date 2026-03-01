# BUSINESS_INSIDES_ECONOMICS_PUBLICATION_CONTRACT

## Scope
Decision-grade economics publication for `BUSINESS_INSIDES` outputs.

## Canonical Inputs
- Sales truth: `view_sales_line_truth`, `view_sales_daily_truth`
- As-of control: `--as-of` execution input
- Volatility window: `AB_ECONOMICS_VOLATILITY_DAYS` (default `14`)

## Publication Rule
Profit-related metrics are publishable only when all checks pass.

## Strict Checks
For the 30-day window ending `as_of`:
- `nonvolatile_missing_days_zero`
  - no nonvolatile day may have missing economics totals (`cogs_kzt`, `profit_kzt`).
- `nonvolatile_missing_sku_identity_zero`
  - no nonvolatile sales line may have missing `sku_key`.
- `nonvolatile_missing_unit_cost_zero`
  - no nonvolatile sales line may have missing unit cost (`cogs_kzt IS NULL` or `cogs_source='unresolved'`).
- `locked_snapshot_masks_profit_fields`
  - if profit lock is ON, snapshot must not expose average COGS/profit fields.

## Fail-Closed Behavior
- Any strict check FAIL -> validator exits non-zero in `--strict`.
- Profit metrics remain locked (`N/A`) while lock conditions remain.

## Command
```bash
python3 scripts/validate_business_insides_economics_ready.py --as-of <YYYY-MM-DD> --strict
```

## Output Artifacts
- `exports/validation/business_insides_economics/<as_of>/economics_ready_report.json`
- `exports/validation/business_insides_economics/<as_of>/economics_ready_report.md`

## Change Protocol
If formulas/policy thresholds change:
1. Update `docs/inventory/Master_Inventory_Rules_v8.md` first.
2. Update this contract.
3. Update validator/tests.
