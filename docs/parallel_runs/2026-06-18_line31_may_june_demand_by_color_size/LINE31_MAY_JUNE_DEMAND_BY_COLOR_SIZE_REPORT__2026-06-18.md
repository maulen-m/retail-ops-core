# LINE31 May-June Demand By Color/Size Report (2026-06-18)

**Decision-grade banner: YELLOW.** Useful for directional PO1B sizing/color discussion, but not GREEN: fact_orders_kaspi has LINE31 intake through 2026-06-17 and LINE31 import/update through 2026-06-18, while sales_fact_v2/view_sales_line_truth stop at 2026-06-16/2026-06-16 and LINE31 status-event evidence in-window stops at 2026-06-15. Cancellation reasons/no-stock reasons are not canonical enough to verify owner-reported 3XL cancels.

**Read-only boundary:** DB opened with SQLite `mode=ro` plus `PRAGMA query_only=ON`; no `--apply`, no write-enable env vars, no marketplace/CRM/Sourcing/Web_automation writes. Only this markdown report and CSV sidecars were written.

## Executive Takeaways

- Primary window: `2026-05-24` through `2026-06-18` inclusive; timezone/date interpretation: Asia/Almaty / GMT+5 business dates as stored in AB date fields.
- LINE31 gross order demand found in `fact_orders_kaspi`: **48 line-units across 47 distinct orders**.
- Operational shipped/fulfilled bucket (`COMPLETED` or `SHIPPED` in `fact_orders_kaspi`): **42 line-units across 42 distinct orders**.
- Cancelled/returned/open-not-shipped bucket (`CANCELLED`, `RETURNED`, `READY`, `ACCEPTED`): **6 line-units across 5 distinct orders**.
- Economic fulfilled cross-check from `view_sales_line_truth`: **33.0 units across 33 orders**, latest LINE31 sale date `2026-06-16`; this is lower/staler than operational order truth, so it is treated as corroboration rather than the only demand source.
- Larger effective sizes are materially stronger than the old “M strongest” assumption in this window: `L+XL+2XL+3XL+` = **37/48 (77.1%)**; `XL+2XL` alone = **28/48 (58.3%)**; `M` = **6/48 (12.5%)**.
- `3XL` evidence in AB for this window: **0 units**. Owner-reported approx five cancelled `3XL` orders are **not visible / not confirmed** in the AB sources inspected.

## Source Freshness

| Surface                       | Freshness / Count                                                                         | Decision Use                                                   |
| ----------------------------- | ----------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| fact_orders_kaspi             | all latest created=2026-06-18, updated=2026-06-18, imported=2026-06-18; rows=35442        | Primary operational order-demand source                        |
| fact_orders_kaspi LINE31         | latest created=2026-06-17, updated=2026-06-18, imported=2026-06-18; all-date LINE31 rows=139 | Current enough for directional intake through Jun 17/18 import |
| sales_fact_v2 LINE31             | latest order_date=2026-06-16; all-date LINE31 rows=136                                       | Downstream sales/status corroboration, stale for Jun 17-18     |
| view_sales_line_truth LINE31     | latest sale_date=2026-06-16; all-date LINE31 rows=113                                        | Economic fulfilled cross-check, stale for last 48h             |
| order_status_event LINE31 window | latest event_ts=2026-06-15; rows=41                                                       | Status timeline/cancel evidence partial only                   |

Latest `kaspi_order_sync_log` rows:

| Store     | Last Success        | Min Seen   | Max Seen   | Fetched | Inserted | Updated |
| --------- | ------------------- | ---------- | ---------- | ------- | -------- | ------- |
| STOREB    | 2026-06-18T07:00:26 | 2026-06-09 | 2026-06-17 | 43      | 2        | 41      |
| 11KZ      | 2026-06-18T07:00:25 | None       | None       | 0       | 0        | 0       |
| MELVIS    | 2026-06-18T07:00:25 | None       | None       | 0       | 0        | 0       |
| ACMEWEAR   | 2026-06-18T07:00:25 | 2026-05-28 | 2026-06-18 | 97      | 3        | 94      |
| UNIVERSAL | 2026-06-18T07:00:21 | 2026-05-31 | 2026-06-17 | 106     | 0        | 106     |

## Exact Sources Inspected

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `.claude/OPERATING.md`
- `docs/inventory/Master_Inventory_Rules_v9.md`
- `docs/inventory/Sales_Data_Model_V16.md`
- `docs/protocol/active/PO_making_logic_v3.md`
- `docs/size_engine_specification.md`
- `db/app.db tables/views: fact_orders_kaspi, sales_fact_v2, view_sales_line_truth, order_status_event, return_qc_event, kaspi_order_sync_log, source_manifest, pipeline_run`
- `repo text grep for LINE31/3XL/54 cancellation evidence in docs/exports/runtime-adjacent files`

