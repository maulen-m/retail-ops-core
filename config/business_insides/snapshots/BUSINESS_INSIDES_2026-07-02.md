# Business Insides Snapshot

- Generated at: `2026-07-03 21:29:56`
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
| Avg 30d Net Rev          | 185,795.31 |
| Avg 30d COGS             | N/A        |
| Avg 30d Profit           | N/A        |
| Avg 30d Ads Spend        | 20,911.77  |
| Avg 30d Profit After Ads | N/A        |
| Avg 7d Net Rev           | 284,387.07 |
| Avg 7d COGS              | N/A        |
| Avg 7d Profit            | N/A        |
| Avg 7d Ads Spend         | 32,983.00  |
| Avg 7d Profit After Ads  | N/A        |
+--------------------------+------------+
```

## Last 7 Days Values (KZT)

```text
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
| Date       | Units Delivered (COMPLETED) | Net Rev    | COGS       | Ads Spend | Profit     | Profit After Ads |
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
| 2026-06-26 | 29                          | 218,682.98 | 90,690.81  | 30,729.00 | 103,064.11 | 72,335.11        |
| 2026-06-27 | 23                          | 177,209.18 | 62,964.54  | 34,194.00 | 88,300.02  | 54,106.02        |
| 2026-06-28 | 21                          | 155,376.05 | 68,443.18  | 30,395.00 | 65,238.80  | 34,843.80        |
| 2026-06-29 | 22                          | 132,555.47 | 58,839.78  | 33,071.00 | 58,711.48  | 25,640.48        |
| 2026-06-30 | 27                          | 284,573.00 | N/A        | 36,213.00 | N/A        | N/A              |
| 2026-07-01 | 25                          | 198,866.00 | N/A        | 31,777.00 | N/A        | N/A              |
| 2026-07-02 | 142                         | 823,446.82 | 370,082.06 | 34,502.00 | 376,246.71 | 341,744.71       |
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
| 2026-06-26 | 29                          | 218,682.98 | 90,690.81  | 30,729.00 | 103,064.11 | 72,335.11        |
| 2026-06-27 | 23                          | 177,209.18 | 62,964.54  | 34,194.00 | 88,300.02  | 54,106.02        |
| 2026-06-28 | 21                          | 155,376.05 | 68,443.18  | 30,395.00 | 65,238.80  | 34,843.80        |
| 2026-06-29 | 22                          | 132,555.47 | 58,839.78  | 33,071.00 | 58,711.48  | 25,640.48        |
| 2026-06-30 | 27                          | 284,573.00 | N/A        | 36,213.00 | N/A        | N/A              |
| 2026-07-01 | 25                          | 198,866.00 | N/A        | 31,777.00 | N/A        | N/A              |
| 2026-07-02 | 142                         | 823,446.82 | 370,082.06 | 34,502.00 | 376,246.71 | 341,744.71       |
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
```

## Waybill-State Shipment Snapshot

- Snapshot status: `as_of_mismatch`
- Cache file: `~/Docs/Autonomous_business/excel_ui/ActiveOrders/waybills/_waybill_selection_orders.json`
- Target date in cache: `2026-07-03`
- Include overdue: `True`
- Mode all_dates: `False`
- Waybill cache is unavailable for this as_of day; shipment metrics are not decision-grade.

## Ocean Drop Provenance

- Anchor configured: `true`
- Anchor registry: `~/Docs/Autonomous_business/config/anchors/ocean_drop_sales_anchor.json`
- Anchor path: `~/Docs/Web_automation/exports/archive_orders_mapped/20260304_013732/ArchiveOrders_ALL_STORES_mapped_20260304_013732_final.csv`
- Anchor sha256: `d047707e94378cfe623cad51c8dec4f3913300c78ee3c7995fe69749fdcd9388` (computed: `d047707e94378cfe623cad51c8dec4f3913300c78ee3c7995fe69749fdcd9388`)
- Anchor as_of_end: `2026-03-03`
- Transaction date mode: `delivered_status_date`
- Anchor source tag: `web_automation_archive_mapped_final`

## Data Quality

- Sales source: `view_sales_line_truth / view_sales_daily_truth (canonical interface over staging) + fact_orders_kaspi COMPLETED revenue-only fallback (days added: 2)`.
- Metric definition: `Units Delivered (COMPLETED)` come from canonical sales truth views.
- Metric definition: `Orders/Units Shipped (Waybill Selection)` come from waybill selection cache + DB quantities.
- COGS fallback rows: `26/691` (3.76%).
- Unresolved COGS rows: `78`.
- Unresolved SKU count: `1`.
- Economics volatility window (days): `14`.
- Economics missing days (COGS/profit): `2` (2026-06-30, 2026-07-01).
- Economics missing nonvolatile days: `0` (none).
- Profit publication locked: `true`.
- Ads source status: `available` (reason: `canonical_ads_truth`).
- Ads mapping coverage: `100.00%`.
- Ads mapped/unmapped cost: `627,353.00` / `0.00`.
- ArchiveOrders source status: `disabled` (reason: `disabled_by_default`).
- ArchiveOrders files used: `0`.

## External Reference Check

- Status: `skipped`
- Details: `{'status': 'skipped', 'reason': 'strict_not_requested', 'anchor_configured': True, 'anchor_registry': '~/Docs/Autonomous_business/config/anchors/ocean_drop_sales_anchor.json'}`

