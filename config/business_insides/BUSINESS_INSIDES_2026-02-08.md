# Business Insides Snapshot

- Generated at: `2026-02-09 18:27:40`
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
| Avg 30d COGS             | 170,250.29 |
| Avg 30d Profit           | 191,547.61 |
| Avg 30d Ads Spend        | 0.00       |
| Avg 30d Profit After Ads | 191,547.61 |
| Avg 7d Net Rev           | 347,085.04 |
| Avg 7d COGS              | 163,892.49 |
| Avg 7d Profit            | 183,192.51 |
| Avg 7d Ads Spend         | 0.00       |
| Avg 7d Profit After Ads  | 183,192.51 |
+--------------------------+------------+
```

## Last 7 Days Values (KZT)

```text
+------------+---------------+------------+------------+-----------+------------+------------------+
| Date       | Units Shipped | Net Rev    | COGS       | Ads Spend | Profit     | Profit After Ads |
+------------+---------------+------------+------------+-----------+------------+------------------+
| 2026-02-02 | 60            | 369,205.40 | 171,502.42 | 0.00      | 197,702.93 | 197,702.93       |
| 2026-02-03 | 49            | 294,228.04 | 136,926.68 | 0.00      | 157,301.35 | 157,301.35       |
| 2026-02-04 | 51            | 428,146.24 | 225,282.70 | 0.00      | 202,863.49 | 202,863.49       |
| 2026-02-05 | 41            | 235,971.05 | 105,554.11 | 0.00      | 130,416.91 | 130,416.91       |
| 2026-02-06 | 46            | 278,560.36 | 128,835.91 | 0.00      | 149,724.42 | 149,724.42       |
| 2026-02-07 | 50            | 327,356.33 | 136,835.22 | 0.00      | 190,521.11 | 190,521.11       |
| 2026-02-08 | 48            | 496,127.84 | 242,310.41 | 0.00      | 253,817.37 | 253,817.37       |
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
