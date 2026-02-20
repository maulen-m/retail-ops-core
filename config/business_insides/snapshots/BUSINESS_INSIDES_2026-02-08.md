# Business Insides Snapshot

- Generated at: `2026-02-09 20:51:45`
- As of date: `2026-02-08`
- Paid-capital snapshot date: `2026-02-08`
- Bank snapshot date: `2026-02-08`

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
| Avg 30d Net Rev          | 360,508.73 |
| Avg 30d COGS             | 211,076.62 |
| Avg 30d Profit           | 149,432.10 |
| Avg 30d Ads Spend        | 0.00       |
| Avg 30d Profit After Ads | 149,432.10 |
| Avg 7d Net Rev           | 346,635.51 |
| Avg 7d COGS              | 197,688.37 |
| Avg 7d Profit            | 148,947.13 |
| Avg 7d Ads Spend         | 0.00       |
| Avg 7d Profit After Ads  | 148,947.13 |
+--------------------------+------------+
```

## Last 7 Days Values (KZT)

```text
+------------+---------------+------------+------------+-----------+------------+------------------+
| Date       | Units Shipped | Net Rev    | COGS       | Ads Spend | Profit     | Profit After Ads |
+------------+---------------+------------+------------+-----------+------------+------------------+
| 2026-02-02 | 60            | 369,205.40 | 217,537.91 | 0.00      | 151,667.45 | 151,667.45       |
| 2026-02-03 | 49            | 294,228.04 | 167,936.65 | 0.00      | 126,291.38 | 126,291.38       |
| 2026-02-04 | 51            | 428,146.24 | 262,210.96 | 0.00      | 165,935.25 | 165,935.25       |
| 2026-02-05 | 41            | 235,971.05 | 130,985.17 | 0.00      | 104,985.89 | 104,985.89       |
| 2026-02-06 | 46            | 278,560.36 | 158,788.63 | 0.00      | 119,771.71 | 119,771.71       |
| 2026-02-07 | 50            | 326,488.18 | 174,908.73 | 0.00      | 151,579.46 | 151,579.46       |
| 2026-02-08 | 48            | 493,849.31 | 271,450.52 | 0.00      | 222,398.75 | 222,398.75       |
+------------+---------------+------------+------------+-----------+------------+------------------+
```

## Data Quality

- Sales source: `view_sales_line_truth` / `view_sales_daily_truth` (canonical interface over staging).
- COGS fallback rows: `0/1645` (0.00%).
- Unresolved COGS rows: `0`.
- Unresolved SKU count: `0`.
- Ads mapping coverage: `0.00%`.
- Ads mapped/unmapped cost: `0.00` / `0.00`.

## External Reference Check

- Status: `skipped`
- Details: `{'status': 'skipped', 'reason': 'no external csv provided'}`
