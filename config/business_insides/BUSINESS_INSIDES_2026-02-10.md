# Business Insides Snapshot

- Generated at: `2026-02-11 20:33:12`
- As of date: `2026-02-10`
- Paid-capital snapshot date: `2026-02-10`
- Bank snapshot date: `2026-02-10`

## Capital Snapshot (KZT)

```text
+-----------------------------------+---------------+
| Metric                            | Value KZT     |
+-----------------------------------+---------------+
| Cash (actual, bank_accounts.yaml) | 2,003,917.38  |
| Inventory on-hand paid            | 6,259,032.00  |
| Inventory inbound paid            | 12,145,974.20 |
| Inventory on-delivery paid        | 435,150.00    |
| Total capital (paid truth)        | 20,844,073.58 |
| Inbound unpaid obligations        | 19,228,238.50 |
| Capital + unpaid inbound          | 40,072,312.08 |
+-----------------------------------+---------------+
```

## Performance Metrics (KZT)

```text
+--------------------------+------------+
| Metric                   | Value KZT  |
+--------------------------+------------+
| Avg 30d Net Rev          | 356,737.07 |
| Avg 30d COGS             | 136,216.15 |
| Avg 30d Profit           | 104,594.75 |
| Avg 30d Ads Spend        | 0.00       |
| Avg 30d Profit After Ads | 104,594.75 |
| Avg 7d Net Rev           | 356,135.26 |
| Avg 7d COGS              | 147,841.76 |
| Avg 7d Profit            | 129,835.68 |
| Avg 7d Ads Spend         | 0.00       |
| Avg 7d Profit After Ads  | 129,835.68 |
+--------------------------+------------+
```

## Last 7 Days Values (KZT)

```text
+------------+---------------+------------+------------+-----------+------------+------------------+
| Date       | Units Shipped | Net Rev    | COGS       | Ads Spend | Profit     | Profit After Ads |
+------------+---------------+------------+------------+-----------+------------+------------------+
| 2026-02-04 | 50            | 347,646.42 | 125,598.47 | 0.00      | 109,212.20 | 109,212.20       |
| 2026-02-05 | 41            | 241,396.26 | 100,851.15 | 0.00      | 86,454.26  | 86,454.26        |
| 2026-02-06 | 46            | 278,560.36 | 129,597.86 | 0.00      | 99,666.97  | 99,666.97        |
| 2026-02-07 | 50            | 306,631.31 | 151,363.18 | 0.00      | 111,246.02 | 111,246.02       |
| 2026-02-08 | 47            | 329,922.34 | 130,843.92 | 0.00      | 133,636.35 | 133,636.35       |
| 2026-02-09 | 59            | 462,468.96 | 190,157.83 | 0.00      | 173,518.29 | 173,518.29       |
| 2026-02-10 | 66            | 526,321.15 | 206,479.92 | 0.00      | 195,115.70 | 195,115.70       |
+------------+---------------+------------+------------+-----------+------------+------------------+
```

## Data Quality

- Sales source: `view_sales_line_truth` / `view_sales_daily_truth` (canonical interface over staging).
- COGS fallback rows: `0/1659` (0.00%).
- Unresolved COGS rows: `475`.
- Unresolved SKU count: `1`.
- Ads mapping coverage: `0.00%`.
- Ads mapped/unmapped cost: `0.00` / `0.00`.

## External Reference Check

- Status: `skipped`
- Details: `{'status': 'skipped', 'reason': 'no external csv provided'}`
