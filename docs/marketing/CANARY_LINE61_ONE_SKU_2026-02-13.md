# LINE61 One-SKU Canary Plan (2026-02-13)

## Scope
- Campaign: `2545773` (`ACMEWEAR_LINE61`)
- SKU: `19796919b`
- Worktree only DB/config:
  - `db/kaspi_marketing_ads_wt.db`
  - `config/kaspi_ads_bid_rules.yaml`
  - `docs/marketing/bid_api_discovery.json`

## Preconditions (must all be true)
1. Ads resumed after pause recorded at `2026-02-12 22:00` and stable for at least 24 hours.
2. Stock gate passes for LINE61 SKU (`19796919b`) with enough units to support incremental clicks.
3. Live rollback path is implemented and test-covered (`tests/test_kaspi_ads_bid_manager.py`).
4. Discovery payload present and sanitized.
5. Write gate armed only for canary window:
   - `safety.dry_run=false`
   - `ENABLE_KASPI_ADS_WRITE=1`
   - run with `--apply`

## Canary Schedule
- 02:00 local: reduce bid using schedule multiplier `0.5`
- 07:00 local: restore bid using schedule multiplier `1.0`

## Operator Commands

### 02:00 Reduce (live, gated)
```bash
ENABLE_KASPI_ADS_WRITE=1 \
python3 scripts/kaspi_ads_bid_manager.py \
  --ads-db db/kaspi_marketing_ads_wt.db \
  --rules config/kaspi_ads_bid_rules.yaml \
  --discovery-file docs/marketing/bid_api_discovery.json \
  --apply \
  --now-local 2026-02-14T02:00:00+05:00
```

### 07:00 Restore (live, gated)
```bash
ENABLE_KASPI_ADS_WRITE=1 \
python3 scripts/kaspi_ads_bid_manager.py \
  --ads-db db/kaspi_marketing_ads_wt.db \
  --rules config/kaspi_ads_bid_rules.yaml \
  --discovery-file docs/marketing/bid_api_discovery.json \
  --apply \
  --now-local 2026-02-14T07:00:00+05:00
```

### Emergency Rollback (live)
```bash
ENABLE_KASPI_ADS_WRITE=1 \
python3 scripts/kaspi_ads_bid_manager.py \
  --ads-db db/kaspi_marketing_ads_wt.db \
  --rules config/kaspi_ads_bid_rules.yaml \
  --discovery-file docs/marketing/bid_api_discovery.json \
  --apply \
  --rollback-last-good
```

## Stop Conditions
1. `ad_score` drops materially versus baseline within 24h.
2. Spend rises sharply without order conversion.
3. Hourly-vs-daily reconciliation drift exceeds tolerance.
4. Any live write error appears in `bid_change_log`.

## Monitoring Checklist
- `bid_change_log` entries show `success=1` and expected `new_bid`.
- `hourly_snapshot` and `hourly_delta` continue updating each hour.
- `hourly_reconciliation` does not trend worse after canary changes.