## Mapping Assumptions And Risks

- Color identity is resolved primarily from `sku_key`, because some `kaspi_offer_name`/article strings are generic or misleading for LINE31 color variants.
- Size identity is resolved as `assigned_size` first, then `my_size`, then terminal size parsed from `sku_id`. This follows the operational size-engine reality that the final picked/shipped size can differ from the marketplace offer-size token.
- `color_cn` is set to `UNKNOWN_IN_AB` in CSVs because the AB rows inspected expose English/Russian color identity but not a canonical Chinese color field. This is safer than inventing supplier-language labels.
- `COMPLETED` and `SHIPPED` are grouped as operational shipped/fulfilled. `COMPLETED` aligns with final fulfillment; `SHIPPED` is a warehouse-handoff/waybill state that may still not be economically delivered.
- `READY` and `ACCEPTED` are counted as open-not-shipped demand, not fulfilled. `RETURNED` is included in the cancelled/unfulfilled sidecar as non-active net demand because returned stock is not sellable unless QC accepts it under inventory rules.
- Cancellation/no-stock reasons are not available at enough granularity in the inspected AB tables to prove that a cancelled order was cancelled specifically because `3XL` was unavailable.

## LINE31 Gross Order Demand By Color And Size

| Color                        | Color Code                  | Size | Distinct Orders | Line Units |
| ---------------------------- | --------------------------- | ---- | --------------- | ---------- |
| Cardamom Green / Olive Green | B/J C-005 + L C-015         | XL   | 1               | 1          |
| Cardamom Green / Olive Green | B/J C-005 + L C-015         | 2XL  | 2               | 2          |
| Espresso                     | C-008                       | XL   | 3               | 3          |
| Iris Purple                  | C-010                       | XL   | 1               | 1          |
| Iris Purple                  | C-010                       | 2XL  | 3               | 3          |
| Ivory                        | C-011                       | M    | 1               | 1          |
| Ivory                        | C-011                       | L    | 1               | 1          |
| Ivory / White / Starry Black | B C-011 + J C-026 + L C-023 | S    | 1               | 1          |
| Ivory / White / Starry Black | B C-011 + J C-026 + L C-023 | M    | 1               | 1          |
| Ivory / White / Starry Black | B C-011 + J C-026 + L C-023 | L    | 1               | 1          |
| Ivory / White / Starry Black | B C-011 + J C-026 + L C-023 | XL   | 2               | 2          |
| Misty Blue                   | C-014                       | L    | 2               | 2          |
| Misty Blue                   | C-014                       | 2XL  | 2               | 2          |
| Starry Black                 | C-023                       | S    | 4               | 4          |
| Starry Black                 | C-023                       | M    | 4               | 4          |
| Starry Black                 | C-023                       | L    | 5               | 5          |
| Starry Black                 | C-023                       | XL   | 8               | 8          |
| Starry Black                 | C-023                       | 2XL  | 6               | 6          |

Gross color totals:

| Color                        | Line Units | Share |
| ---------------------------- | ---------- | ----- |
| Starry Black                 | 27         | 56.2% |
| Ivory / White / Starry Black | 5          | 10.4% |
| Iris Purple                  | 4          | 8.3%  |
| Misty Blue                   | 4          | 8.3%  |
| Espresso                     | 3          | 6.2%  |
| Cardamom Green / Olive Green | 3          | 6.2%  |
| Ivory                        | 2          | 4.2%  |

Gross size totals:

| Size | Line Units | Share |
| ---- | ---------- | ----- |
| S    | 5          | 10.4% |
| M    | 6          | 12.5% |
| L    | 9          | 18.8% |
| XL   | 15         | 31.2% |
| 2XL  | 13         | 27.1% |

## LINE31 Shipped/Fulfilled Demand By Color And Size

| Color                        | Color Code                  | Size | Distinct Orders | Line Units |
| ---------------------------- | --------------------------- | ---- | --------------- | ---------- |
| Cardamom Green / Olive Green | B/J C-005 + L C-015         | XL   | 1               | 1          |
| Cardamom Green / Olive Green | B/J C-005 + L C-015         | 2XL  | 1               | 1          |
| Espresso                     | C-008                       | XL   | 3               | 3          |
| Iris Purple                  | C-010                       | XL   | 1               | 1          |
| Iris Purple                  | C-010                       | 2XL  | 2               | 2          |
| Ivory                        | C-011                       | M    | 1               | 1          |
| Ivory                        | C-011                       | L    | 1               | 1          |
| Ivory / White / Starry Black | B C-011 + J C-026 + L C-023 | S    | 1               | 1          |
| Ivory / White / Starry Black | B C-011 + J C-026 + L C-023 | M    | 1               | 1          |
| Ivory / White / Starry Black | B C-011 + J C-026 + L C-023 | L    | 1               | 1          |
| Ivory / White / Starry Black | B C-011 + J C-026 + L C-023 | XL   | 2               | 2          |
| Misty Blue                   | C-014                       | L    | 1               | 1          |
| Misty Blue                   | C-014                       | 2XL  | 1               | 1          |
| Starry Black                 | C-023                       | S    | 3               | 3          |
| Starry Black                 | C-023                       | M    | 4               | 4          |
| Starry Black                 | C-023                       | L    | 5               | 5          |
| Starry Black                 | C-023                       | XL   | 8               | 8          |
| Starry Black                 | C-023                       | 2XL  | 5               | 5          |

