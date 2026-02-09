# Kaspi Ads Optimization — Implementation Blueprint

> Companion to [KASPI_ADS_MAX_EFFICIENCY_AND_PROFIT_GROWTH_PLAN.md](./KASPI_ADS_MAX_EFFICIENCY_AND_PROFIT_GROWTH_PLAN.md) (high-level strategy).
> This document provides concrete implementation: scripts, DB schemas, cron configs, safety controls, and phased execution.

## Context

**Problem:** The current ads system collects daily aggregates only. No hourly activity data exists, no automated bid control, no elasticity analysis. The business may be overpaying during low-activity hours, but we have zero intra-day data to prove it or quantify the waste.

**Critical insight:** Kaspi's ad algorithm may penalize frequent bid changes (similar to Meta Ads quality score). We must collect baseline hourly data FIRST (10+ days) before attempting any bid automation, so we can measure whether bid changes cause downstream penalties.

**Existing infrastructure:**
- Daily scraper: `scripts/kaspi_marketing_scrape.py` (Playwright + API, 20:30 daily via launchd)
- Ads DB: `External_database/Kaspi_marketing/db/kaspi_marketing.db` (5 tables, 13.5 months daily data)
- Owner workbook: `scripts/build_kaspi_marketing_owner_workbook.py` (43-column XLSX)
- Sidecar sync: `scripts/sync_ads_sidecar.py` (mirrors to app.db)
- 2 active campaigns: LINE-51 (`19102598b`) and SUIT-61 (`19796919b`), merchant 759051, store 30137883
- API endpoints for reading: campaigns list (v5), products per campaign (v5), campaign core (v1), products CSV reports (v3)
- No existing bid-write API endpoint discovered; requires one-time Playwright network capture

**Key Kaspi platform fact:** Current-day data shows running totals that reset at midnight. To get hourly resolution, we must snapshot every hour and compute deltas.

---

## Phase 1 (PRIORITY): Hourly Data Collection

### New files

| File | Purpose |
|------|---------|
| `scripts/kaspi_ads_common.py` | Shared auth/login/API utilities extracted from `kaspi_marketing_scrape.py` |
| `scripts/kaspi_ads_hourly_snapshot.py` | Lightweight hourly watcher |
| `config/com.example.kaspi-marketing-hourly.plist` | launchd agent (every hour at :05) |
| `tests/test_kaspi_ads_hourly_snapshot.py` | Tests |

### Modified files

| File | Change |
|------|--------|
| `scripts/kaspi_marketing_scrape.py` | Import shared functions from `kaspi_ads_common.py` instead of defining inline |

### 1a. Extract shared module (`kaspi_ads_common.py`)

Move from `kaspi_marketing_scrape.py`:
- `build_kaspi_headers()`, `ensure_login()` / `wait_for_login()`
- `parse_number()`, `parse_int()`, `_coerce_str()`
- `download_with_details()`
- Constants: `ALMATY_TZ`, URL templates, paths, merchant/store IDs

Update existing scraper to import from common. Verify: `pytest -q tests/test_kaspi_marketing_scrape.py tests/test_kaspi_marketing_owner_workbook.py`

### 1b. New DB tables (in `kaspi_marketing.db`)

