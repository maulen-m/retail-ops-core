# UNIVERSAL Ads Hourly Integration Notes (2026-02-13)

## Scope
- Integrated UNIVERSAL ads ingest into the same hourly telemetry workflow used for ACMEWEAR.
- Worktree-only path: `~/Docs/Autonomous_business__wt_ads_v1`.
- No live bid writes enabled in this integration.

## Implemented Changes
- Added store-target config for hourly ingest:
  - `config/kaspi_ads_hourly_stores.yaml`
  - `ACMEWEAR` merchant `759051` with `credential_profile=default`
  - `UNIVERSAL` merchant `761413` with `credential_profile=universal`
- Extended hourly snapshot collector:
  - `scripts/kaspi_ads_hourly_snapshot.py`
  - new `--merchant-ids`, `--credential-profile`, `--env-file`
  - env-file loader + merchant-id parser + credential-profile resolver
  - per-merchant summary in JSON output
- Extended hourly pipeline orchestrator:
  - `scripts/kaspi_ads_hourly_pipeline.py`
  - new `--stores-config` support
  - runs per-store snapshot jobs, then one profile/reconciliation pass
- Updated hourly launchd template:
  - `config/com.example.kaspi-marketing-hourly.plist`
  - now points to stores config + env file for credentials.

## Idempotency and Scalability
- Idempotent DB writes preserved:
  - `hourly_snapshot` unique key: `(date, snapshot_hour, merchant_id, campaign_id, sku_key)`
  - `hourly_delta` unique key: `(date, hour_start, hour_end, merchant_id, campaign_id, sku_key)`
- Multi-store scaling is config-driven:
  - add store entries to `config/kaspi_ads_hourly_stores.yaml`
  - no code changes needed for additional merchants.
- Cross-account reliability:
  - per-store `profile_dir` prevents session collisions between ACMEWEAR and UNIVERSAL accounts.

## Live Validation Run (This Session)
Command executed:
```bash
python3 scripts/kaspi_ads_hourly_pipeline.py \
  --ads-db db/kaspi_marketing_ads_wt.db \
  --stores-config config/kaspi_ads_hourly_stores.yaml \
  --env-file ~/Docs/Autonomous_business/.env \
  --tolerance-pct 5.0
```

Observed results:
- ACMEWEAR (`759051`):
  - rows collected: `1`
  - campaign_ids seen: `2380614`
- UNIVERSAL (`761413`):
  - rows collected: `21`
  - campaign_ids seen: `2566809`, `2572387`, `2572822`, `2572825`
- Profile build executed after both store ingests and completed successfully.

## Universal Discovery Findings
- Inventory file:
  - `docs/marketing/universal_ads_campaign_inventory_2026-02-13.json`
- Ingest probe file:
  - `docs/marketing/universal_ads_ingest_probe_2026-02-13.json`
- Confirmed `line52` campaigns:
  - `2566809` (`Line52_bundle`)
  - `2572387` (`Line52_bad_ratings`)

## Action Notes
- Keep hourly job on integrated stores-config mode.
- If adding more stores, append to `config/kaspi_ads_hourly_stores.yaml` with:
  - `merchant_id`
  - `credential_profile`
  - isolated `profile_dir`
- Continue dry-run bid governance unchanged until explicit live-write authorization.
