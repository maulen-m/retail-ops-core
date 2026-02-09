# Kaspi Ads: Maximum Efficiency and Profit/ROIC Growth Plan

## 1. Goal
Build an ads operating system that is:
- cost-efficient (minimum waste spend),
- profit-first (maximize gross profit and ROIC, not only traffic),
- scalable (works for all current/future campaigns/SKUs),
- idempotent and reliable (safe to re-run, resilient to folder loss),
- measurable (clear before/after uplift attribution).

This plan covers both theory and practical implementation in the current Autonomous_business stack.

## 2. Business Outcomes (Target)
Primary targets:
- lower wasted CPC spend in low-intent hours,
- increase gross-profit-per-ads-KZT,
- keep or improve order volume quality,
- create stable daily owner reporting with full traceability.

North-star metrics:
- `db_roas` (DB sales GMV / ads cost),
- `db_acos` (ads cost / DB sales GMV),
- `db_profit_est_kzt`,
- `ads_cost_per_db_order`,
- incremental gross profit vs baseline.

## 3. Core Constraints
- Kaspi exposes many metrics as current snapshots in UI; historical hour-level behavior must be built internally.
- Historical `bid_cpc` is not natively exposed as full time series; we need bid snapshots + change logs.
- Ads data and DB sales data are from different systems; robust key mapping and reconciliation are mandatory.

## 4. Operating Principles
- API-first ingestion (no fragile DOM parsing for core data).
- Full idempotency: reruns must not duplicate or corrupt state.
- Backfill-safe: can replay D-3..D-1 with monotonic correction rules.
- Separation of concerns:
  - raw immutable layer,
  - normalized warehouse layer,
  - owner-facing workbook layer.
- Profit-first control: bid changes require expected profitability support.

## 5. Data Architecture

### 5.1 Layers
1. Raw layer (immutable):
- store untouched campaign and per-campaign product CSV payloads per run.
- naming includes date + run timestamp.

2. Normalized layer (SQLite ads DB):
- `campaign_daily_history`
- `campaign_product_daily_history`
- `campaign_daily_current`
- `campaign_product_daily_current`
- `scrape_runs`
- `scrape_anomalies`
- `bid_cpc_overrides`

3. Analytics/export layer:
- owner workbook (`campaign_daily`, `campaign_product_daily`),
- CSV mirrors,
- optional app DB current snapshot export.

### 5.2 Keys
Natural uniqueness keys:
- campaign daily: `(date, merchant_id, campaign_id)`
- campaign product daily: `(date, merchant_id, campaign_id, sku_key)`

Always include:
- `ingested_at`, `run_id`, `source_type`, `source_file`.

### 5.3 Mapping
- Map `sku_key -> mapped_sku_key/mapped_sku_id/mapped_model` through canonical mapping rules.
- Keep `mapping_status` and `filter_rule` explicit for auditability.
- Do not drop rows in history; filter only in owner-facing workbook as needed by policy.

## 6. Reliability and Resilience

### 6.1 Folder-loss resilience
Problem: removing `External_database/Kaspi_marketing` should not break operations.

Solution:
- ads DB is canonical source.
- before each run, preflight checks required folders.
- if missing, restore from latest valid snapshot in local backup root.
- rebuild owner workbook from DB after restore.

### 6.2 Backups (20:30 daily)
Backup schedule:
- daily at `20:30 Asia/Almaty`.
- backup entire `External_database` to timestamped snapshots.

Retention:
- daily snapshots for 30 days,
- weekly snapshot for 12 weeks,
- monthly snapshot for 12 months (optional extension).

Exclusions (space control):
- heavy standalone price files and related duplicates,
- `kaspi_offer_uploads` directories,
- any explicitly configured high-volume artifacts.

Manifest:
- every snapshot includes `backup_manifest.json` with checksum summary and excluded-path list.

## 7. Hourly Behavior Intelligence (24h cycle)

## 7.1 Why
Kaspi day-level reports hide intra-day demand shifts. We need hourly telemetry to understand:
- real click/order concentration windows,
- low-activity windows where high CPC is waste,
- bid elasticity by hour.

## 7.2 Collector design
Run hourly watcher (API pull + optional bid snapshot):
- schedule: every hour at minute `05` (or `00`).
- capture current-day cumulative metrics for all active campaigns/products.
- write to `campaign_product_intraday_snapshots`.

Table key:
- `(snapshot_ts, merchant_id, campaign_id, sku_key)`

Core snapshot columns:
- views, clicks, orders, gmv, cost,
- current `bid_cpc` and `bid_cpc_source`,
- product status, campaign status.

Derived hourly deltas:
- compute `delta_*` between consecutive snapshots per key.
- discard negative deltas unless anomaly flag says data reset.

## 7.3 Data quality rules
- monotonic guard for cumulative metrics,
- anomaly flags for sudden resets/spikes,
- missing-hour imputation marker (not synthetic overwrite).

## 8. Automated CPC Control Engine

## 8.1 Rule layer (deterministic baseline)
Initial baseline rule (as requested):
- `02:00-07:00` local time -> set bid multiplier to `0.50`.
- `07:00-02:00` -> revert to base bid policy.