```sql
CREATE TABLE IF NOT EXISTS hourly_snapshot (
    snapshot_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_at   TEXT NOT NULL,          -- ISO timestamp (Almaty TZ)
    snapshot_hour INTEGER NOT NULL,       -- 0-23
    date          TEXT NOT NULL,          -- YYYY-MM-DD
    merchant_id   TEXT NOT NULL,
    campaign_id   TEXT NOT NULL,
    campaign_name TEXT,
    sku_key       TEXT NOT NULL,
    bid_cpc       REAL,
    views_cumul   INTEGER,
    clicks_cumul  INTEGER,
    cost_cumul    REAL,
    gmv_cumul     REAL,
    orders_cumul  INTEGER,
    favorites_cumul INTEGER,
    carts_cumul   INTEGER,
    cost_today    REAL,
    UNIQUE(date, snapshot_hour, merchant_id, campaign_id, sku_key)
);

CREATE TABLE IF NOT EXISTS hourly_delta (
    delta_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    hour_start  INTEGER NOT NULL,        -- 10 means 10:00-11:00
    hour_end    INTEGER NOT NULL,
    merchant_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    sku_key     TEXT NOT NULL,
    bid_cpc     REAL,
    views_delta   INTEGER,
    clicks_delta  INTEGER,
    cost_delta    REAL,
    gmv_delta     REAL,
    orders_delta  INTEGER,
    favorites_delta INTEGER,
    carts_delta   INTEGER,
    delta_method TEXT,                   -- 'sequential' | 'gap_interpolated' | 'day_start'
    UNIQUE(date, hour_start, merchant_id, campaign_id, sku_key)
);
```

### 1c. Hourly watcher (`kaspi_ads_hourly_snapshot.py`)

Lightweight script (~200 lines target):
1. Acquire lock file (`logs/.kaspi_ads_lock`) — skip if daily scraper is running
2. Launch Playwright persistent context (same Chrome profile as daily scraper)
3. Call campaigns API for today (Enabled state only — 1 GET)
4. For each campaign, call products API for today (1 GET per campaign = 2 GETs total)
5. Extract: `views`, `clicks`, `cost`, `costToday`, `gmv`, `transactions`, `favorites`, `carts`, `bid`
6. UPSERT into `hourly_snapshot`
7. Compute delta from previous hour's snapshot, INSERT into `hourly_delta`
8. Close browser, release lock. **Target: <30 seconds total runtime**

**Delta edge cases:**
- First snapshot of day (00:05): delta = cumulative itself (midnight-to-00:05 activity)
- Missing snapshot (machine slept): flag as `gap_interpolated`, delta covers multi-hour gap
- Negative delta (Kaspi reset/anomaly): set to 0, log anomaly
- Campaign paused mid-day: cumulative stops growing, deltas become 0

### 1d. launchd config

24 `StartCalendarInterval` entries, one per hour at minute :05. Follows existing plist pattern from `com.example.kaspi-marketing-ads.plist`.

```xml
<!-- config/com.example.kaspi-marketing-hourly.plist -->
<plist version="1.0">
<dict>
  <key>Label</key><string>com.example.kaspi-marketing-hourly</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/python3</string>
    <string>~/Docs/Autonomous_business/scripts/kaspi_ads_hourly_snapshot.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>~/Docs/Autonomous_business</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>0</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>1</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>4</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>5</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>16</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>20</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>21</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>22</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>5</integer></dict>
  </array>
  <key>StandardOutPath</key>
  <string>~/Docs/Autonomous_business/logs/hourly_snapshot_stdout.log</string>
  <key>StandardErrorPath</key>
  <string>~/Docs/Autonomous_business/logs/hourly_snapshot_stderr.log</string>
</dict>
</plist>
```

### 1e. Storage estimate

~48 rows/day (24h x 2 campaigns x 1 product each) = ~67 KB/day = ~2 MB/month. Trivial alongside existing 1 MB ads DB.

---

## Phase 2: Activity Analysis & Reporting (after 10+ days of hourly data)

### New files

| File | Purpose |
|------|---------|
| `scripts/kaspi_ads_hourly_analysis.py` | Builds activity profiles, generates reports |

### Modified files

| File | Change |
|------|--------|
| `scripts/build_kaspi_marketing_owner_workbook.py` | Optional "Hourly Profile" sheet |

### New DB table

```sql
CREATE TABLE IF NOT EXISTS hourly_activity_profile (
    campaign_id    TEXT NOT NULL,
    sku_key        TEXT NOT NULL,
    hour           INTEGER NOT NULL,     -- 0-23
    days_observed  INTEGER,
    avg_views      REAL,
    avg_clicks     REAL,
    avg_cost       REAL,
    avg_orders     REAL,
    pct_daily_views  REAL,
    pct_daily_clicks REAL,
    pct_daily_orders REAL,
    classification TEXT,                 -- 'peak' | 'normal' | 'low' | 'dead'
    computed_at    TEXT NOT NULL,
    UNIQUE(campaign_id, sku_key, hour)
);
```

