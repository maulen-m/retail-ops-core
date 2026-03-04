P0 — Clear REFERENCE_STALE (blocks doctor + all owner-grade publication)

Why first: system_doctor is red on this, and reference freshness is a prerequisite for “latest month” truth.

What the gate is asking for: delivered max date must be within allowed lag. Right now it’s 2026‑02‑24; required minimum is 2026‑02‑26 (for as‑of 2026‑03‑04 with max lag 7).

Action (fastest):

Refresh the UI status-change-date packs through 2026‑03‑04 (the “Дата изменения статуса” truth source).

Rebuild the canonical mapped archive using those packs.

Acceptance gate:

python3 scripts/export_sales_archive_statusdate_mapped.py --since 2025-06-06 --until 2026-03-04 --strict (rebuild)

python3 scripts/validate_reference_freshness.py --as-of 2026-03-04 --strict → PASS (max_delivered_date >= required_min_delivered_date).

Important constraint: strict mode explicitly says delivered date basis must be statusChangeDate, and after the cutover you must not rely on creationDate fallback.

P0 — Clear IDENTITY_COVERAGE_FAIL (prevents “COGS missing → profit inflated”)

Your own validator shows that for the last 15 days (as-of 2026‑03‑04) UNIVERSAL and STOREB are at 100% missing identity core, i.e., every recent order is missing required fields.

Backfill was computed but not applied (apply=false), meaning the system still cannot rely on it.

Action (fastest, capital-safe):

Back up DB (write safety).

Apply deterministic identity backfill for the recent window (and record identity_source).

Patch ingestion so new orders don’t regress (identity captured at ingest; if not possible, quarantine).

Acceptance gates (must be strict):

python3 scripts/validate_recent_identity_coverage.py --as-of 2026-03-04 --strict → PASS.

Re-run backfill in apply mode so unresolved drops below threshold (and any remaining unresolved orders are quarantined, not silently included). The last dry run indicated it would update 703 rows with 54 unresolved.

P0 — Clear ADS_SOURCE_STALE and populate ads sidecar (unlocks profit-after-ads)

Your ads readiness contract is fail-closed by design:

It resolves ads DB path via CLI arg → AB_ADS_DB_PATH → default external path.

It requires freshness within AB_ADS_DB_MAX_AGE_HOURS (default 36 hours).

Key finding: the scheduling described in your pack is daily (20:30 scrape + 21:10 backup), not “hourly.” If it runs daily, it should still satisfy a 36h freshness window. If it’s not running, you will reliably fail.

Action (fastest):

Restore/verify the ads source DB is being updated by the scheduler (or run the scrape manually once to refresh the DB).

Sync ads into the app DB sidecar tables (dry run first, then gated apply).

Write-safety + apply gate:

python3 scripts/backup_db.py --db db/app.db

Dry run: python3 scripts/sync_ads_sidecar.py --since 2025-06-06 --until 2026-03-04

Apply (gated): ENABLE_CASHFLOW_WRITE=1 python3 scripts/sync_ads_sidecar.py --since 2025-06-06 --until 2026-03-04 --apply

Acceptance gate:

python3 scripts/validate_ads_sidecar_readiness.py --as-of 2026-03-04 --strict → PASS.

P0 — Publish the only allowed owner surface: OWNER_PNL

The publication contract is explicit: if ads readiness is not green, OWNER_PNL must not show profit-after-ads; it must lock.

Action:

Run doctor strict.

Build owner PnL strict (store breakdown on).

Publish/export only if strict passes.

Acceptance gates:

python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-04 → GREEN (no stoplines).

python3 scripts/build_owner_pnl_report.py --as-of 2026-03-04 --since 2025-06-06 --include-store-breakdown --strict → PASS + emits exports under exports/owner_pnl/2026-03-04/.

Two extra “profit realism” checks worth adding (P1, but high ROI)

These directly address “I don’t believe profit is that high” with hard evidence.

Returns economics audit
Cashflow contract already states: on RETURN you reverse cash-in and reverse COGS back to inventory, but delivery fee stays as cost. 

CASHFLOW_TRUTH_CONTRACT_2026-01…


Add a strict validator that checks returned orders reduce economics by at least the delivery-fee impact (and don’t quietly disappear from the month).

Monthly payout reconciliation (cash reality check)
Add a validator that compares:

economics NetRev by month
vs

cashflow payouts + adjustments by month
and flags deviations beyond tolerance (separating timing vs logic errors). This gives “bank-truth anchored” confidence.

Reproducible evidence chain (the exact green path)

Run in this order; stop immediately on first fail:

Reference truth

python3 scripts/export_sales_archive_statusdate_mapped.py --since 2025-06-06 --until 2026-03-04 --strict

python3 scripts/validate_reference_freshness.py --as-of 2026-03-04 --strict

Identity truth

python3 scripts/validate_recent_identity_coverage.py --as-of 2026-03-04 --strict

If FAIL: backfill (with DB backup + gated apply), then rerun validator.

Ads truth

Ensure ads DB is fresh (scheduler or manual scrape)

python3 scripts/backup_db.py --db db/app.db

python3 scripts/sync_ads_sidecar.py --since 2025-06-06 --until 2026-03-04

ENABLE_CASHFLOW_WRITE=1 python3 scripts/sync_ads_sidecar.py --since 2025-06-06 --until 2026-03-04 --apply

python3 scripts/validate_ads_sidecar_readiness.py --as-of 2026-03-04 --strict

Owner truth publication

python3 scripts/system_doctor.py --strict --as-of 2026-03-04

python3 scripts/build_owner_pnl_report.py --as-of 2026-03-04 --since 2025-06-06 --include-store-breakdown --strict

---

Execution status (2026-03-04):
- Implemented and replayed with transcript:
  `exports/validation/clearence_plan_2026-03-04/full_execution_transcript.md`
- Current strict chain outcome in transcript:
  - `validate_reference_freshness --strict`: PASS
  - `validate_recent_identity_coverage --strict`: PASS
  - `validate_ads_sidecar_readiness --strict`: PASS
  - `validate_sales_vs_waybill_parity --strict`: PASS
  - `system_doctor --strict --as-of 2026-03-04`: GREEN
  - `build_owner_pnl_report --strict`: PASS

Key policy alignments applied:
- Reference freshness default lag updated to 7 days (as this clearance plan specifies).
- Status-date strict cutover aligned to `2026-02-27` across doctor/economics validators/contracts.
- Waybill parity guards hardened against stale cache drift:
  - Ops selector parity skips strict cache-vs-archive checks when cache is newer than the archived run manifest.
  - Business-insides waybill snapshot now falls back to archived run snapshot on cache underflow (project-scope only).
  - Sales-vs-waybill parity now respects shipped-truth primary mode when BUSINESS_INSIDES uses that source.
