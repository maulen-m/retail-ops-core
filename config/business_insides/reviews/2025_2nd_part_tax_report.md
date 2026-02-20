# 2025 2nd Part Tax Report

## Scope
- Sales source: `view_sales_line_truth` in `db/app.db`.
- Ads source: `ads_campaign_product_daily_current` (`SUM(cost)` by date).
- H2 reference period: `2025-07-01`..`2025-12-31`.
- Government reporting deadline: `2026-02-15`.
- Payment deadline: `2026-02-25`.

## H2 Context Totals
- Orders: `6,767`
- Units: `6,947`
- Net revenue: `53,870,105.37 KZT`
- COGS: `34,008,032.58 KZT`
- Ads: `248,015.00 KZT`
- Profit after ads: `19,470,541.71 KZT`

## Universal Net Revenue Split (Requested)

```text
+--------------+------------------------+---------------+--------------+----------------------------------+
| store_scope  | period                 | net_rev_kzt   | tax_3pct_kzt | status                           |
+--------------+------------------------+---------------+--------------+----------------------------------+
| UNIVERSAL_Q3 | 2025-07-01..2025-09-30 | 11,663,192.30 | 349,895.77   | REFERENCE_SPLIT                  |
| UNIVERSAL_Q4 | 2025-10-01..2025-12-31 | 15,910,446.52 | 477,313.40   | IN_MAIN_REPORT_PAYABLE           |
+--------------+------------------------+---------------+--------------+----------------------------------+
```

## Main Tax Filing Table (Per Store)

```text
+---------------------+-----------------------------+---------------+--------------+----------------------+
| store_code          | period_used                 | net_rev_kzt   | tax_3pct_kzt | payment_status       |
+---------------------+-----------------------------+---------------+--------------+----------------------+
| UNIVERSAL           | Q4 (2025-10-01..2025-12-31) | 15,910,446.52 | 477,313.40   | PAYABLE              |
| ACMEWEAR             | H2 (2025-07-01..2025-12-31) | 15,613,157.66 | 468,394.73   | PAYABLE              |
| STOREB              | H2 (2025-07-01..2025-12-31) | 8,982,176.84  | 269,465.31   | PAYABLE              |
| 11KZ                | H2 (2025-07-01..2025-12-31) | 1,701,132.04  | 51,033.96    | PAYABLE              |
| MELVIS              | H2 (2025-07-01..2025-12-31) | 0.00          | 0.00         | PAYABLE              |
| OVERALL_DECLARED    |                             | 42,206,913.06 | 1,266,207.40 | DECLARED             |
| OVERALL_PAYABLE_NOW |                             | 42,206,913.06 | 1,266,207.40 | TO_PAY_BY_2026-02-25 |
+---------------------+-----------------------------+---------------+--------------+----------------------+
```

## Important Notes
- Main filing includes `UNIVERSAL` only for Q4 (`2025-10-01..2025-12-31`).
- Other stores (`ACMEWEAR`, `STOREB`, `11KZ`, `MELVIS`) are included for full H2 (`2025-07-01..2025-12-31`).
- `UNIVERSAL Q3` is already paid and shown only as split reference.
- `UNIVERSAL Q4` is payable in this report.
- Ads cost is deducted from profit only; tax is always 3% of full net revenue.
- Accounting cashflow schedule event added: `2026-02-24 10:00 (+05:00)`, ref_id `TAX_2025_H2_PAY_20260224_1000`, amount `-1,266,207.40 KZT`.

- Generated at: `2026-02-11 13:20:00`
