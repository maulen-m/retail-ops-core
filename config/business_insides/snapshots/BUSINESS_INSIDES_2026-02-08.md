# Business Insides Snapshot

- Generated at: `2026-02-09 16:20:14`
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
| Avg 30d Net Rev          | 361,797.93 |
| Avg 30d COGS             | 174,181.64 |
| Avg 30d Profit           | 187,616.27 |
| Avg 30d Ads Spend        | 0.00       |
| Avg 30d Profit After Ads | 187,616.27 |
| Avg 7d Net Rev           | 347,085.04 |
| Avg 7d COGS              | 160,806.70 |
| Avg 7d Profit            | 186,278.31 |
| Avg 7d Ads Spend         | 0.00       |
| Avg 7d Profit After Ads  | 186,278.31 |
+--------------------------+------------+
```

## Last 7 Days Values (KZT)

```text
+------------+---------------+------------+------------+-----------+------------+------------------+
| Date       | Units Shipped | Net Rev    | COGS       | Ads Spend | Profit     | Profit After Ads |
+------------+---------------+------------+------------+-----------+------------+------------------+
| 2026-02-02 | 60            | 369,205.40 | 173,020.18 | 0.00      | 196,185.21 | 196,185.21       |
| 2026-02-03 | 49            | 294,228.04 | 137,620.51 | 0.00      | 156,607.52 | 156,607.52       |
| 2026-02-04 | 51            | 428,146.24 | 221,314.02 | 0.00      | 206,832.23 | 206,832.23       |
| 2026-02-05 | 41            | 235,971.05 | 105,554.04 | 0.00      | 130,416.98 | 130,416.98       |
| 2026-02-06 | 46            | 278,560.36 | 124,867.22 | 0.00      | 153,693.10 | 153,693.10       |
| 2026-02-07 | 50            | 327,356.33 | 132,866.48 | 0.00      | 194,489.84 | 194,489.84       |
| 2026-02-08 | 48            | 496,127.84 | 230,404.48 | 0.00      | 265,723.30 | 265,723.30       |
+------------+---------------+------------+------------+-----------+------------+------------------+
```

## Data Quality

- Sales source: `view_sales_line_truth` / `view_sales_daily_truth` (canonical interface over staging).
- COGS fallback rows: `517/1645` (31.43%).
- Unresolved COGS rows: `6`.
- Unresolved SKU count: `2`.
- Ads mapping coverage: `0.00%`.
- Ads mapped/unmapped cost: `0.00` / `0.00`.

## External Reference Check

- Status: `ok`
- Details: `{'status': 'ok', 'path': '~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/Exports_db/real_sales_snapshots/20260207_205717/sales_daily_sku_size_2024-09-06_to_2026-02-07_real_sales_snapshot_20260207_205717.csv', 'matched_days': 6, 'max_abs_diff_net_rev_kzt': 96228.12, 'max_abs_diff_cogs_kzt': 221314.02}`