### Analysis pipeline

1. Aggregate `hourly_delta` into `hourly_activity_profile` (min 10 days required)
2. Per-hour classification:
   - **Peak:** top 25% of daily views
   - **Normal:** 25th-75th percentile
   - **Low:** 75th-90th percentile
   - **Dead:** <10% (under 1% of daily traffic)
3. Generate text report:
   ```
   LINE-51 (Acmewear_16k):
     Peak hours (>15% daily views): 10:00-12:00, 19:00-21:00
     Dead hours (<1% daily views):  01:00-06:00
     Recommendation: 50% bid reduction during 01:00-06:00 saves ~X KZT/day
   ```
4. Cross-validate: `SUM(hourly_deltas)` vs daily scraper total (within 5% tolerance)
5. Weekday vs weekend pattern comparison

### Key questions this answers

- When exactly are customers clicking and ordering?
- How much spend is wasted during dead hours?
- What hours have the best conversion rates (clicks → orders)?
- Is there a meaningful difference between weekday and weekend patterns?
- Are there "shoulder hours" where moderate bid adjustments would help?

---

## Phase 3: Automated Bid Management (ONLY after Phase 2 analysis proves value)

### Prerequisites before ANY bid changes

1. 10+ days of hourly baseline data collected
2. Activity profile confirms dead hours exist (not just assumed)
3. One-time bid-change API discovery via Playwright network capture
4. Baseline `ad_score` and quality metrics recorded for comparison
5. Decision: does Kaspi penalize bid frequency? (monitor `ad_score` after first manual test change)

### New files

| File | Purpose |
|------|---------|
| `scripts/kaspi_ads_discover_bid_api.py` | One-time: captures bid-change endpoint via Playwright network interception |
| `scripts/kaspi_ads_bid_manager.py` | Rule-based bid automation with safety controls |
| `config/ads_bid_rules.yaml` | Declarative rules (time windows, multipliers, caps) |
| `config/com.example.kaspi-marketing-bids.plist` | launchd for bid changes |
| `tests/test_kaspi_ads_bid_manager.py` | Tests |

### Bid change API discovery (one-time)

`kaspi_ads_discover_bid_api.py`:
1. Launch Playwright in **headful** mode with request interception enabled
2. Navigate to campaign products page
3. Prompt operator: "Manually change a bid in the UI, then press Enter"
4. Capture all POST/PUT/PATCH requests during the change
5. Save discovered endpoint URL, method, headers, payload to `docs/marketing/bid_api_discovery.json`
6. If no REST endpoint found → fallback to Playwright UI automation

### Bid rules config (`config/ads_bid_rules.yaml`)

```yaml
version: 1
safety:
  dry_run: true                  # MUST start true
  max_bid_kzt: 200               # Hard ceiling — never exceed
  min_bid_kzt: 10                # Hard floor — never go below
  max_daily_changes: 4           # Per product per day
  require_env: "ENABLE_ADS_WRITE"  # Env var must be "1" to execute
  cooldown_minutes: 60           # Min time between changes per product

schedules:
  night_reduction:
    description: "Reduce bids during low-traffic hours"
    enabled: true
    windows:
      - start_hour: 2
        end_hour: 7
        bid_multiplier: 0.5
    apply_to: all

campaigns:
  "2380614":  # Acmewear_16k / LINE-51
    base_bid: 70
  "2545773":  # ACMEWEAR_LINE61
    base_bid: 70
```

### Bid manager execution flow (`kaspi_ads_bid_manager.py`)

