# Business Insides Snapshot

- Generated at: `2026-02-08 18:43:46`
- Latest cashflow date: `2026-02-08`
- Paid-capital truth snapshot date: `2026-02-07`
- Bank snapshot date: `2026-02-08`

## Capital Snapshot (KZT)

```text
+----------------------------------------------+---------------+
| Metric                                       | Value KZT     |
+----------------------------------------------+---------------+
| Cash (actual, bank_accounts.yaml)            | 2,003,917.38  |
| Inventory on-hand paid (Astana)              | 7,975,188.00  |
| Inventory inbound paid                       | 12,145,974.20 |
| Inventory on-delivery paid                   | 289,275.00    |
| Total capital (paid truth)                   | 22,414,354.58 |
| Inbound unpaid obligations (delayed payment) | 19,228,238.50 |
| Capital + unpaid inbound                     | 41,642,593.08 |
+----------------------------------------------+---------------+
```

## Performance Metrics (KZT)

```text
+-----------------+------------+
| Metric          | Value KZT  |
+-----------------+------------+
| Avg 30d Net Rev | 598,981.99 |
| Avg 30d COGS    | 142,452.40 |
| Avg 30d Profit  | 250,168.29 |
| Avg 7d Net Rev  | 427,311.00 |
| Avg 7d COGS     | 444,779.14 |
| Avg 7d Profit   | -17,468.14 |
+-----------------+------------+
```

## Last 7 Days Values (KZT)

```text
+------------+--------------+--------------+-------------+
| Date       | Net Rev      | COGS         | Profit      |
+------------+--------------+--------------+-------------+
| 2026-02-02 | 0.00         | 151,398.00   | -151,398.00 |
| 2026-02-03 | 0.00         | 116,532.00   | -116,532.00 |
| 2026-02-04 | 0.00         | 183,768.00   | -183,768.00 |
| 2026-02-05 | 2,364,694.20 | 2,379,156.00 | -14,461.80  |
| 2026-02-06 | 0.00         | 0.00         | 0.00        |
| 2026-02-07 | 512,935.86   | 231,525.00   | 281,410.86  |
| 2026-02-08 | 113,546.95   | 51,075.00    | 62,471.95   |
+------------+--------------+--------------+-------------+
```

## Notes

- Cash source: `config/bank_accounts.yaml`.
- On-hand inventory treated as fully paid (Astana).
- Inbound paid/unpaid split comes from `po_part` payment truth synced from `Inbound_calendar_V10.002.xlsx` (`PO_part_id_Totals`).
- Net Rev/COGS/Profit are from `fact_cashflow_daily` (`sales_accrued_kzt`, `cogs_kzt`, `profit_accrual_kzt`).
