# Business Insides Snapshot

- Generated at: `2026-02-13 22:03:14`
- As of date: `2026-02-13`
- Paid-capital snapshot date: `2026-02-12`
- Bank snapshot date: `2026-02-13`

## Capital Snapshot (KZT)

```text
+-----------------------------------+---------------+
| Metric                            | Value KZT     |
+-----------------------------------+---------------+
| Cash (actual, bank_accounts.yaml) | 2,003,917.38  |
| Inventory on-hand paid            | 5,643,300.00  |
| Inventory inbound paid            | 12,145,974.20 |
| Inventory on-delivery paid        | 436,800.00    |
| Total capital (paid truth)        | 20,229,991.58 |
| Inbound unpaid obligations        | 19,228,238.50 |
| Capital + unpaid inbound          | 39,458,230.08 |
+-----------------------------------+---------------+
```

## Performance Metrics (KZT)

```text
+--------------------------+------------+
| Metric                   | Value KZT  |
+--------------------------+------------+
| Avg 30d Net Rev          | 382,640.07 |
| Avg 30d COGS             | 225,735.62 |
| Avg 30d Profit           | 156,904.43 |
| Avg 30d Ads Spend        | 0.00       |
| Avg 30d Profit After Ads | 156,904.43 |
| Avg 7d Net Rev           | 468,690.59 |
| Avg 7d COGS              | 257,307.84 |
| Avg 7d Profit            | 211,382.73 |
| Avg 7d Ads Spend         | 0.00       |
| Avg 7d Profit After Ads  | 211,382.73 |
+--------------------------+------------+
```

## Last 7 Days Values (KZT)

```text
+------------+---------------+------------+------------+-----------+------------+------------------+
| Date       | Units Shipped | Net Rev    | COGS       | Ads Spend | Profit     | Profit After Ads |
+------------+---------------+------------+------------+-----------+------------+------------------+
| 2026-02-07 | 50            | 302,833.76 | 174,908.73 | 0.00      | 127,925.04 | 127,925.04       |
| 2026-02-08 | 48            | 493,849.31 | 276,166.77 | 0.00      | 217,682.50 | 217,682.50       |
| 2026-02-09 | 59            | 453,246.20 | 246,667.15 | 0.00      | 206,579.03 | 206,579.03       |
| 2026-02-10 | 66            | 515,144.81 | 272,407.46 | 0.00      | 242,737.35 | 242,737.35       |
| 2026-02-11 | 57            | 424,128.01 | 219,093.01 | 0.00      | 205,034.96 | 205,034.96       |
| 2026-02-12 | 72            | 556,143.80 | 304,063.94 | 0.00      | 252,079.83 | 252,079.83       |
| 2026-02-13 | 76            | 535,488.26 | 307,847.82 | 0.00      | 227,640.38 | 227,640.38       |
+------------+---------------+------------+------------+-----------+------------+------------------+
```

## Data Quality

- Sales source: `view_sales_line_truth` / `view_sales_daily_truth` (canonical interface over staging).
- COGS fallback rows: `0/1706` (0.00%).
- Unresolved COGS rows: `0`.
- Unresolved SKU count: `0`.
- Ads mapping coverage: `0.00%`.
- Ads mapped/unmapped cost: `0.00` / `0.00`.

## External Reference Check

- Status: `skipped`
- Details: `{'status': 'skipped', 'reason': 'no external csv provided'}`
