# G-PRICE-03 Under-Floor Leak Contract

Status: active validation contract
Gate: G-PRICE-03

## Purpose

`G-PRICE-03` proves that the business is no longer selling non-cancelled orders below the binding internal floor.

The gate is GREEN only when a read-only report over the trailing 7 calendar days proves:

- every non-cancelled `sales_fact_v2` row has a resolvable binding floor;
- every compared row has a sell price;
- `sell_price_kzt >= binding_floor_kzt` for every compared row;
- the sales truth source is fresh enough for the standing check.

## Authority

Binding floor source:

- Web_automation `exports/pricelist_snapshots/min_price_floor_35pct_by_sku_v7.csv`
- documented by Web_automation `Docs/inventory/repricer_live_price_rules.md`

Sales source:

- `sales_fact_v2` is used as the current sales movement truth because it carries `order_date`, `quantity`, `sell_price_kzt`, status, store, and SKU fields at the sales grain.
- The original gate note names `fact_orders_kaspi`; the current production schema has order lifecycle dates and `unit_price_kzt`, but no `order_date`. Use `fact_orders_kaspi` only as a corroborating order-lifecycle probe unless the gate contract is explicitly revised.

Compact child floor aliases are allowed only when declared in `config/validation/under_floor_leak.json`. Missing aliases are stoplines, not silent inheritance.

The current declared aliases use only suit compatibility evidence from `config/owner_decisions/owner_stock_approval_2026_06_14.json`. LINE compact child rows are intentionally not aliased by this contract because existing owner COGS approvals were exact-row/DB-only and explicitly did not create SKU-wide inheritance or pricing authority.

## Evidence

Reporter:

- `scripts/report_under_floor_leak.py`

Default outputs:

- `exports/validation/under_floor_leak/<run>/under_floor_leak_report.json`
- `exports/validation/under_floor_leak/<run>/under_floor_leak_report.md`
- `exports/validation/under_floor_leak/<run>/under_floor_sales.csv`
- `exports/validation/under_floor_leak/<run>/missing_floor_sales.csv`
- `exports/validation/under_floor_leak/<run>/missing_price_sales.csv`
- `exports/validation/under_floor_leak/<run>/under_floor_by_sku.csv`

The report must not contain customer names, phones, addresses, tokens, or message contents.

## Forbidden Actions

This contract does not authorize:

- production DB writes;
- workbook writes;
- Google Sheet edits;
- Telegram sends;
- Kaspi merchant/UI/API writes;
- Repricer writes;
- price uploads;
- stock writes;
- customer/operator-message writes;
- LaunchAgent changes;
- any other external write.

If the report is RED, remediation must be a separate dry-run/plan first. Any live price write still needs an exact owner-approved write surface, env gate, fresh input vintage, and post-readback proof.
