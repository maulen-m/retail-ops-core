# Business Insides Snapshot

- Generated at: `2026-02-10 20:32:34`
- As of date: `2026-02-09`
- Paid-capital snapshot date: `2026-02-09`
- Bank snapshot date: `2026-02-09`

## Capital Snapshot (KZT)

```text
+-----------------------------------+---------------+
| Metric                            | Value KZT     |
+-----------------------------------+---------------+
| Cash (actual, bank_accounts.yaml) | 2,003,917.38  |
| Inventory on-hand paid            | 6,407,856.00  |
| Inventory inbound paid            | 12,145,974.20 |
| Inventory on-delivery paid        | 416,175.00    |
| Total capital (paid truth)        | 20,973,922.58 |
| Inbound unpaid obligations        | 19,228,238.50 |
| Capital + unpaid inbound          | 40,202,161.08 |
+-----------------------------------+---------------+
```

## Performance Metrics (KZT)

```text
+--------------------------+------------+
| Metric                   | Value KZT  |
+--------------------------+------------+
| Avg 30d Net Rev          | 365,174.43 |
| Avg 30d COGS             | 218,516.16 |
| Avg 30d Profit           | 146,658.26 |
| Avg 30d Ads Spend        | 0.00       |
| Avg 30d Profit After Ads | 146,658.26 |
| Avg 7d Net Rev           | 355,262.14 |
| Avg 7d COGS              | 205,487.94 |
| Avg 7d Profit            | 149,774.19 |
| Avg 7d Ads Spend         | 0.00       |
| Avg 7d Profit After Ads  | 149,774.19 |
+--------------------------+------------+
```

## Last 7 Days Values (KZT)

```text
+------------+---------------+------------+------------+-----------+------------+------------------+
| Date       | Units Shipped | Net Rev    | COGS       | Ads Spend | Profit     | Profit After Ads |
+------------+---------------+------------+------------+-----------+------------+------------------+
| 2026-02-03 | 49            | 294,228.04 | 174,539.40 | 0.00      | 119,688.63 | 119,688.63       |
| 2026-02-04 | 51            | 428,146.24 | 269,756.96 | 0.00      | 158,389.25 | 158,389.25       |
| 2026-02-05 | 41            | 235,971.05 | 133,814.92 | 0.00      | 102,156.14 | 102,156.14       |
| 2026-02-06 | 46            | 278,560.36 | 162,561.63 | 0.00      | 115,998.71 | 115,998.71       |
| 2026-02-07 | 50            | 302,833.76 | 174,908.73 | 0.00      | 127,925.04 | 127,925.04       |
| 2026-02-08 | 48            | 493,849.31 | 276,166.77 | 0.00      | 217,682.50 | 217,682.50       |
| 2026-02-09 | 59            | 453,246.20 | 246,667.15 | 0.00      | 206,579.03 | 206,579.03       |
+------------+---------------+------------+------------+-----------+------------+------------------+
```

## Data Quality

- Sales source: `view_sales_line_truth` / `view_sales_daily_truth` (canonical interface over staging).
- COGS fallback rows: `0/1658` (0.00%).
- Unresolved COGS rows: `0`.
- Unresolved SKU count: `0`.
- Ads mapping coverage: `0.00%`.
- Ads mapped/unmapped cost: `0.00` / `0.00`.

## External Reference Check

- Status: `skipped`
- Details: `{'status': 'skipped', 'reason': 'no external csv provided'}`
