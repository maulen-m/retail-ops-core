# Business Insides Snapshot

- Generated at: `2026-02-10 01:13:09`
- As of date: `2026-02-10`
- Paid-capital snapshot date: `2026-02-08`
- Bank snapshot date: `2026-02-10`

## Capital Snapshot (KZT)

```text
+-----------------------------------+---------------+
| Metric                            | Value KZT     |
+-----------------------------------+---------------+
| Cash (actual, bank_accounts.yaml) | 2,003,917.38  |
| Inventory on-hand paid            | 7,263,594.00  |
| Inventory inbound paid            | 12,145,974.20 |
| Inventory on-delivery paid        | 380,250.00    |
| Total capital (paid truth)        | 21,793,735.58 |
| Inbound unpaid obligations        | 19,228,238.50 |
| Capital + unpaid inbound          | 41,021,974.08 |
+-----------------------------------+---------------+
```

## Performance Metrics (KZT)

```text
+--------------------------+------------+
| Metric                   | Value KZT  |
+--------------------------+------------+
| Avg 30d Net Rev          | 365,717.09 |
| Avg 30d COGS             | 213,801.99 |
| Avg 30d Profit           | 151,915.08 |
| Avg 30d Ads Spend        | 0.00       |
| Avg 30d Profit After Ads | 151,915.08 |
| Avg 7d Net Rev           | 365,434.49 |
| Avg 7d COGS              | 206,401.40 |
| Avg 7d Profit            | 159,033.07 |
| Avg 7d Ads Spend         | 0.00       |
| Avg 7d Profit After Ads  | 159,033.07 |
+--------------------------+------------+
```

## Last 7 Days Values (KZT)

```text
+------------+---------------+------------+------------+-----------+------------+------------------+
| Date       | Units Shipped | Net Rev    | COGS       | Ads Spend | Profit     | Profit After Ads |
+------------+---------------+------------+------------+-----------+------------+------------------+
| 2026-02-04 | 51            | 428,146.24 | 262,210.96 | 0.00      | 165,935.25 | 165,935.25       |
| 2026-02-05 | 41            | 235,971.05 | 130,985.17 | 0.00      | 104,985.89 | 104,985.89       |
| 2026-02-06 | 46            | 278,560.36 | 158,788.63 | 0.00      | 119,771.71 | 119,771.71       |
| 2026-02-07 | 50            | 302,833.76 | 174,908.73 | 0.00      | 127,925.04 | 127,925.04       |
| 2026-02-08 | 48            | 493,849.31 | 271,450.52 | 0.00      | 222,398.75 | 222,398.75       |
| 2026-02-09 | 59            | 453,246.20 | 240,064.40 | 0.00      | 213,181.78 | 213,181.78       |
| 2026-02-10 | N/A           | N/A        | N/A        | 0.00      | N/A        | N/A              |
+------------+---------------+------------+------------+-----------+------------+------------------+
```

## Data Quality

- Sales source: `view_sales_line_truth` / `view_sales_daily_truth` (canonical interface over staging).
- COGS fallback rows: `0/1599` (0.00%).
- Unresolved COGS rows: `0`.
- Unresolved SKU count: `0`.
- Ads mapping coverage: `0.00%`.
- Ads mapped/unmapped cost: `0.00` / `0.00`.

## External Reference Check

- Status: `skipped`
- Details: `{'status': 'skipped', 'reason': 'no external csv provided'}`
