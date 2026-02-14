# RUNBOOK_KASPI_ADS_HOURLY

## Scope
- Worktree only: `~/Docs/Autonomous_business__wt_ads_v1`
- Objective: keep hourly telemetry + trust loop running with minimal operator time.
- Safety: this runbook does not require bid writes.

## Launchd Jobs
- Hourly telemetry pipeline:
  - Label: `com.example.kaspi-marketing-hourly`
  - Plist: `config/com.example.kaspi-marketing-hourly.plist`
- Daily trust loop healthcheck:
  - Label: `com.example.kaspi-marketing-healthcheck`
  - Plist: `config/com.example.kaspi-marketing-healthcheck.plist`
- Daily campaign coverage check:
  - Label: `com.example.kaspi-marketing-coverage`
  - Plist: `config/com.example.kaspi-marketing-coverage.plist`
- Daily brief generation (elasticity/profit snapshot):
  - Label: `com.example.kaspi-marketing-daily-brief`
  - Plist: `config/com.example.kaspi-marketing-daily-brief.plist`

## Stable Log Paths
- `logs/hourly_snapshot_stdout.log`
- `logs/hourly_snapshot_stderr.log`
- `logs/kaspi_ads_healthcheck_stdout.log`
- `logs/kaspi_ads_healthcheck_stderr.log`
- `logs/kaspi_ads_coverage_stdout.log`
- `logs/kaspi_ads_coverage_stderr.log`
- `logs/kaspi_ads_daily_brief_stdout.log`
- `logs/kaspi_ads_daily_brief_stderr.log`

## Report Output Paths
- Coverage JSON (latest): `reports/marketing/trust_loop/kaspi_ads_campaign_coverage_latest.json`
- Daily brief outputs (latest set):
  - `reports/marketing/daily_brief/kaspi_ads_elasticity_summary.json`
  - `reports/marketing/daily_brief/kaspi_ads_bid_recommendations.csv`
  - `reports/marketing/daily_brief/kaspi_ads_elasticity_levels.csv`

## One-time Install/Update (per job)
Use user LaunchAgents. Do not run in main repo path.

```bash
cd ~/Docs/Autonomous_business__wt_ads_v1
mkdir -p ~/Library/LaunchAgents logs
cp config/com.example.kaspi-marketing-hourly.plist ~/Library/LaunchAgents/
cp config/com.example.kaspi-marketing-healthcheck.plist ~/Library/LaunchAgents/
cp config/com.example.kaspi-marketing-coverage.plist ~/Library/LaunchAgents/
cp config/com.example.kaspi-marketing-daily-brief.plist ~/Library/LaunchAgents/

launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.example.kaspi-marketing-hourly.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.example.kaspi-marketing-healthcheck.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.example.kaspi-marketing-coverage.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.example.kaspi-marketing-daily-brief.plist
```

If already loaded, use `bootout` first:

```bash
launchctl bootout "gui/$(id -u)/com.example.kaspi-marketing-hourly" || true
launchctl bootout "gui/$(id -u)/com.example.kaspi-marketing-healthcheck" || true
launchctl bootout "gui/$(id -u)/com.example.kaspi-marketing-coverage" || true
launchctl bootout "gui/$(id -u)/com.example.kaspi-marketing-daily-brief" || true
```

## Status Checks
List all ads jobs:

```bash
launchctl list | rg "com.example.kaspi-marketing-(hourly|healthcheck|coverage|daily-brief)"
```

Inspect one job in detail:

```bash
launchctl print "gui/$(id -u)/com.example.kaspi-marketing-hourly"
```

Look for:
- `last exit code = 0`
- recent `last fire time`
- no repeated crash loop

## Log Checks
Quick tails:

```bash
tail -n 120 logs/hourly_snapshot_stdout.log
tail -n 120 logs/hourly_snapshot_stderr.log
tail -n 120 logs/kaspi_ads_healthcheck_stdout.log
tail -n 120 logs/kaspi_ads_healthcheck_stderr.log
tail -n 120 logs/kaspi_ads_coverage_stdout.log
tail -n 120 logs/kaspi_ads_coverage_stderr.log
tail -n 120 logs/kaspi_ads_daily_brief_stdout.log
tail -n 120 logs/kaspi_ads_daily_brief_stderr.log
```

