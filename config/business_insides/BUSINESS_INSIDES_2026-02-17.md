# Business Insides Snapshot

- Generated at: `2026-02-17 00:13:28`
- As of date: `2026-02-17`
- Paid-capital snapshot date: `2026-02-13`
- Bank snapshot date: `2026-02-17`

## Capital Snapshot (KZT)

```text
+-----------------------------------+---------------+
| Metric                            | Value KZT     |
+-----------------------------------+---------------+
| Cash (actual, bank_accounts.yaml) | 2,003,917.38  |
| Inventory on-hand paid            | 6,132,048.00  |
| Inventory inbound paid            | 12,145,974.20 |
| Inventory on-delivery paid        | 416,175.00    |
| Total capital (paid truth)        | 20,698,114.58 |
| Inbound unpaid obligations        | 19,228,238.50 |
| Capital + unpaid inbound          | 39,926,353.08 |
+-----------------------------------+---------------+
```

## Performance Metrics (KZT)

```text
+--------------------------+------------+
| Metric                   | Value KZT  |
+--------------------------+------------+
| Avg 30d Net Rev          | 372,644.22 |
| Avg 30d COGS             | 222,246.47 |
| Avg 30d Profit           | 150,397.72 |
| Avg 30d Ads Spend        | 0.00       |
| Avg 30d Profit After Ads | 150,397.72 |
| Avg 7d Net Rev           | 0.00       |
| Avg 7d COGS              | 0.00       |
| Avg 7d Profit            | 0.00       |
| Avg 7d Ads Spend         | 0.00       |
| Avg 7d Profit After Ads  | 0.00       |
+--------------------------+------------+
```

## Last 7 Days Values (KZT)

```text
+------------+---------------+---------+------+-----------+--------+------------------+
| Date       | Units Shipped | Net Rev | COGS | Ads Spend | Profit | Profit After Ads |
+------------+---------------+---------+------+-----------+--------+------------------+
| 2026-02-11 | N/A           | N/A     | N/A  | 0.00      | N/A    | N/A              |
| 2026-02-12 | N/A           | N/A     | N/A  | 0.00      | N/A    | N/A              |
| 2026-02-13 | N/A           | N/A     | N/A  | 0.00      | N/A    | N/A              |
| 2026-02-14 | N/A           | N/A     | N/A  | 0.00      | N/A    | N/A              |
| 2026-02-15 | N/A           | N/A     | N/A  | 0.00      | N/A    | N/A              |
| 2026-02-16 | N/A           | N/A     | N/A  | 0.00      | N/A    | N/A              |
| 2026-02-17 | N/A           | N/A     | N/A  | 0.00      | N/A    | N/A              |
+------------+---------------+---------+------+-----------+--------+------------------+
```

## Data Quality

- Sales source: `view_sales_line_truth` / `view_sales_daily_truth` (canonical interface over staging).
- COGS fallback rows: `0/1293` (0.00%).
- Unresolved COGS rows: `0`.
- Unresolved SKU count: `0`.
- Ads mapping coverage: `0.00%`.
- Ads mapped/unmapped cost: `0.00` / `0.00`.

## External Reference Check

- Status: `skipped`
- Details: `{'status': 'skipped', 'reason': 'no external csv provided'}`
