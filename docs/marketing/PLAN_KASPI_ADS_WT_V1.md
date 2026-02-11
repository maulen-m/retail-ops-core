# PLAN_KASPI_ADS_WT_V1

Merged execution plan for the ads worktree branch `ads/TASK-kaspi-ads-wt-v1`.

Sources merged:
- `docs/ideas/KASPI_ADS_MAX_EFFICIENCY_AND_PROFIT_GROWTH_PLAN_A).md`
- `docs/ideas/KASPI_ADS_IMPLEMENTATION_BLUEPRINT_B).md`
- `docs/ideas/PLAN_KASPI_ADS_WT_V1.md` (Plan C)

## Objective
Build a safe ads-leveraging system in the dedicated worktree:
1. Hourly telemetry collection and delta quality controls
2. Hourly behavior profiles + daily reconciliation
3. Bid manager with strict dry-run/write guards
4. Controlled canary automation artifacts (worktree-only)
5. Offline elasticity + profit/ROIC optimizer

## Hard Safety Contract
- Work only in `~/Docs/Autonomous_business__wt_ads_v1`
- Never write to production ads DB unless explicitly overridden:
  - production path: `External_database/Kaspi_marketing/db/kaspi_marketing.db`
  - guard variable: `ALLOW_PROD_ADS_DB=1`
- All ads scripts accept `--ads-db` and/or `KASPI_MARKETING_DB_PATH`
- Bid writes require BOTH:
  - `--apply`
  - `ENABLE_KASPI_ADS_WRITE=1`
- Default mode is dry-run
- No `launchctl load` in this branch

## Phase 0: Worktree DB Isolation + Production Guard
Deliverables:
- `scripts/kaspi_ads_paths.py`
- path resolution precedence: `--ads-db` > `KASPI_MARKETING_DB_PATH` > safe default
- copy-once helper for worktree DB bootstrap
- production path refusal unless `ALLOW_PROD_ADS_DB=1`

Acceptance:
- tests pass for path override, guard refusal, and copy-once behavior

## Phase 1: Hourly Snapshot + Delta Collector
Deliverables:
- `scripts/kaspi_ads_hourly_snapshot.py`
- tables: `hourly_snapshot`, `hourly_delta`
- lock file guard: `logs/.kaspi_ads_lock`
- idempotent upserts
- reset-aware delta logic (no negative deltas; flagged as reset anomalies)
- retry/backoff for rate-limit and transient API failures
- sample plist: `config/com.example.kaspi-marketing-hourly.plist`

Acceptance:
- tests pass for idempotency, reset handling, lock behavior, and backoff

## Phase 2: Hourly Profile + Reconciliation
Deliverables:
- `scripts/kaspi_ads_build_hourly_profile.py`
- tables: `hourly_activity_profile`, `hourly_reconciliation`
- reconciliation against `campaign_product_daily_current` with configurable tolerance

Acceptance:
- tests pass for reconciliation pass/fail cases and profile generation

## Phase 3: Bid Discovery + Safe Bid Manager
Deliverables:
- `scripts/kaspi_ads_discover_bid_write_api.py`
- discovery output template/artifact: `docs/marketing/bid_api_discovery.json`
- rules config: `config/kaspi_ads_bid_rules.yaml`
- `scripts/kaspi_ads_bid_manager.py`
- table: `bid_change_log`
- sample plist: `config/com.example.kaspi-marketing-bids.plist`

Safety:
- dry-run by default
- write gate requires `--apply` + `ENABLE_KASPI_ADS_WRITE=1`
- min/max bid, max step, max daily changes, cooldown, allowlist
- full audit log for every proposed/executed action

Acceptance:
- tests pass for dry-run logs, write gating, and guardrails

## Phase 4: Controlled Canary Automation (Worktree-only)
Deliverables:
- conservative schedule artifact (02:00 reduce, 07:00 restore)
- canary starts from allowlist scope only
- rollback command supported by bid-change log history

Operational protocol:
1. Run dry-run for multiple days and review logs
2. Execute one manual API change
3. Monitor `ad_score` at 24h / 48h / 7d
4. Only then consider live canary write enablement

## Phase 5: Elasticity + Profit/ROIC Optimizer (Offline First)
Deliverables:
- `scripts/kaspi_ads_elasticity.py`
- outputs to `reports/marketing/`:
  - `kaspi_ads_elasticity_levels.csv`
  - `kaspi_ads_elasticity_transitions.csv`
  - `kaspi_ads_bid_recommendations.csv`
  - `kaspi_ads_elasticity_summary.json`

Method:
- aggregate daily ads metrics by bid level
- compute click/order elasticity between adjacent bids
- estimate profit and ROIC using app DB economics where available
- fall back to configurable margin when economics are missing

## Phase 6: Promotion (Later)
Not implemented in this branch.
Promotion is a separate action after stable telemetry, clean reconciliation, and canary confidence.

## Required Gate Commands
Run in this order before declaring success:

```bash
python3 scripts/validate_params.py --strict
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
scripts/lint_docs.sh
scripts/check_no_db_tracked.sh
```

## Rollback
If branch/worktree rollback is needed:

```bash
git worktree remove ~/Docs/Autonomous_business__wt_ads_v1
git branch -D ads/TASK-kaspi-ads-wt-v1
```
