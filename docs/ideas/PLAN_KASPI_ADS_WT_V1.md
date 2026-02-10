Merged execution plan (best-effort “Plan C”) for a new worktree
Goal

Build an ads operating system that:
minimizes wasted spend and improves profit efficiency (profit-first metrics)
is safe/idempotent/backfill-friendly
produces hourly telemetry (since Kaspi UI resets totals at midnight)
enables controlled, auditable bid automation (later)
Non-goals (for this worktree)

Do not wire ads into main cashflow/business-insides “operator truth” yet (that belongs in main repo once sales anchor + inventory settlement are fully green).

Do not install any launchd/cron on the production machine as part of the first PR. Plists can be authored, but not loaded.

Phase 0 — Worktree isolation + “do not break daily ops” defaults

Deliverables

A new worktree directory and branch (see starter prompt below).

Ads DB path override mechanism:

--ads-db <path> CLI flag and/or KASPI_MARKETING_DB_PATH env var for all ads scripts (read/write DB).

A “production DB protect” guard:
If --ads-db points to the known prod path, refuse unless ALLOW_PROD_ADS_DB=1.

Why
Plan B relies on existing daily scraper + DB + workbook pipeline.

We must ensure experiments cannot lock or corrupt the production DB.

Gates
Unit tests for path override + “refuse prod path” behavior.
Phase 1 — Hourly telemetry collector (read-only Kaspi, write-only to worktree DB)
This directly implements Plan B’s highest priority: hourly snapshots + deltas, because Kaspi exposes current-day cumulative totals that reset daily.



Deliverables
scripts/kaspi_ads_hourly_snapshot.py (hourly snapshot watcher).
DB tables (in worktree ads DB) equivalent to Plan B’s intraday snapshot + delta tables (or your naming variant).



Data quality:
monotonic guard
negative delta handling (reset/anomaly flags)
“gap_interpolated” marker for missed hours (no silent smoothing)
Safety controls from Plan B:
lock file to avoid conflict with daily scraper,
low request volume per run,
backoff on rate limits.



Important efficiency tweak
You can skip refactoring scripts/kaspi_marketing_scrape.py in the first iteration (Plan B suggests extracting a shared module).
For speed + low risk: keep hourly script self-contained; do extraction later as a cleanup PR once functionality is proven.

Gates

Tests for:

idempotent insert (same hour run twice doesn’t duplicate)

delta correctness with resets at midnight

lock behavior (skip when locked)

“no negative delta unless reset flag”

Phase 2 — Hour-of-day behavior profiles + daily reconciliation

Turn raw hourly deltas into something you can act on.

Deliverables

scripts/kaspi_ads_build_hourly_profile.py:

Aggregates hourly deltas into hour-of-day totals per campaign + SKU.

Computes concentration % (which hours carry clicks/orders/cost).

Reconciliation validator:

SUM(hourly_deltas) should match the daily totals from the daily scrape (within tolerance) with explicit “delta_method”/quality flags.



Gates

“hourly sums vs daily totals” reconciliation test.

Phase 3 — Bid-write discovery + dry-run bid manager (no automation yet)

Plan B is right: you need a one-time Playwright network capture to discover the bid-write endpoint, because it’s not known yet.



Deliverables

scripts/kaspi_ads_discover_bid_write_api.py:

Headful Playwright capture.

Outputs a JSON artifact with discovered endpoint + headers shape (stored in repo docs/config, no secrets committed).

scripts/kaspi_ads_bid_manager.py:

Reads rules from config/kaspi_ads_bid_rules.yaml.

Default dry_run: true.

Hard safety controls:

min bid floor, max bid ceiling

max step change

max changes per day

per-SKU allowlist (start with one SKU / one campaign)

full bid change audit log (who/when/why/old/new) (aligns with Plan A safety/audit requirements).



Protocol before enabling any scheduled bid changes

Plan B’s mitigation protocol is essential:

do ONE manual bid change,

observe ad_score after 24h/48h/7d,

if score drops, reduce change frequency dramatically.



Gates

--apply must require ENABLE_KASPI_ADS_WRITE=1

dry-run produces an audit log “would change”

bid changes never exceed caps/floors

Phase 4 — Controlled canary automation (still in worktree)

Only after baseline telemetry exists and Phase 3 dry-run is trusted.

Deliverables

A conservative schedule file (but not installed by default):

only 2 runs/day (02:00 reduce, 07:00 restore) per Plan B



aligns with Plan A default night multiplier 0.50 for 02:00-07:00.



Rollback command:

restore base bids from “last known good” table/log.

Phase 5 — Elasticity + profit/ROIC optimizer (offline analysis first)

You can do this immediately because you already have 13.5 months of daily data with natural bid variation for at least SUIT-61 and LINE-51.



Deliverables

scripts/kaspi_ads_elasticity.py computing:

views/click elasticity

marginal cost per order

profit-maximizing bid / ROAS bid target



Profit/ROIC model report:

use app.db economics (dim_sku cogs, delivery fee, commission) and predict incremental profit vs ads cost (Plan B profit model).

Phase 6 — Promotion back to main repo (later)

When:

hourly telemetry is stable,

bid manager is safe in dry-run,

you have at least one cycle of clean reconciliation.

Then:

cherry-pick only the safe commits into main.

only after that, decide whether to integrate ads cost into operator dashboards.