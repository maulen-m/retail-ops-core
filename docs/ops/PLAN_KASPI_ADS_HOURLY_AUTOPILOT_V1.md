# PLAN_KASPI_ADS_HOURLY_AUTOPILOT_V1

## Objective
Operate Kaspi ads hourly telemetry and trust loop with near-zero manual effort in WT:
- hourly snapshot/profile pipeline remains automated
- daily trust loop runs automatically
- stable logs and stable report artifacts are always available for operators

## Scope
- In scope:
  - hourly pipeline launchd runbook contract
  - daily trust loop orchestration (healthcheck + coverage + daily brief)
  - launchd sample artifacts for daily jobs
  - success-verification tests for orchestrator/plists/runbook consistency
- Out of scope:
  - bid write automation changes
  - alert delivery channels (Telegram/email) in this phase
  - live launchctl load/bootstrap during implementation

## Design
### Hourly path
- Existing launchd job:
  - `config/com.example.kaspi-marketing-hourly.plist`
  - triggers `scripts/kaspi_ads_hourly_pipeline.py` every hour at `:05`

### Daily trust loop path
- New orchestrator script:
  - `scripts/kaspi_ads_daily_trust_loop.py`
- Sequence:
  1. `scripts/kaspi_ads_healthcheck.py`
  2. `scripts/kaspi_ads_campaign_coverage_report.py`
  3. `scripts/kaspi_ads_elasticity.py`
- Output:
  - summary JSON: `reports/marketing/trust_loop/kaspi_ads_daily_trust_loop_latest.json`
  - coverage JSON: `reports/marketing/trust_loop/kaspi_ads_campaign_coverage_latest.json`
  - daily brief outputs: `reports/marketing/daily_brief/*`
- Exit policy:
  - non-zero if any trust-loop step fails

## Stable Log and Artifact Paths
- Hourly:
  - `logs/hourly_snapshot_stdout.log`
  - `logs/hourly_snapshot_stderr.log`
- Daily healthcheck:
  - `logs/kaspi_ads_healthcheck_stdout.log`
  - `logs/kaspi_ads_healthcheck_stderr.log`
- Daily coverage:
  - `logs/kaspi_ads_coverage_stdout.log`
  - `logs/kaspi_ads_coverage_stderr.log`
- Daily brief:
  - `logs/kaspi_ads_daily_brief_stdout.log`
  - `logs/kaspi_ads_daily_brief_stderr.log`

## Recommended Schedule (Asia/Almaty)
- Hourly pipeline: every hour at `:05`
- Daily healthcheck: `06:20`
- Daily coverage: `06:25`
- Daily brief generation: `06:40`

## Verification Strategy
Tests-first and fail-first:
1. Orchestrator behavior tests:
   - `tests/test_kaspi_ads_daily_trust_loop.py`
2. Launchd artifact contract tests:
   - `tests/test_kaspi_ads_launchd_artifacts.py`
3. Runbook consistency tests:
   - `tests/test_kaspi_ads_ops_runbook_links.py`

Required gates after implementation:
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q`
- `scripts/lint_docs.sh`
- `scripts/check_no_db_tracked.sh`

## Rollback
If this phase needs rollback:
- remove added script/tests/docs/plists in WT branch and recommit
- no production impact since no launchctl load/bootstrap is performed in this phase
