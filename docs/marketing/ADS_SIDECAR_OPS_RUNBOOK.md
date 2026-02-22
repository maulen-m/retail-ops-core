# ADS Sidecar Ops Runbook

## Purpose
Run ads attribution as a read-only sidecar and keep profit publication fail-closed.

## Contracts
- `docs/marketing/ADS_SIDE_CAR_CONTRACT.md`
- `docs/marketing/PROFIT_AFTER_ADS_CONTRACT.md`

## Operational mode
- Default mode is read-only.
- Missing or stale ads data must produce `N/A` for ads-derived metrics, never `0`.
- No bid or write-side actions unless explicitly gated by env + `--apply`.

## Daily commands
1. Sync ads sidecar (read-only mode):
   - `python3 scripts/sync_ads_sidecar.py`
2. Build profit-after-ads outputs:
   - `python3 scripts/build_profit_after_ads.py`
3. Validate strict chain:
   - `python3 scripts/validate_params.py --strict`

## Stop-line criteria
- Sidecar freshness is unknown and profit-after-ads still shows numeric output.
- Any path publishes ads-adjusted metrics as zero when source is missing.
- Any ungated write/apply path becomes reachable.

## Rollback
1. Revert ads sidecar ops changes.
2. Re-run strict gates.
3. Keep ads outputs as `N/A` until freshness is proven.