Shipped/fulfilled color totals:

| Color                        | Line Units | Share |
| ---------------------------- | ---------- | ----- |
| Starry Black                 | 25         | 59.5% |
| Ivory / White / Starry Black | 5          | 11.9% |
| Iris Purple                  | 3          | 7.1%  |
| Espresso                     | 3          | 7.1%  |
| Misty Blue                   | 2          | 4.8%  |
| Ivory                        | 2          | 4.8%  |
| Cardamom Green / Olive Green | 2          | 4.8%  |

Shipped/fulfilled size totals:

| Size | Line Units | Share |
| ---- | ---------- | ----- |
| S    | 4          | 9.5%  |
| M    | 6          | 14.3% |
| L    | 8          | 19.0% |
| XL   | 15         | 35.7% |
| 2XL  | 9          | 21.4% |

## Cancelled / Returned / Open-Not-Shipped Demand

| Color                        | Color Code          | Size | Distinct Orders | Line Units |
| ---------------------------- | ------------------- | ---- | --------------- | ---------- |
| Cardamom Green / Olive Green | B/J C-005 + L C-015 | 2XL  | 1               | 1          |
| Iris Purple                  | C-010               | 2XL  | 1               | 1          |
| Misty Blue                   | C-014               | L    | 1               | 1          |
| Misty Blue                   | C-014               | 2XL  | 1               | 1          |
| Starry Black                 | C-023               | S    | 1               | 1          |
| Starry Black                 | C-023               | 2XL  | 1               | 1          |

Status breakdown from primary operational source:

| Status    | Line Units |
| --------- | ---------- |
| COMPLETED | 35         |
| SHIPPED   | 7          |
| ACCEPTED  | 2          |
| RETURNED  | 2          |
| CANCELLED | 1          |
| READY     | 1          |

Downstream `sales_fact_v2` status cross-check for the same window:

| Status    | Rows | Units | Min Date   | Max Date   |
| --------- | ---- | ----- | ---------- | ---------- |
| DELIVERED | 33   | 33    | 2026-05-28 | 2026-06-16 |
| RETURNED  | 4    | 4     | 2026-05-25 | 2026-06-16 |
| CANCELLED | 1    | 1     | 2026-06-09 | 2026-06-09 |

Important cross-source nuance: `sales_fact_v2` dates return/cancel facts by downstream economic/status timing, so it includes two in-window LINE31 returns for orders created before the `2026-05-24` intake window (`916280873`, `930833501`). They are useful return/refund evidence, but they are not counted as new post-arrival gross order demand in the 48-unit `fact_orders_kaspi` intake total.

## 3XL Evidence

- No `3XL` LINE31 row was visible in `fact_orders_kaspi` during the primary window using effective size, `assigned_size`, `my_size`, `sku_id`, `sku_key`, offer text, or `54` textual search signals.
- No canonical AB cancellation/no-stock reason evidence was found that confirms approximately five cancelled `3XL` LINE31 orders.
- A targeted repo text search found LINE31 `3XL` mapping/stock/planning/history references, including older April evidence and offer-mapping rows, but did not surface primary-window `2026-05-24` to `2026-06-18` LINE31 `3XL` cancellation/no-stock order evidence.
- Report classification for owner-reported approx five cancelled `3XL` orders: **not visible / not confirmed in AB data**.

## June-Only Secondary Window

For `2026-06-01` through `2026-06-18`: gross LINE31 demand = **34 units**, operational shipped/fulfilled = **28 units**, cancelled/returned/open-not-shipped = **6 units**.

June gross color totals:

| Color                        | Line Units | Share |
| ---------------------------- | ---------- | ----- |
| Starry Black                 | 18         | 52.9% |
| Ivory / White / Starry Black | 4          | 11.8% |
| Misty Blue                   | 3          | 8.8%  |
| Iris Purple                  | 3          | 8.8%  |
| Cardamom Green / Olive Green | 3          | 8.8%  |
| Ivory                        | 2          | 5.9%  |
| Espresso                     | 1          | 2.9%  |

