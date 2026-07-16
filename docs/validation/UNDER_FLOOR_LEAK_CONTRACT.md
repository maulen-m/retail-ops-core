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

- owner decision
  `config/owner_decisions/price_floor_doctrine_5pct_poc_2026_07_06.json`
  (`OD-PRICE-FLOOR-DOCTRINE-5PCT-POC-2026-07-06`), which retires the old
  30/35%-POC floors and makes the sell-off red-line the sell price that
  preserves at least 5% profit on COGS;
- Web_automation
  `exports/pricelist_snapshots/min_price_floor_5pct_by_sku_v8.csv`, whose
  compatibility column `Min_price_35pct` carries the binding 5%-POC values;
- documented by Web_automation `Docs/inventory/repricer_live_price_rules.md`.

Sales source:

- `sales_fact_v2` is used as the current sales movement truth because it carries `order_date`, `quantity`, `sell_price_kzt`, status, store, and SKU fields at the sales grain.
- The original gate note names `fact_orders_kaspi`; the current production schema has order lifecycle dates and `unit_price_kzt`, but no `order_date`. Use `fact_orders_kaspi` only as a corroborating order-lifecycle probe unless the gate contract is explicitly revised.

Compact child floor aliases are allowed only when declared in `config/validation/under_floor_leak.json`. Missing aliases are stoplines, not silent inheritance.

The declared suit aliases use compatibility evidence from `config/owner_decisions/owner_stock_approval_2026_06_14.json`. The declared compact LINE `TS` aliases use the 2026-06-18 owner-approved `OA-PRICE03-LINE` floor authority from the current owner-action queue and resolve only `LINE-21-TS` and `LINE-31-TS` to parent `CL_OC_MEN_LINE51_WHITE` for `G-PRICE-03` scoring. This contract does not create live price-write authority.

Scoring exception authority is optional and config-driven through
`config/validation/under_floor_leak.json` key `scoring_exception_authority`. If
that key is absent, the reporter keeps the legacy behavior: all non-cancelled
rows with floors and prices are scored for under-floor leakage.

`scoring_exception_authority.entries[]` is the only accepted exception surface.
Each entry must include:

- `id`;
- `class`;
- `action`;
- exact non-wildcard `store_code`;
- `decision_ref`;
- `decision_record`;
- at least one row/family scope field: `sku_keys`, `sku_key_prefixes`,
  `sku_ids`, `sku_id_prefixes`, or `kaspi_offer_name_contains`.

Entries with missing required fields or unsupported values fail the report check
`scoring_exception_authority_config_valid`. Store matching is case-insensitive.
SKU key, SKU id, and prefix matching are exact/case-sensitive. Offer-name
contains matching is case-insensitive. The reporter never applies a silent
store-wide exception.

The only supported exception class is `STRATEGIC_BRAND_PRICING`. The only
supported actions are:

- `EXCLUDE_FROM_LEAK_SCORING`: matching non-cancelled rows are excluded from
  under-floor leak counts, missing-floor counts, and missing-price counts for
  `G-PRICE-03`, but are still emitted visibly in
  `strategic_brand_pricing_excluded_rows`;
- `ENFORCE_FLOOR`: matching rows are a carve-out and remain in normal floor
  scoring even if another strategic entry could otherwise match.

`ENFORCE_FLOOR` entries are evaluated before `EXCLUDE_FROM_LEAK_SCORING`
entries.

OD2-B 2026-07-02, recorded in
`docs/plan/green_path_2026-06/green_path_run/OWNER_APPROVALS_20260702_RESUME.md`,
defines the current `STRATEGIC_BRAND_PRICING` policy:

- ACMEWEAR-store LINE31, LINE61, LINE51, and current configured sub-bundle child
  rows are owner-brand strategic pricing rows. They are excluded from
  `G-PRICE-03` leak scoring only by explicit `STRATEGIC_BRAND_PRICING`
  `EXCLUDE_FROM_LEAK_SCORING` entries.
- The LINE61 LS31-BLK / RUSH 3-in-1 carve-out remains enforced by an explicit
  `ENFORCE_FLOOR` entry. Current sales data carries this concrete row as
  `SUIT-31-LS`; the config also names literal owner label `LS31-BLK` if a future
  row arrives with that key.
- UNIVERSAL and STOREB rows are generic commodity rows and remain fully enforced
  with no strategic exception authority. The independent selloff-protection
  rule below may still protect an explicitly named product family in any store.

## Selloff protection

The reporter loads the read-only selloff-protection authority from
Web_automation `config/selloff_price_protect.yaml`, introduced by commit
`2600dde53c7d9fcae18ef1c2c1999e3fc58a8cee`. If that path is unavailable, the
reporter must load the AB-local mirror
`config/validation/selloff_price_protect.local.json` and emit a visible warning
that the fallback was used. If neither source is available or the selected
source is invalid, `selloff_price_protect_config_valid` fails closed.

The selected protection source must declare `never_raise: true`. SKU-key prefix
matching is exact and case-sensitive. Product-code matching is exact against
the sales row's `sku_id`, the only product-code-like identifier on the
`sales_fact_v2` reporting grain. Protection applies across all stores; it is
not strategic-brand pricing and does not reuse
`scoring_exception_authority`.

Every matching non-cancelled row is reported informationally under the JSON
`selloff_protected` section and in `selloff_protected.csv`, including whether
it is below floor, above floor, missing a floor, or missing a price. Protected
rows are excluded from `under_floor_sales.csv` and from
`under_floor_by_sku.csv`; they never become lift candidates or contribute to
the strict leak, missing-floor, or missing-price counts.

This is scoring authority only. It does not create aggressive price-lowering
authority, owner-brand price-change authority, Repricer authority, Kaspi
authority, or any other external-write authority.

## Evidence

Reporter:

- `scripts/report_under_floor_leak.py`

Default outputs:

- `exports/validation/under_floor_leak/<run>/under_floor_leak_report.json`
- `exports/validation/under_floor_leak/<run>/under_floor_leak_report.md`
- `exports/validation/under_floor_leak/<run>/under_floor_sales.csv`
- `exports/validation/under_floor_leak/<run>/selloff_protected.csv`
- `exports/validation/under_floor_leak/<run>/strategic_brand_pricing_excluded_rows.csv`
- `exports/validation/under_floor_leak/<run>/missing_floor_sales.csv`
- `exports/validation/under_floor_leak/<run>/missing_price_sales.csv`
- `exports/validation/under_floor_leak/<run>/under_floor_by_sku.csv`

JSON reports include:

- `selloff_protected`: selected authority source, warnings, visible row list,
  row/unit counts, and informational under-floor gap;
- `strategic_brand_pricing_excluded_rows`: visible list of every row matched by
  `EXCLUDE_FROM_LEAK_SCORING`;
- `strategic_brand_pricing_excluded_row_count`;
- `strategic_brand_pricing_excluded_units`;
- `strategic_brand_pricing_excluded_gap_kzt`.

The Markdown report includes a `Strategic Brand Pricing Excluded Rows` section.
These rows are excluded from the leak count but are never hidden.

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
