# Green Path Phase 2 Meta External Spend Production Apply

Gate: GREEN for `src_facebook_ads_external_ads`; retained global blockers remain outside this lane.

Date: 2026-06-13

## Scope

This lane ingested the June 13 ACMEWEAR Meta/Instagram positive-spend proof into Autonomous Business as external spend provenance only.

It did not claim deterministic order, SKU, product, profit, or publication attribution. It did not mutate Meta, Instagram, Kaspi, Telegram, LaunchAgents, workbooks, prices, stock, or customer/operator surfaces.

## Evidence

- Production evidence root: `exports/validation/orchestrator_meta_external_spend_prod_apply_20260613/`
- Source summary: `~/Docs/Business_3/Facebook_ads/runs/ab_source_freshness_20260613_acmewear_meta_spend_boundary/meta_live_refresh_summary.json`
- Source summary SHA-256: `105f4812e278c8ea1d600eca5977c7dd165f18ed62396338b390c76ebcaf6c35`
- Raw evidence: `~/Docs/Business_3/Facebook_ads/runs/ab_source_freshness_20260613_acmewear_meta_spend_boundary/raw_meta_source/2026-06-13/meta_insights_live_readonly_2026-06-13.json`
- Raw evidence SHA-256: `7c48d97b8aec100c67f5b01e778c04d79f80200f971887534e466f4f90079088`
- Account: `1517999585924947`
- Spend amount: `124.64`

## Production Write

- DB backup: `exports/validation/orchestrator_meta_external_spend_prod_apply_20260613/backups/app_before_meta_external_spend_prod_apply_20260613.db`
- Table written: `meta_external_ads_spend_daily`
- Inserted row basis: `source_system=meta_instagram`, `store_code=ACMEWEAR`, `date=2026-06-13`, `publication_attribution_claimed=0`
- C3 replay: `src_facebook_ads_external_ads` became `FRESH`

## Validation

- Daily ops verified paused before write: `exports/automation_control/2026-06-13/20260613_230820_verify_daily-ops`, `0/10 loaded`
- Telegram/customer/operator/external campaign writes: none
- DB guard: passed
- C3 retained blockers after this lane were not Meta blockers; remaining blockers were stock/source related.

## Rollback

Use the DB backup above if the Meta provenance row must be reverted:

```bash
sqlite3 db/app.db ".restore 'exports/validation/orchestrator_meta_external_spend_prod_apply_20260613/backups/app_before_meta_external_spend_prod_apply_20260613.db'"
```

After rollback, rerun C3 policy materialization and the ads validators before any owner-facing publication.