June gross size totals:

| Size | Line Units | Share |
| ---- | ---------- | ----- |
| S    | 4          | 11.8% |
| M    | 3          | 8.8%  |
| L    | 6          | 17.6% |
| XL   | 9          | 26.5% |
| 2XL  | 12         | 35.3% |

## Color Trend

- Top operational shipped/fulfilled colors: Starry Black=25, Ivory / White / Starry Black=5, Iris Purple=3, Espresso=3, Misty Blue=2.
- Top gross order-attempt colors: Starry Black=27, Ivory / White / Starry Black=5, Iris Purple=4, Misty Blue=4, Espresso=3.
- Because the total sample is 48 line-units and some colors were activated later than others, weak-demand conclusions should be cautious. Treat this as directional allocation evidence, not a final SKU rationalization model.

## Size Trend

- `M` is not the leading size in the May/June operational demand window: `M` = 6/48 (12.5%).
- Larger sizes dominate: `L+XL+2XL+3XL+` = 37/48 (77.1%); `XL+2XL` alone = 28/48 (58.3%).
- `3XL` remains unproven in AB demand truth: 0 visible units/orders in this window.

## Decision Notes For Sourcing / Tracy

- The evidence supports discussing a modest shift toward larger sizes versus an April `M strongest` assumption, especially protecting `XL` and `2XL` availability.
- The evidence does **not** support a confident material `3XL` quantity increase from AB data alone. If Tracy can add `3XL` with low MOQ/low risk, frame it as a small exploratory availability question, not as confirmed AB demand.
- If asking Tracy about `3XL`, the safest wording is: confirm whether `3XL` can be produced for LINE31 and what MOQ/color constraints apply. Do not commit to a large `3XL` allocation until owner/chat/manual cancellation evidence is reconciled into AB.
- PO1B color allocation changes should be conservative because color activation dates differ and the freshness banner is YELLOW, not GREEN.

## Stoplines / Caveats

- **YELLOW freshness:** operational LINE31 order truth is current enough directionally, but sales/economic fulfillment/status-event tables lag the report end date.
- **3XL stopline:** owner-reported approx five cancelled `3XL` orders were not visible in AB canonical sources. Do not treat that claim as confirmed until external/customer-chat evidence is connected to order IDs.
- **Cancellation reason stopline:** `fact_orders_kaspi` exposes statuses/details but not enough canonical no-stock reason detail to distinguish size-unavailable cancellations from buyer/platform cancellations.
- **Color-language caveat:** no canonical Chinese color field was found in AB demand rows; CSV `color_cn` is intentionally `UNKNOWN_IN_AB`.
- **No stock inference:** this is demand evidence, not physical stock truth. Inventory snapshot/ledger state was not used to override demand counts.

## CSV Sidecars

- `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-18_line31_may_june_demand_by_color_size/line31_orders_by_color_size__2026-05-24_to_2026-06-18.csv`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-18_line31_may_june_demand_by_color_size/line31_shipped_or_fulfilled_by_color_size__2026-05-24_to_2026-06-18.csv`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-18_line31_may_june_demand_by_color_size/line31_cancelled_unfulfilled_by_color_size__2026-05-24_to_2026-06-18.csv`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-18_line31_may_june_demand_by_color_size/line31_3xl_demand_evidence__2026-05-24_to_2026-06-18.csv`

## Commands Run And Validation Checks

- Read handoff: `sed -n ... 00_HANDOFF.md`.
- Read repo guidance: `AGENTS.md`, `docs/00_START_HERE.md`, `.claude/OPERATING.md`, `docs/inventory/Master_Inventory_Rules_v9.md`, `docs/inventory/Sales_Data_Model_V16.md`, `docs/protocol/active/PO_making_logic_v3.md`, `docs/size_engine_specification.md`.
- Schema/freshness exploration: `sqlite3 -readonly db/app.db` plus table/view schema and max-date queries.
- Report/CSV generation: Python SQLite connection opened as `file:db/app.db?mode=ro` with `PRAGMA query_only=ON`.
- Targeted text search: `rg -n -i "LINE31.*(3XL|54|cancel|cancelled|отмен|отмена|нет|законч)|3XL.*LINE31|54.*LINE31" docs exports runtime .claude config scripts --glob '*.md' --glob '*.csv' --glob '*.json' --glob '*.txt'`.
- DB SHA-256 before: `5fcb39cebb5c4ef8c03e476590fb7b9e15af7c3ce8167db7f26fce7e3d103ba3`.
- DB SHA-256 after: `5fcb39cebb5c4ef8c03e476590fb7b9e15af7c3ce8167db7f26fce7e3d103ba3`.
- DB unchanged: `YES`.
- External-system writes: none.
- DB writes: none.
