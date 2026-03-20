# Ads Sidecar Readiness Runtime Split Contract

## Purpose

Separate live owner-truth read readiness from ads sidecar apply readiness without weakening fail-closed write-side freshness rules.

## Modes

### `live`

- Intended for read-only owner-truth proving and publication preparation.
- Validates current usability of `ads_spend_sidecar_daily` in `db/app.db`.
- External marketing DB freshness is recorded, but stale source is a warning rather than a hard failure.
- Live mode still fails if:
  - `ads_spend_sidecar_daily` is missing
  - ads mapping coverage is below threshold
  - sidecar data is otherwise unavailable

### `apply`

- Intended for refresh/apply readiness.
- Requires external marketing DB freshness via `validate_ads_source(...)`.
- Fails closed on stale or missing external ads source.
- Also requires current sidecar usability and mapping coverage.

## Operational rule

- `sync_ads_sidecar.py` remains the write-side freshness gate.
- `run_owner_truth_daily.py --mode live` and `system_doctor.py` must call ads readiness in `live` mode explicitly.
- No live-mode path may treat stale ads source as zero spend.
- No live-mode path may trigger sidecar apply implicitly.

## Output contract

- `validate_ads_sidecar_readiness.py` emits:
  - `readiness_mode`
  - `warnings`
  - `ads_source_status`
  - sidecar availability / coverage checks

## Current decision

- Runtime split accepted because:
  - the external marketing refresh path is auth/session-blocked
  - current sidecar table for the live proving window is populated and mapped
  - apply readiness is already enforced independently by `sync_ads_sidecar.py`
