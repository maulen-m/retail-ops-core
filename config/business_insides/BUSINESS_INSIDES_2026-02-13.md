# Business Insides Snapshot

- Generated at: `2026-02-13 21:47:29`
- As of date: `2026-02-13`
- Paid-capital snapshot date: `2026-02-09`
- Bank snapshot date: `2026-02-13`

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
| Avg 30d Net Rev          | 368,868.03 |
| Avg 30d COGS             | 219,846.33 |
| Avg 30d Profit           | 149,021.67 |
| Avg 30d Ads Spend        | 0.00       |
| Avg 30d Profit After Ads | 149,021.67 |
| Avg 7d Net Rev           | 438,453.28 |
| Avg 7d COGS              | 241,234.32 |
| Avg 7d Profit            | 197,218.94 |
| Avg 7d Ads Spend         | 0.00       |
| Avg 7d Profit After Ads  | 197,218.94 |
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
| 2026-02-10 | 65            | 503,883.84 | 267,194.64 | 0.00      | 236,689.20 | 236,689.20       |
| 2026-02-11 | N/A           | N/A        | N/A        | 0.00      | N/A        | N/A              |
| 2026-02-12 | N/A           | N/A        | N/A        | 0.00      | N/A        | N/A              |
| 2026-02-13 | N/A           | N/A        | N/A        | 0.00      | N/A        | N/A              |
+------------+---------------+------------+------------+-----------+------------+------------------+
```

## Data Quality

- Sales source: `view_sales_line_truth` / `view_sales_daily_truth` (canonical interface over staging).
- COGS fallback rows: `0/1501` (0.00%).
- Unresolved COGS rows: `0`.
- Unresolved SKU count: `0`.
- Ads mapping coverage: `0.00%`.
- Ads mapped/unmapped cost: `0.00` / `0.00`.

## External Reference Check

- Status: `skipped`
- Details: `{'status': 'skipped', 'reason': 'no external csv provided'}`