1. Load `ads_bid_rules.yaml`
2. Check `ENABLE_ADS_WRITE=1` env var — abort if missing
3. Determine current Almaty hour
4. For each campaign/product:
   - Find applicable rule for this hour
   - Compute `target_bid = base_bid * multiplier`, clamp to [min_bid, max_bid]
   - Read current bid from API
   - If current != target:
     - Check cooldown (last change > cooldown_minutes ago via `bid_change_log`)
     - Check daily limit (changes today < max_daily_changes)
     - If `dry_run`: log intended change only
     - If live: execute change via discovered API, verify, log result
5. Summary: "Changed X bids, skipped Y (cooldown), Z errors"

### New DB table

```sql
CREATE TABLE IF NOT EXISTS bid_change_log (
    change_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    executed_at  TEXT NOT NULL,
    campaign_id  TEXT NOT NULL,
    sku_key      TEXT,
    campaign_product_id TEXT,
    old_bid      REAL,
    new_bid      REAL,
    rule_name    TEXT,
    dry_run      INTEGER NOT NULL DEFAULT 1,
    success      INTEGER,
    error_message TEXT,
    method       TEXT                    -- 'api' | 'playwright_ui'
);
```

### Safety controls (non-negotiable)

- `dry_run: true` default — must be explicitly flipped after reviewing dry-run logs
- Hard ceiling `max_bid_kzt: 200` + floor `min_bid_kzt: 10` enforced in code (assertion, not just config)
- `ENABLE_ADS_WRITE=1` env var gate (same pattern as existing `ENABLE_CASHFLOW_WRITE`)
- Max 2 bid changes per product per day initially (night reduce + morning restore)
- Cooldown: minimum 60 min between changes for same product
- Full audit log in `bid_change_log` with old/new values for instant rollback
- Campaign `dailyBudget` on Kaspi side provides platform-level safety net
- Monitor `ad_score` changes after bid modifications — **halt if score degrades**
- Optional: Telegram alert on live bid changes

### Bid frequency risk mitigation protocol

Before enabling scheduled bid changes:
1. Make ONE manual test bid change via the discovered API
2. Record `ad_score` before and after (24h, 48h, 7d)
3. If `ad_score` drops → Kaspi penalizes bid frequency → switch to less frequent changes (weekly schedule or static optimal bids)
4. If `ad_score` stable → safe to proceed with nightly bid adjustments

### Bid manager launchd schedule (conservative)

Only 2 runs per day:
- 02:00 — apply night reduction (bid * multiplier)
- 07:00 — restore to base bid

```xml
<!-- config/com.example.kaspi-marketing-bids.plist -->
<key>StartCalendarInterval</key>
<array>
  <dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>0</integer></dict>
  <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
</array>
```

---

## Phase 4: Elasticity Analysis

### Already-available data (no new collection needed)

13.5 months of daily data shows natural bid variation:

| Product | Bid levels observed | Pattern |
|---------|-------------------|---------|
| SUIT-61 | 30, 70, 140 | 2x bid (70→140) = ~5x views, ROAS drops ~35→~9 |
| LINE-51 | 70, 140, 150 | Similar diminishing returns |

This is enough for an initial elasticity estimate before controlled experiments.

### New files

| File | Purpose |
|------|---------|
| `scripts/kaspi_ads_elasticity.py` | Bid-performance elasticity + profit sweet-spot finder |

### Metrics to compute

- **Views elasticity** = %change_views / %change_bid
- **Click elasticity** = %change_clicks / %change_bid
- **Marginal cost per click** at each bid level
- **Marginal cost per order** at each bid level
- **Optimal ROAS bid** = where ROAS meets target threshold (e.g., 5x)
- **Profit-maximizing bid** = where marginal revenue > marginal cost

### Controlled experiments (requires Phase 3)

Once bid manager works, run structured bid sweeps:
- Bid level A for 7 days → B for 7 days → C for 7 days
- Record performance at each level
- Compute elasticity curves with confidence intervals

---

## Phase 5: Profit/ROIC Optimization

### Profit model

Using economics data from app.db (`dim_sku.cogs_kzt`, `fact_sales`):

```
profit(bid) = predicted_orders(bid) * sell_price
            - predicted_orders(bid) * (cogs + delivery_fee)
            - predicted_orders(bid) * sell_price * kaspi_commission_pct
            - predicted_ads_cost(bid)
```