Guardrails:
- min/max CPC per campaign and per mapped model,
- maximum bid step change per hour (for stability),
- no decreases if campaign is near stock-out or protected promo window.

## 8.2 Activity-aware dynamic multipliers
Build hour-of-week score from last N days:
- click density,
- order density,
- conversion quality,
- marginal profit per click.

Multiplier example:
- very low intent hours: `0.40-0.65`
- medium intent: `0.80-1.00`
- high intent + strong margin: `1.05-1.25`

## 8.3 Elasticity estimation
Estimate relationship between bid and outcomes using historical snapshots:
- log-log or piecewise model:
  - `ln(clicks) ~ a + b*ln(bid_cpc) + controls`
  - `ln(orders) ~ a + b*ln(bid_cpc) + controls`
- control for weekday, hour, campaign, SKU/model.

Use elasticity to avoid over-bidding where incremental return is weak.

## 8.4 Profit-first decision function
For each candidate bid change, estimate:
- expected click lift,
- expected order lift,
- expected GMV lift,
- expected gross profit lift.

Apply change only if expected net profit improves and risk constraints pass.

## 8.5 Safety controls
- daily spend cap,
- rollback to previous bid set on anomaly or API error burst,
- freeze bids during system degradation,
- full audit trail of each bid action (`who/when/why/old/new`).

## 9. Experimentation Framework

A/B structure:
- control group: static baseline bids,
- treatment group: automated rules.

Randomization unit:
- campaign x SKU bucket (balanced by model and traffic tier).

Evaluation windows:
- short-term: 7 days,
- robust decision: 21-28 days.

Success criteria:
- treatment improves `db_profit_est_kzt` and `db_roas` without material volume collapse.

## 10. Workbook and Owner Reporting Model

Single owner workbook should include:
- `campaign_daily`
- `campaign_product_daily`
- optional `hourly_profile` summary sheet.

Required alignment:
- `db_sales_gmv_kzt` must be gross sales (`sell_price * quantity`),
- only active products in owner-facing `campaign_product_daily` (policy),
- keep mapping columns for traceability,
- include delta columns against DB orders/sales.

Recommended additional columns:
- `hour_segment` (night/morning/day/evening),
- `efficiency_score`,
- `margin_pressure_flag`,
- `bid_change_recommendation`.

## 11. End-to-End Scheduler Topology

Daily (20:30):
1. backup `External_database` (with exclusions),
2. scrape D-1 + fallback refresh D-2 and D-3,
3. run normalization + merge rules,
4. rebuild owner workbook + CSV mirrors,
5. run validations,
6. write run summary + anomalies,
7. optional export to app DB current tables.

Hourly:
1. snapshot collector for current day,
2. update intraday telemetry,
3. optionally evaluate bid controller (if enabled),
4. append bid action log.

## 12. Idempotency and Merge Policy

For the same natural key:
- insert if missing,
- update if incoming record has stronger evidence (example: higher finalized cost/GMV during D-3 fallback cycle),
- keep previous version in audit trail.

Never destructive overwrite without provenance.

Suggested fields:
- `record_version`, `supersedes_version`, `update_reason`, `evidence_source`.

## 13. Practical Roadmap

Phase 1 (stability foundation, 1-2 weeks):
- harden backup/restore,
- complete snapshot/audit tables,
- validate workbook consistency and mapping coverage.

Phase 2 (hourly intelligence, 1-2 weeks):
- deploy hourly watcher,
- produce first hour-of-day behavior profiles,
- baseline reporting.

Phase 3 (controlled automation, 2-4 weeks):
- enable deterministic night-rule CPC automation,
- run A/B vs control,
- evaluate profitability impact.

Phase 4 (adaptive optimization, 3-6 weeks):
- add elasticity-informed bid logic,
- dynamic multipliers by hour/model,
- integrate anomaly-aware rollback.

## 14. Risks and Mitigations
- API changes/rate limits:
  - adaptive throttling, backoff, endpoint health checks.
- Session/auth instability:
  - robust login fallback and cookie refresh strategy.
- Mapping drift:
  - daily unmapped SKU alert queue.
- False optimization from noisy data:
  - minimum sample thresholds before bid changes.

## 15. Acceptance Criteria
This plan is successful when:
- daily pipeline runs unattended with recoverability from folder deletion,
- owner workbook is always reproducible from DB,
- hourly behavior dataset is complete enough for 24h pattern analysis,
- automated bid policy yields measured profit efficiency lift,
- all changes are auditable and reversible.

## 16. Decision Defaults (for immediate execution)
- timezone: `Asia/Almaty`.
- daily closeout: `20:30`.
- hourly collector: every hour at minute `05`.
- initial night CPC multiplier: `0.50` during `02:00-07:00`.
- D-3 fallback merge window active by default.
- owner workbook filters to active products only.
- historical store focus: AcmeWear merchant/store mapping; framework remains multi-store-ready.

## 17. What this enables next
Once in place, we can move from passive reporting to active profit control:
- identify true sweet spots by hour/model/SKU,
- stop overpaying during weak demand periods,
- compound gains via continuous learning loops.
