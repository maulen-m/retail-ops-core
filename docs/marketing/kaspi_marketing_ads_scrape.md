# Kaspi Marketing Ads — scraping & automation plan

## Goal
Automate **daily (20:30 GMT+5)** headless export of **yesterday-only** ad data from https://marketing.kaspi.kz/advertising/ using **API endpoints (no UI parsing)**.
Outputs:
- Raw report files (CSV) in **timestamped subfolders** (per run).
- Per-campaign + per-product (SKU) detail tables from **per-campaign CSV + JSON endpoints**.
- One **bookkeeper** workbook with **two sheets** (`campaign_daily`, `campaign_product_daily`), updated only when cost increases.
- Dedicated SQLite “db doc” + optional export view to `app.db` for downstream use.

All raw/detail outputs live under:
```
~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing
```

Bookkeeper workbook lives under:
```
~/Docs/Autonomous_business/excel/marketing/Kaspi_marketing_bookkeeper.xlsx
```

## Authentication & session handling
The Kaspi marketing UI auto-logs out after ~20 minutes or when idle. We must use the existing Chrome profile session and fall back to login.

**Active Chrome profile:**
```
~/Library/Application Support/Google/Chrome/Profile 4
```
**Automation copy (recommended):**
```
~/Library/Application Support/ChromePlaywrightProfile4
```

### Recommended approach (Playwright)
- Use **persistent context** so cookies/session survive headless runs.
- Prefer Chrome channel (`channel="chrome"`) to match the real profile/session.
- Detect login screen and auto-login using credentials from `.env`.

**Notes / risks:**
- Using the **live profile directory** may conflict if Chrome is open. Safer to **copy profile** to a dedicated automation profile and refresh cookies when needed.
- If Kaspi enforces SMS/2FA, login may require a manual refresh to re-seed cookies; keep a fallback path for that.

### Env vars (suggested)
- `Kaspi_marketing_login` (or login ID)
- `Kaspi_marketing_Password`
- Optional: `KASPI_MARKETING_PROFILE_DIR` (override)

## Key URLs & UI flow
### Base pages
- Campaigns page:
  - `https://marketing.kaspi.kz/advertising/campaigns?tab=campaigns&activeTab=Enabled`
- With date filter (yesterday):
  - `https://marketing.kaspi.kz/advertising/campaigns?tab=campaigns&startDate=YYYY-MM-DD&endDate=YYYY-MM-DD&activeTab=Enabled`

### Date selection
UI period selector includes: **Сегодня / Вчера / Последние 7 дней / Последние 30 дней / Выбрать период**.
For automation we **force yesterday** using URL parameters or via date picker to avoid partial data.

## Report download (raw file)
When clicking **“Скачать отчет”**, the UI triggers a download request. Example observed endpoint:
```
https://marketing.kaspi.kz/advertising/products/api/v3/merchant/759051/reports/campaigns/csv?dateFrom=2026-02-02&dateTo=2026-02-02
```
**Action:** capture the **actual endpoint + format** (csv/xlsx) by inspecting network logs when the button is pressed.
The scraper parses this campaigns CSV and adds any **extra columns** into `report_*` fields (plus a fallback `report_extra` JSON blob).

### Campaign list API (all states)
Use the campaigns API to fetch **Enabled + Paused + Finished** in one run:
```
https://marketing.kaspi.kz/advertising/products/api/v5/merchant/759051/Campaigns?StartDate=YYYY-MM-DD&EndDate=YYYY-MM-DD&state=Enabled
https://marketing.kaspi.kz/advertising/products/api/v5/merchant/759051/Campaigns?StartDate=YYYY-MM-DD&EndDate=YYYY-MM-DD&state=Paused
https://marketing.kaspi.kz/advertising/products/api/v5/merchant/759051/Campaigns?StartDate=YYYY-MM-DD&EndDate=YYYY-MM-DD&state=Finished
```
Merge by `campaign_id` to avoid duplicates. Map `merchant_id` → AcmeWear store code `30137883` for downstream joins.

### Observed (Playwright, 2026-02-03)
- Download URL (CSV):
  - `https://marketing.kaspi.kz/advertising/products/api/v3/merchant/759051/reports/campaigns/csv?dateFrom=2026-02-02&dateTo=2026-02-02`
