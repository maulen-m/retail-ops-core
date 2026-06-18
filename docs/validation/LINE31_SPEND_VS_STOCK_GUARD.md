# LINE31 Spend Vs Stock Guard

Purpose: provide the `G-LINE31-01` read-only evidence surface that checks LINE31 Kaspi ad spend against current LINE31 stock truth.

## Contract

- Source ads truth is `ads_campaign_product_daily` in `db/app.db`.
- Source stock truth is the latest `fact_inventory_snapshot_size` snapshot on or before the report `as_of` date.
- LINE31 scope is any row where `sku_key` or `campaign_name` contains `LINE31`.
- The guard never invents spend. Missing LINE31 ad rows are reported as absence of in-scope rows, not as synthetic zero-spend.
- Any positive LINE31 spend row is a violation when the advertised LINE31 `sku_key` has at least one latest-snapshot size with `current_stock <= 0`.
- Any positive LINE31 spend row without matching latest LINE31 stock evidence is also a violation.
- Zero-cost LINE31 rows are retained as evidence but do not create spend-vs-empty-size violations.

## Outputs

The guard writes a timestamped evidence directory with:

- `line31_spend_vs_stock_guard.json`
- `line31_spend_vs_stock_guard.md`
- `line31_ads_rows.csv`
- `line31_stock_rows.csv`
- `line31_violations.csv`

The guard is read-only over the DB and does not mutate DB, workbook, Google Sheet, Telegram, Kaspi, Web_automation, Meta, price, stock, cash, PO, supplier, scheduler, or customer/operator-message surfaces.

## Prepared Standing Schedule

The prepared LaunchAgent config is `config/com.example.line31-spend-vs-stock-guard.plist`.

- Label: `com.example.line31-spend-vs-stock-guard`
- Wrapper: `scripts/run_line31_spend_vs_stock_guard.sh`
- Schedule: daily `06:10` local time
- RunAtLoad: `false`
- Behavior: run the guard in strict mode and write evidence under `exports/validation/line31_spend_vs_stock_guard/`

Installing/loading the LaunchAgent is a separate scheduler mutation and must be recorded as runtime evidence before `G-LINE31-01` can be promoted from `ARMED` to `GREEN`.