Follow hourly live:

```bash
tail -f logs/hourly_snapshot_stdout.log logs/hourly_snapshot_stderr.log
```

## Restart / Manual Trigger
Restart hourly job:

```bash
launchctl bootout "gui/$(id -u)/com.example.kaspi-marketing-hourly"
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.example.kaspi-marketing-hourly.plist
```

Trigger immediately:

```bash
launchctl kickstart -k "gui/$(id -u)/com.example.kaspi-marketing-hourly"
launchctl kickstart -k "gui/$(id -u)/com.example.kaspi-marketing-healthcheck"
launchctl kickstart -k "gui/$(id -u)/com.example.kaspi-marketing-coverage"
launchctl kickstart -k "gui/$(id -u)/com.example.kaspi-marketing-daily-brief"
```

## Common Failure Modes
1. Login failure (`{\"status\":\"login_failed\"}` in hourly stdout)
- Cause: expired session/credentials.
- Checks:
  - `.env` values present for both profiles:
    - `Kaspi_marketing_login`, `Kaspi_marketing_Password`
    - `Kaspi_marketing_login_UNIVERSAL`, `Kaspi_marketing_Password_UNIVERSAL`
  - profile dirs from `config/kaspi_ads_hourly_stores.yaml` exist and are accessible.
- Recovery:
  - run one manual headful login:
    - `python3 scripts/kaspi_ads_hourly_snapshot.py --ads-db db/kaspi_marketing_ads_wt.db --stores-config config/kaspi_ads_hourly_stores.yaml --env-file ~/Docs/Autonomous_business/.env --headful --manual-login`

2. Playwright runtime error
- Symptoms: missing playwright/chrome channel errors in stderr.
- Recovery:
  - `python3 -m pip install playwright`
  - `python3 -m playwright install chromium`

3. Stale telemetry (>2h old snapshots)
- Checks:
  - `python3 scripts/kaspi_ads_healthcheck.py --ads-db db/kaspi_marketing_ads_wt.db --stores-config config/kaspi_ads_hourly_stores.yaml --require-recon-rows`
  - inspect `latest_snapshot_at`/`stale_hours` fields.
- Recovery:
  - kickstart hourly job, then re-run healthcheck after one cycle.

4. Lock contention (`{\"status\":\"skipped_locked\"}`)
- Cause: another ads scrape/snapshot process holds lock `logs/.kaspi_ads_lock`.
- Recovery:
  - wait 1 cycle; if persistent, verify no stuck process, then rerun kickstart.

5. Coverage gaps (expected campaigns missing)
- Checks:
  - `python3 scripts/kaspi_ads_campaign_coverage_report.py --ads-db db/kaspi_marketing_ads_wt.db --stores-config config/kaspi_ads_hourly_stores.yaml --out reports/marketing/trust_loop/kaspi_ads_campaign_coverage_latest.json`
- Recovery:
  - verify campaign inventory JSON in `docs/marketing/*campaign_inventory*.json`
  - verify merchant/store mappings in `config/kaspi_ads_hourly_stores.yaml`

## Recommended Schedule
Local timezone: Almaty (`Asia/Almaty`).

1. Hourly pipeline: every hour at `:05`
- Job: `com.example.kaspi-marketing-hourly`
- Purpose: snapshot + delta + profile/reconciliation refresh

2. Daily healthcheck/trust loop: `06:20` and `06:25`
- Jobs:
  - `com.example.kaspi-marketing-healthcheck` at `06:20`
  - `com.example.kaspi-marketing-coverage` at `06:25`
- Purpose: freshness, reconciliation drift, campaign completeness

3. Daily brief generation: `06:40`
- Job: `com.example.kaspi-marketing-daily-brief`
- Purpose: regenerate elasticity/profit recommendations for operator review
