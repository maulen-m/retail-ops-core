# Business Insides Snapshot

- Generated at: `2026-07-02 21:04:06`
- As of date: `2026-07-02`
- Paid-capital snapshot date: `2026-06-29`
- Bank snapshot date: `2026-07-02`

## Capital Snapshot (KZT)

```text
+-----------------------------------+---------------+
| Metric                            | Value KZT     |
+-----------------------------------+---------------+
| Cash (actual, bank_accounts.yaml) | 2,594,680.00  |
| Inventory on-hand paid            | 21,157,460.67 |
| Inventory inbound paid            | 29,384,389.71 |
| Inventory on-delivery paid        | 679,246.99    |
| Total capital (paid truth)        | 53,815,777.37 |
| Inbound unpaid obligations        | 3,175,272.00  |
| Capital + unpaid inbound          | 56,991,049.37 |
+-----------------------------------+---------------+
```

## Performance Metrics (KZT)

```text
+--------------------------+------------+
| Metric                   | Value KZT  |
+--------------------------+------------+
| Avg 30d Net Rev          | 206,707.30 |
| Avg 30d COGS             | N/A        |
| Avg 30d Profit           | N/A        |
| Avg 30d Ads Spend        | 4,486.73   |
| Avg 30d Profit After Ads | N/A        |
| Avg 7d Net Rev           | 206,940.86 |
| Avg 7d COGS              | N/A        |
| Avg 7d Profit            | N/A        |
| Avg 7d Ads Spend         | 0.00       |
| Avg 7d Profit After Ads  | N/A        |
+--------------------------+------------+
```

## Last 7 Days Values (KZT)

```text
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
| Date       | Units Delivered (COMPLETED) | Net Rev    | COGS       | Ads Spend | Profit     | Profit After Ads |
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
| 2026-06-26 | 14                          | 106,853.00 | 36,553.84  | 0.00      | 61,236.16  | 61,236.16        |
| 2026-06-27 | 17                          | 165,369.00 | 62,874.27  | 0.00      | 102,494.73 | 102,494.73       |
| 2026-06-28 | 26                          | 188,558.00 | 84,260.90  | 0.00      | 104,297.10 | 104,297.10       |
| 2026-06-29 | 32                          | 314,724.00 | 122,873.94 | 0.00      | 191,850.06 | 191,850.06       |
| 2026-06-30 | 28                          | 258,152.00 | 113,263.55 | 0.00      | 144,888.45 | 144,888.45       |
| 2026-07-01 | 25                          | 179,229.00 | 87,420.11  | 0.00      | 91,808.89  | 91,808.89        |
| 2026-07-02 | 32                          | 235,701.00 | 113,248.53 | 0.00      | 122,452.47 | 122,452.47       |
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
```

## Sales Truth Freshness

- Latest observed sale date (truth): `2026-07-02`
- Freshness lag (days): `0`
- Freshness status: `fresh`
- Observed rows in last 7 calendar days: `7`

## Latest Observed Sales Days (Truth)

```text
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
| Date       | Units Delivered (COMPLETED) | Net Rev    | COGS       | Ads Spend | Profit     | Profit After Ads |
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
| 2026-06-26 | 14                          | 106,853.00 | 36,553.84  | 0.00      | 61,236.16  | 61,236.16        |
| 2026-06-27 | 17                          | 165,369.00 | 62,874.27  | 0.00      | 102,494.73 | 102,494.73       |
| 2026-06-28 | 26                          | 188,558.00 | 84,260.90  | 0.00      | 104,297.10 | 104,297.10       |
| 2026-06-29 | 32                          | 314,724.00 | 122,873.94 | 0.00      | 191,850.06 | 191,850.06       |
| 2026-06-30 | 28                          | 258,152.00 | 113,263.55 | 0.00      | 144,888.45 | 144,888.45       |
| 2026-07-01 | 25                          | 179,229.00 | 87,420.11  | 0.00      | 91,808.89  | 91,808.89        |
| 2026-07-02 | 32                          | 235,701.00 | 113,248.53 | 0.00      | 122,452.47 | 122,452.47       |
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
```

## Waybill-State Shipment Snapshot

- Snapshot status: `available`
- Cache file: `~/Docs/Autonomous_business/excel_ui/ActiveOrders/waybills/_waybill_selection_orders.json`
- Target date in cache: `2026-07-02`
- Include overdue: `True`
- Mode all_dates: `False`

```text
+-----------+------------------------------------+------------------------+
| Store     | Orders Shipped (Waybill Selection) | Units Shipped (DB qty) |
+-----------+------------------------------------+------------------------+
| STOREB    | 13                                 | 13                     |
| ACMEWEAR   | 9                                  | 9                      |
| UNIVERSAL | 12                                 | 14                     |
| TOTAL     | 34                                 | 36                     |
+-----------+------------------------------------+------------------------+
```

## Ocean Drop Provenance

- Anchor configured: `true`
- Anchor registry: `~/Docs/Autonomous_business/config/anchors/ocean_drop_sales_anchor.json`
- Anchor path: `~/Docs/Web_automation/exports/archive_orders_mapped/20260304_013732/ArchiveOrders_ALL_STORES_mapped_20260304_013732_final.csv`
- Anchor sha256: `d047707e94378cfe623cad51c8dec4f3913300c78ee3c7995fe69749fdcd9388` (computed: `d047707e94378cfe623cad51c8dec4f3913300c78ee3c7995fe69749fdcd9388`)
- Anchor as_of_end: `2026-03-03`
- Transaction date mode: `delivered_status_date`
- Anchor source tag: `web_automation_archive_mapped_final`

## Data Quality

- Sales source: `view_sales_line_truth / view_sales_daily_truth (canonical interface over staging)`.
- Metric definition: `Units Delivered (COMPLETED)` come from canonical sales truth views.
- Metric definition: `Orders/Units Shipped (Waybill Selection)` come from waybill selection cache + DB quantities.
- COGS fallback rows: `23/701` (3.28%).
- Unresolved COGS rows: `1`.
- Unresolved SKU count: `1`.
- Economics volatility window (days): `14`.
- Economics missing days (COGS/profit): `0` (none).
- Economics missing nonvolatile days: `0` (none).
- Profit publication locked: `true`.
- Ads source status: `available` (reason: `canonical_ads_truth`).
- Ads mapping coverage: `100.00%`.
- Ads mapped/unmapped cost: `134,602.00` / `0.00`.
- ArchiveOrders source status: `disabled` (reason: `disabled_by_default`).
- ArchiveOrders files used: `0`.

## External Reference Check

- Status: `skipped`
- Details: `{'status': 'skipped', 'reason': 'strict_not_requested', 'anchor_configured': True, 'anchor_registry': '~/Docs/Autonomous_business/config/anchors/ocean_drop_sales_anchor.json'}`