- Suggested filename from download:
  - `2026-02-02 - 2026-02-02 Отчёт по кампаниям.csv`

### Per‑campaign products report (SKU‑level)
This report is downloaded **inside each campaign page** and includes `sku_key`:
```
https://marketing.kaspi.kz/advertising/products/api/v3/merchant/759051/reports/products/csv?campaignId=<campaign_id>&startDate=YYYY-MM-DD&endDate=YYYY-MM-DD
```
Example:
```
https://marketing.kaspi.kz/advertising/products/api/v3/merchant/759051/reports/products/csv?campaignId=2380614&startDate=2026-01-06&endDate=2026-02-04
```
**Rule:** treat `sku_key` from this CSV as the **primary product key** and merge/augment with JSON from
`/campaign/<id>/products` when fields are missing (e.g., `bid_cpc`, rating).

### Best practice (faster + more reliable)
1. Open campaigns page with date params (yesterday).
2. **Intercept or record** the report request on first run.
3. Use `context.request.get(report_url)` with cookies from the browser context.
4. Save file to:
```
.../Kaspi_marketing/raw/YYYY-MM-DD/report_<timestamp>.xlsx
```

## Campaign detail scraping
From “Мои кампании” table, click each campaign row and scrape the **Товары** table.

**Detail URL format (observed):**
```
https://marketing.kaspi.kz/advertising/campaigns/<campaign_id>?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD
```
Campaign links in the list resolve to:
```
https://marketing.kaspi.kz/advertising/campaigns/<campaign_id>
```

### Observed API endpoints (campaign detail page)
These endpoints are called when a campaign detail page loads; use them for reliable data extraction instead of DOM scraping:
- Campaign overview:
  - `https://marketing.kaspi.kz/advertising/products/api/v4/merchant/759051/Overview/<campaign_id>`
- Campaign core info:
  - `https://marketing.kaspi.kz/advertising/products/api/v1/merchant/759051/Campaign/<campaign_id>`
- Campaign daily views (chart/metrics):
  - `https://marketing.kaspi.kz/advertising/products/api/v3/merchant/759051/overview/daily/<campaign_id>/views`
- Campaign product categories (date-scoped):
  - `https://marketing.kaspi.kz/advertising/products/api/v4/merchant/759051/campaign/<campaign_id>/products-categories?StartDate=YYYY-MM-DD&EndDate=YYYY-MM-DD`
- **Campaign products metrics (date-scoped)** — likely contains the per-product table:
  - `https://marketing.kaspi.kz/advertising/products/api/v5/merchant/759051/campaign/<campaign_id>/products?StartDate=YYYY-MM-DD&EndDate=YYYY-MM-DD`

These endpoints returned JSON with top-level keys `result` + `data`.
Use cookies from the authenticated browser context to call them via `context.request.get()`.

**Note:** The UI did not expose a standard HTML `<table>` for product rows during Playwright inspection; metrics appear to be rendered from API responses. Prefer API-driven scraping.

### Required fields per product row
- Товар
- Рекламная оценка
- Просмотры
- Клики
- В избранное
- В корзину
- Все заказы
- Прямые заказы
- Сопутствующие заказы
- Конверсия в заказ
- Ставка за клик
- Средняя стоимость клика
- Расходы на рекламу
- Доля рекламных расходов

### Recommended scrape schema
```
date                (YYYY-MM-DD, date)
merchant_id         (text)
store_code          (text, AcmeWear=30137883)
campaign_id         (text)
campaign_name       (text)
sku_key             (text)
product_name        (text)
product_status      (text)
ad_score            (text)
bid_cpc             (float, CPC input)
avg_cpc             (float)
views               (int)
clicks              (int)
favorites           (int)
cart                (int)
ctr                 (float)
gmv                 (float)
orders_total        (int)
orders_direct       (int)
orders_assisted     (int)
conversion_order    (float)
cost                (float)
acos_share          (float)
order_numbers       (text)
assisted_products   (text)
ingested_at         (ISO timestamp)
```
IDs must stay **TEXT** (do not coerce to numbers).

