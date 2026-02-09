# Business Insides Snapshot

- Generated at: `2026-02-09 11:36:18`
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
+--------------------------+------------+
| Metric                   | Value KZT  |
+--------------------------+------------+
| Avg 30d Net Rev          | 435,508.72 |
| Avg 30d COGS             | 221,269.19 |
| Avg 30d Profit           | 214,239.53 |
| Avg 30d Ads Spend        | 0.00       |
| Avg 30d Profit After Ads | 214,239.53 |
| Avg 7d Net Rev           | 403,197.43 |
| Avg 7d COGS              | 197,155.48 |
| Avg 7d Profit            | 206,041.94 |
| Avg 7d Ads Spend         | 0.00       |
| Avg 7d Profit After Ads  | 206,041.94 |
+--------------------------+------------+
```

## Last 7 Days Values (KZT)

```text
+------------+---------------+------------+------------+-----------+------------+------------------+
| Date       | Units Shipped | Net Rev    | COGS       | Ads Spend | Profit     | Profit After Ads |
+------------+---------------+------------+------------+-----------+------------+------------------+
| 2026-02-02 | 60            | 369,205.40 | 173,020.18 | 0.00      | 196,185.22 | 196,185.22       |
| 2026-02-03 | 56            | 330,709.62 | 160,809.04 | 0.00      | 169,900.58 | 169,900.58       |
| 2026-02-04 | 65            | 535,708.55 | 283,812.43 | 0.00      | 251,896.12 | 251,896.12       |
| 2026-02-05 | 53            | 306,026.88 | 151,441.61 | 0.00      | 154,585.26 | 154,585.26       |
| 2026-02-06 | 64            | 394,852.61 | 186,822.68 | 0.00      | 208,029.93 | 208,029.93       |
| 2026-02-07 | 77            | 482,681.52 | 227,026.96 | 0.00      | 255,654.56 | 255,654.56       |
| 2026-02-08 | N/A           | N/A        | N/A        | 0.00      | N/A        | N/A              |
+------------+---------------+------------+------------+-----------+------------+------------------+
```

## Data Quality

- Sales source: `view_sales_line_truth` / `view_sales_daily_truth` (canonical interface over staging).
- COGS fallback rows: `472/1967` (24.00%).
- Unresolved COGS rows: `3`.
- Unresolved SKU count: `2`.
- Ads mapping coverage: `0.00%`.
- Ads mapped/unmapped cost: `0.00` / `0.00`.

## External Reference Check

- Status: `ok`
- Details: `{'status': 'ok', 'path': '~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/Exports_db/real_sales_snapshots/20260207_205717/sales_daily_sku_size_2024-09-06_to_2026-02-07_real_sales_snapshot_20260207_205717.csv', 'matched_days': 6, 'max_abs_diff_net_rev_kzt': 251553.32, 'max_abs_diff_cogs_kzt': 283812.43}`
