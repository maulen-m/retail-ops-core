# Ads Sidecar Contract

Purpose: integrate marketing spend into profit analytics without introducing write-side risk.

## Integration mode
- Main repo consumes Ads data as a **read-only sidecar**.
- Source DB path resolution order:
  1. `--ads-db` CLI argument
  2. `AB_ADS_DB_PATH`
  3. default external source path (`Kaspi_marketing/db/kaspi_marketing.db`)

## Fail-closed requirements
- Missing ads source file => fail (no synthetic zero spend fallback).
- Stale source file => fail (default max age: 36h).
- Future-mtime skew beyond guard threshold => fail.
- Any write path remains gated with explicit env + `--apply`.

## Canonical helper
Use `core.ads.sidecar_contract`:
- `resolve_ads_db_path(...)`
- `validate_ads_source(...)`

## Operational policy
- Ads metrics are marked `N/A` when source is unavailable/stale.
- Profit-after-ads must not be published as numeric unless ads source contract is green.