## Storage layout
Base:
```
~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing
```
Suggested structure:
```
Kaspi_marketing/
|-- raw/YYYY-MM-DD/<run_id>/        # downloaded reports (untouched)
|-- details/YYYY-MM-DD/<run_id>/    # normalized CSVs
|-- db/kaspi_marketing.db           # sqlite history/current
|-- logs/scrape_<run_id>.json       # run log + anomalies
|-- backups/                        # workbook backups (timestamped)
```

Optional export view:
- `--export-app-db` copies `campaign_*_current` into `app.db` tables:
  - `ads_campaign_daily_current`
  - `ads_campaign_product_daily_current`

## Bookkeeper workbook (Excel-safe-ops)
Use **two sheets** (`campaign_daily`, `campaign_product_daily`) with **cost-increase upserts**:
- Record every run in history (db); workbook keeps latest per key **only if cost increases**.
- Location:
  - `~/Docs/Autonomous_business/excel/marketing/Kaspi_marketing_bookkeeper.xlsx`
- Always **backup** before writing: `backups/<name>.<timestamp>.xlsx`
- Never reorder/rename columns.
- IDs as **TEXT**.
- Write to temp file, then **atomic replace**.
- Validate by re-open.

## Scheduler (20:30 GMT+5)
Use **launchd** on macOS (preferred) or cron. Launchd uses **system local time**, so ensure system TZ is GMT+5.
The scraper itself uses `Asia/Almaty` to compute **yesterday**, so date boundaries remain GMT+5 even if the Mac timezone drifts.

### Launchd plist template (example)
```
Label: com.example.kaspi-marketing
ProgramArguments:
  - /bin/bash
  - ~/Docs/Autonomous_business/scripts/run_kaspi_marketing_scrape.command
StartCalendarInterval:
  Hour: 20
  Minute: 30
WorkingDirectory: ~/Docs/Autonomous_business
StandardOutPath: ~/Docs/Autonomous_business/logs/marketing_stdout.log
StandardErrorPath: ~/Docs/Autonomous_business/logs/marketing_stderr.log
```

Repo files:
- `config/com.example.kaspi-marketing-ads.plist`
- `scripts/run_kaspi_marketing_scrape.command`
- `scripts/install_kaspi_marketing_scheduler.sh`

## Execution flow (headless)
1. Compute **target_date window**: вчера, позавчера, и 3‑й день назад (re-run last 3 days).
2. Launch persistent browser context with profile/session.
3. Detect login state; if logged out, auto-login.
4. Call **Campaigns API** for each date + state (Enabled/Paused/Finished).
5. Call **campaigns report CSV** endpoint; save raw file untouched.
6. Loop campaigns → call **per-campaign products CSV** (SKU‑level) + JSON endpoints.
7. Persist results: raw file + details + db + append to bookkeeper (upsert last 3 days).
8. Close browser cleanly.

## Backfill (from 2025-01-01)
Use the scraper in **API-only** mode with an explicit date range:
```
python3 scripts/kaspi_marketing_scrape.py --start-date 2025-01-01 --end-date 2026-02-03 --export-app-db
```
If the API denies some days, re-run with `--headful` to refresh session cookies and continue.

## Login notes (observed)
- Login page title: **“Войти в кабинет – Маркетинг”**
- Auto-login worked using `.env` keys:
  - `Kaspi_marketing_login`
  - `Kaspi_marketing_Password`
- If login fails, fall back to manual cookie refresh in the copied automation profile.

## Resilience & reliability
- Handle **auto-logout** by checking for login form at each major step.
- If login fails (e.g., SMS required), stop and alert.
- Retry page loads (timeout/backoff) and use explicit waits for tables.
- Keep **rate limits low** (small delays between campaign detail pages).
- Store logs with timestamps for each run.

## Merchant mapping note
Kaspi Ads uses **merchant_id** values that can differ from Kaspi store IDs.
For now, ads run only for **AcmeWear**. Store the ads `merchant_id` and also map to the AcmeWear store ID/code in downstream tables.

## How to discover endpoints (once)
1. Open DevTools → Network.
2. Click “Скачать отчет”.
3. Note request URL, headers, response type (csv/xlsx).
4. Save as report endpoint template.

This endpoint can be called directly using cookies from the browser context for faster, more stable downloads.