### Sweet spot finder

Sweep bid range [10, 200] in steps of 10, compute at each level:
- `incremental_profit` = profit_with_ads - organic_profit
- `ads_ROIC` = incremental_profit / ads_cost
- **Optimal bid** = max(incremental_profit)

Output: recommended bid per product with expected profit impact and confidence range.

### Stretch features

- Day-of-week bid schedules (weekday vs weekend patterns from Phase 2 data)
- Seasonal adjustment (thermal wear peaks in cold months; suits peak around events)
- Anomaly detection (competitor enters auction → sudden performance shift)
- Multi-product budget allocation (more budget to higher-ROIC product when constrained)
- Activity-aware dynamic multipliers:
  - Dead hours: 0.40-0.65x
  - Normal hours: 0.80-1.00x
  - Peak hours with strong margin: 1.05-1.25x

---

## Risk Mitigations

| Risk | Mitigation |
|------|------------|
| Kaspi rate limiting (24 hourly sessions) | Persistent Chrome profile reuses cookies; only 2-5 GET requests per hourly run; exponential backoff on 429s |
| Browser conflict (hourly vs daily scraper) | Lock file `logs/.kaspi_ads_lock`; hourly has 10s acquire timeout, skips on failure |
| Kaspi penalizing bid frequency | Monitor `ad_score` before/after first bid change; halt if degradation detected; default to infrequent changes |
| Budget runaway from bad bids | `dry_run: true` default + hard caps + Kaspi's `dailyBudget` + audit log + Telegram alerts |
| Accidental zero bid | Hard floor `min_bid_kzt: 10` with assertion in code |
| Delta accuracy (missed snapshots) | `delta_method` column flags quality; daily `SUM(hourly) vs daily total` reconciliation |
| Mac sleeping | launchd queues missed jobs; `gap_interpolated` flag on wakeup; consider `caffeinate` wrapper for critical coverage |

---

## Scheduler topology (after all phases)

| Job | Schedule | Script |
|-----|----------|--------|
| `com.example.kaspi-marketing-ads` | 20:30 daily | `run_kaspi_marketing_scrape.command` (existing) |
| `com.example.kaspi-marketing-hourly` | :05 every hour | `kaspi_ads_hourly_snapshot.py` (new) |
| `com.example.kaspi-marketing-bids` | 02:00, 07:00 | `kaspi_ads_bid_manager.py` (Phase 3) |
| `com.example.external-database-backup` | 21:10 daily | `run_external_database_backup.command` (existing) |

---

## Verification

After each phase:
1. Existing tests pass: `pytest -q tests/test_kaspi_marketing_scrape.py tests/test_kaspi_marketing_owner_workbook.py`
2. New tests pass: `pytest -q tests/test_kaspi_ads_hourly_snapshot.py`
3. Manual: run hourly snapshot once, inspect DB (`sqlite3 kaspi_marketing.db "SELECT * FROM hourly_snapshot"`)
4. After 1 day of collection: `SUM(hourly_deltas)` vs daily scraper total (within 5% tolerance)
5. After 10 days: generate first activity profile, validate against manual observations
6. Before Phase 3 go-live: dry-run bid manager, review all logs, verify `ad_score` baseline

---

## First session execution sequence

1. Create `scripts/kaspi_ads_common.py` — extract shared utilities from scraper
2. Update `scripts/kaspi_marketing_scrape.py` — import from common module
3. Verify no regression: `pytest -q tests/test_kaspi_marketing_scrape.py tests/test_kaspi_marketing_owner_workbook.py`
4. Create `scripts/kaspi_ads_hourly_snapshot.py` with DB table creation in `ensure_schema()`
5. Create `tests/test_kaspi_ads_hourly_snapshot.py`
6. Create `config/com.example.kaspi-marketing-hourly.plist`
7. Manual test: run snapshot once, inspect DB
8. Install scheduler: `launchctl load config/com.example.kaspi-marketing-hourly.plist`
