# PLAN_KASPI_ADS_REAL_WORLD_ACTIVATION_V1

## Objective
Turn Ads WT V1 (Phases 0–5) into a *real operational decision loop* for LINE61:
- Know what 30k/day spend produces (views/clicks/orders/cost) with hour-by-hour attribution
- Find the bid “sweet spot” quickly using existing daily history + new hourly telemetry
- Keep capital risk low: no uncontrolled write automation, explicit stop/rollback procedures

## Non‑negotiables (Safety)
- Work ONLY in: ~/Docs/Autonomous_business__wt_ads_v1
- Bid writes remain OFF unless ALL true:
  - config/kaspi_ads_bid_rules.yaml safety.dry_run == false
  - ENABLE_KASPI_ADS_WRITE=1
  - --apply passed
  - bid_api_discovery.json is real (post discovery, no secrets)
- Before any scheduled bid changes:
  - do ONE manual bid change
  - monitor ad_score at 24h/48h/7d
  - halt if score degrades

(These are requirements from PLAN_KASPI_ADS_WT_V1 / Blueprint B.)

## Phase 6A — Make the WT “mergeable” (blocks integration)
1) In WT, commit everything currently untracked into clean phase-chunk commits:
   - Phase 0: kaspi_ads_paths + wiring
   - Phase 1: hourly snapshot/delta + tests + plist
   - Phase 2: hourly profile/reconciliation + tests
   - Phase 3–4: discovery + bid manager + rules + bids plist + tests
   - Phase 5: elasticity + tests
   - Docs: merged plan docs + discovery template

2) Re-run gates after commits:
   - python3 scripts/validate_params.py --strict
   - PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
   - scripts/lint_docs.sh
   - scripts/check_no_db_tracked.sh

3) Regenerate a fresh oracle pack AFTER git status is clean.

## Phase 6B — Start telemetry immediately (no writes)
### One-time: confirm CLI + DB path
Use the existing args of the hourly script:
- python3 scripts/kaspi_ads_hourly_snapshot.py --help

Recommended initial run (dry, safe):
- python3 scripts/kaspi_ads_hourly_pipeline.py \
    --ads-db db/kaspi_marketing_ads_wt.db \
    --stores-config config/kaspi_ads_hourly_stores.yaml \
    --env-file ~/Docs/Autonomous_business/.env \
    --tolerance-pct 5.0

Then build the profile:
- python3 scripts/kaspi_ads_build_hourly_profile.py \
    --ads-db db/kaspi_marketing_ads_wt.db

### Turn on hourly schedule (still no writes)
Use config/com.example.kaspi-marketing-hourly.plist (points to WT + logs + stores config + env file).
Enable it in *user space* only after the manual run works and logs look clean.

### Acceptance for telemetry
- hourly_snapshot increases each hour
- hourly_delta has no weird negatives (resets flagged)
- hourly_reconciliation within tolerance (if daily_current present)

## Phase 6C — Get the “sweet spot” now using Phase 5 (daily history)
Run the optimizer right away (no need to wait for hourly):
- python3 scripts/kaspi_ads_elasticity.py \
    --ads-db db/kaspi_marketing_ads_wt.db \
    --app-db db/app.db \
    --campaign-ids 2545773 \
    --min-days 7 \
    --default-margin-pct 0.35 \
    --out-dir reports/marketing

Review:
- kaspi_ads_bid_recommendations.csv
- kaspi_ads_elasticity_summary.json

Decision output:
- recommended base bid for LINE61 (static first)
- expected profit delta vs cost (with confidence guards)

## Phase 6D — Fix config to target LINE61 only
1) Validate the real (campaign_id, sku_key) pairs in DB for LINE61.
2) Update config/kaspi_ads_bid_rules.yaml allowlist to *one* LINE61 pair only:
   - campaign_id should be 2545773 for LINE61
   - sku_key must match that campaign in DB

Keep safety.dry_run=true for now.

## Phase 6E — Bid write discovery (one-time operator session)
Run:
- python3 scripts/kaspi_ads_discover_bid_write_api.py

Operator steps:
- open the exact campaign product page
- manually change ONE bid in UI
- capture network request
- save sanitized payload into docs/marketing/bid_api_discovery.json (no cookies/tokens)

## Phase 6F — Dry-run bid manager against real data
Run bid manager without --apply and confirm it:
- proposes changes
- logs would_change into bid_change_log
- respects cooldown/max_daily_changes/max_step

## Phase 6G — Patch rollback to be real before any live canary
Current code refuses live rollback.
Implement live rollback using the same discovery payload mechanism as live writes.
Add a test that asserts rollback can execute in live mode (but keep it gated).

## Phase 6H — Controlled canary (ONLY after rollback is real)
Scope:
- LINE61 only (one campaign + one sku_key)
Schedule:
- 02:00 reduce (multiplier 0.5)
- 07:00 restore (1.0)
Stop conditions:
- ad_score drops materially
- spend spikes without orders
- reconciliation drift > tolerance
Rollback:
- --rollback-last-good must restore previous bid via live write

## Phase 6I — Promotion to main repo (fast + safe)
1) Create a new promotion worktree (separate from WT):
   - cherry-pick ONLY the phase commits (no runtime db files)
2) In the promotion WT, run full gates again.
3) Merge into main with defaults OFF:
   - dry_run true
   - ENABLE_KASPI_ADS_WRITE not set
   - ALLOW_PROD_ADS_DB not set
