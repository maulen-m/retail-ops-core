# Business Insides Snapshot

- Generated at: `2026-03-03 14:58:30`
- As of date: `2026-02-12`
- Paid-capital snapshot date: `2026-02-09`
- Bank snapshot date: `2026-02-12`

## Capital Snapshot (KZT)

```text
+-----------------------------------+---------------+
| Metric                            | Value KZT     |
+-----------------------------------+---------------+
| Cash (actual, bank_accounts.yaml) | 467,804.38    |
| Inventory on-hand paid            | 6,407,856.00  |
| Inventory inbound paid            | 18,407,100.58 |
| Inventory on-delivery paid        | 415,350.00    |
| Total capital (paid truth)        | 25,698,110.96 |
| Inbound unpaid obligations        | 12,967,110.00 |
| Capital + unpaid inbound          | 38,665,220.96 |
+-----------------------------------+---------------+
```

## Performance Metrics (KZT)

```text
+--------------------------+------------+
| Metric                   | Value KZT  |
+--------------------------+------------+
| Avg 30d Net Rev          | 438,022.71 |
| Avg 30d COGS             | N/A        |
| Avg 30d Profit           | N/A        |
| Avg 30d Ads Spend        | N/A        |
| Avg 30d Profit After Ads | N/A        |
| Avg 7d Net Rev           | 420,000.00 |
| Avg 7d COGS              | N/A        |
| Avg 7d Profit            | N/A        |
| Avg 7d Ads Spend         | N/A        |
| Avg 7d Profit After Ads  | N/A        |
+--------------------------+------------+
```

## Last 7 Days Values (KZT)

```text
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
| Date       | Units Delivered (COMPLETED) | Net Rev    | COGS       | Ads Spend | Profit     | Profit After Ads |
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
| 2026-02-06 | 48                          | 373,814.00 | 169,145.75 | N/A       | 204,668.25 | N/A              |
| 2026-02-07 | 36                          | 272,005.00 | 120,932.72 | N/A       | 151,072.28 | N/A              |
| 2026-02-08 | 45                          | 355,353.00 | 158,981.90 | N/A       | 196,371.10 | N/A              |
| 2026-02-09 | 61                          | 496,873.00 | 219,350.61 | N/A       | 277,522.39 | N/A              |
| 2026-02-10 | 43                          | 603,796.00 | 272,888.16 | N/A       | 330,907.84 | N/A              |
| 2026-02-11 | N/A                         | N/A        | N/A        | N/A       | N/A        | N/A              |
| 2026-02-12 | 49                          | 418,159.00 | 180,113.00 | N/A       | 238,046.00 | N/A              |
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
```

## Sales Truth Freshness

- Latest observed sale date (truth): `2026-02-12`
- Freshness lag (days): `0`
- Freshness status: `fresh`
- Observed rows in last 7 calendar days: `6`

## Latest Observed Sales Days (Truth)

```text
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
| Date       | Units Delivered (COMPLETED) | Net Rev    | COGS       | Ads Spend | Profit     | Profit After Ads |
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
| 2026-02-05 | 52                          | 497,821.00 | 255,822.29 | N/A       | 241,998.71 | N/A              |
| 2026-02-06 | 48                          | 373,814.00 | 169,145.75 | N/A       | 204,668.25 | N/A              |
| 2026-02-07 | 36                          | 272,005.00 | 120,932.72 | N/A       | 151,072.28 | N/A              |
| 2026-02-08 | 45                          | 355,353.00 | 158,981.90 | N/A       | 196,371.10 | N/A              |
| 2026-02-09 | 61                          | 496,873.00 | 219,350.61 | N/A       | 277,522.39 | N/A              |
| 2026-02-10 | 43                          | 603,796.00 | 272,888.16 | N/A       | 330,907.84 | N/A              |
| 2026-02-12 | 49                          | 418,159.00 | 180,113.00 | N/A       | 238,046.00 | N/A              |
+------------+-----------------------------+------------+------------+-----------+------------+------------------+
```

## Waybill-State Shipment Snapshot

- Snapshot status: `available_shipped_truth`
- Cache file: `~/Docs/Autonomous_business/exports/validation/shipped_truth_crm_waybill/2026-02-01_to_2026-03-01/summary.json`
- Target date in cache: `2026-02-12`
- Include overdue: `None`
- Mode all_dates: `None`

```text
+-----------+------------------------------------+------------------------+
| Store     | Orders Shipped (Waybill Selection) | Units Shipped (DB qty) |
+-----------+------------------------------------+------------------------+
| STORE-B   | 34                                 | 34                     |
| AcmeWear   | 15                                 | 15                     |
| Universal | 18                                 | 18                     |
| TOTAL     | 67                                 | 67                     |
+-----------+------------------------------------+------------------------+
```

## Ocean Drop Provenance

- Anchor configured: `true`
- Anchor registry: `~/Docs/Autonomous_business/config/anchors/ocean_drop_sales_anchor.json`
- Anchor path: `~/Docs/Autonomous_business/exports/ocean_drop/20260228_214554/ArchiveOrders_ALL_STORES_ocean_drop_20260228_214554.csv`
- Anchor sha256: `8381f979e2863009f6d0ff92b469764260f5e34047dadfaf03eaa1e91e6b604d` (computed: `8381f979e2863009f6d0ff92b469764260f5e34047dadfaf03eaa1e91e6b604d`)
- Anchor as_of_end: `2026-02-26`
- Transaction date mode: `delivered_status_date`
- Anchor source tag: `merged_api_ui_statusdate`

## Data Quality

- Sales source: `view_sales_line_truth / view_sales_daily_truth (canonical interface over staging) + fact_orders_kaspi COMPLETED revenue-only fallback (days added: 1)`.
- Metric definition: `Units Delivered (COMPLETED)` come from canonical sales truth views.
- Metric definition: `Orders/Units Shipped (Waybill Selection)` come from waybill selection cache + DB quantities.
- COGS fallback rows: `0/1389` (0.00%).
- Unresolved COGS rows: `0`.
- Unresolved SKU count: `0`.
- Economics volatility window (days): `14`.
- Economics missing days (COGS/profit): `1` (2026-01-14).
- Economics missing nonvolatile days: `1` (2026-01-14).
- Profit publication locked: `true`.
- Ads source status: `unavailable` (reason: `stale`).
- Ads mapping coverage: `N/A`.
- Ads mapped/unmapped cost: `N/A` / `N/A`.
- ArchiveOrders source status: `disabled` (reason: `disabled_by_default`).
- ArchiveOrders files used: `0`.

## External Reference Check

- Status: `skipped`
- Details: `{'status': 'skipped', 'reason': 'strict_not_requested', 'anchor_configured': True, 'anchor_registry': '~/Docs/Autonomous_business/config/anchors/ocean_drop_sales_anchor.json'}`

