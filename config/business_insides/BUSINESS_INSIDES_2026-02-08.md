# Business Insides Snapshot

- Generated at: `2026-02-08 23:14:26`
- As of date: `2026-02-08`
- Paid-capital snapshot date: `2026-02-07`
- Bank snapshot date: `2026-02-08`

## Capital Snapshot (KZT)

```text
+-----------------------------------+---------------+
| Metric                            | Value KZT     |
+-----------------------------------+---------------+
| Cash (actual, bank_accounts.yaml) | 2,003,917.38  |
| Inventory on-hand paid            | 7,975,188.00  |
| Inventory inbound paid            | 12,145,974.20 |
| Inventory on-delivery paid        | 289,275.00    |
| Total capital (paid truth)        | 22,414,354.58 |
| Inbound unpaid obligations        | 19,228,238.50 |
| Capital + unpaid inbound          | 41,642,593.08 |
+-----------------------------------+---------------+
```

## Performance Metrics (KZT)

```text
+-----------------+------------+
| Metric          | Value KZT  |
+-----------------+------------+
| Avg 30d Net Rev | 357,221.99 |
| Avg 30d COGS    | 173,297.33 |
| Avg 30d Profit  | 183,924.66 |
| Avg 7d Net Rev  | 322,515.85 |
| Avg 7d COGS     | 150,241.00 |
| Avg 7d Profit   | 172,274.85 |
+-----------------+------------+
```

## Last 7 Days Values (KZT)

```text
+------------+------------+------------+------------+
| Date       | Net Rev    | COGS       | Profit     |
+------------+------------+------------+------------+
| 2026-02-02 | 369,205.40 | 175,032.00 | 194,173.40 |
| 2026-02-03 | 294,228.04 | 139,230.00 | 154,998.04 |
| 2026-02-04 | 428,146.24 | 220,584.00 | 207,562.24 |
| 2026-02-05 | 235,971.05 | 106,548.00 | 129,423.05 |
| 2026-02-06 | 278,560.36 | 121,836.00 | 156,724.36 |
| 2026-02-07 | 328,983.99 | 138,216.00 | 190,767.99 |
| 2026-02-08 | N/A        | N/A        | N/A        |
+------------+------------+------------+------------+
```

## Data Quality

- Sales source: `sales_fact_v2` (`DELIVERED`, `return_flag=0`).
- COGS fallback rows: `472/1597` (29.56%).
- Unresolved COGS rows: `3`.
- Unresolved SKU count: `2`.

## External Reference Check

- Status: `ok`
- Details: `{'status': 'ok', 'path': '~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/Exports_db/real_sales_snapshots/20260207_205717/sales_daily_sku_size_2024-09-06_to_2026-02-07_real_sales_snapshot_20260207_205717.csv', 'matched_days': 6, 'max_abs_diff_net_rev_kzt': 97855.78, 'max_abs_diff_cogs_kzt': 220584.0}`
