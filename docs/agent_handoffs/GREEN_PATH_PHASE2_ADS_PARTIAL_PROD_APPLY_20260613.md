# Green Path Phase 2 Ads Partial Production Apply - 2026-06-13

Gate: YELLOW_PARTIAL

Repo: `~/Docs/Autonomous_business`
Branch: `greenpath/20260613-phase2-truth`
Production DB: `~/Docs/Autonomous_business/db/app.db`
Evidence root: `~/Docs/Autonomous_business/exports/validation/agent21_ads_partial_prod_apply_20260613/`
Backup: `~/Docs/Autonomous_business/exports/validation/agent21_ads_partial_prod_apply_20260613/backups/app_before_agent21_ads_partial_apply_20260613.db`

## Result

Agent 21 returned `Gate: YELLOW`, but proved a safe partial AB-local Kaspi ads refresh. The orchestrator accepted and serialized only that partial write.

This does not clear owner publication. It clears `src_ab_db_ads_truth` from stale to fresh and preserves the remaining blockers honestly.

Production deltas:

| table | before rows | after rows | delta | before max | after max |
| --- | ---: | ---: | ---: | --- | --- |
| `ads_source_refresh_runs` | 556 | 558 | +2 | 2026-05-11 | 2026-06-13 |
| `ads_campaign_product_daily` | 2709 | 2713 | +4 | 2026-05-11 | 2026-06-13 |

Materializer summary:

- `source_rows=14`
- `mapped_rows=4`
- `unmapped_rows=10`
- `refresh_rows=2`
- `source_issues=[]`
- STOREB no-spend product-code rows were preserved as unmapped evidence; no positive spend was hidden or fabricated.

## Source Readback

Run id: `agent21_ads_partial_prod_apply_20260613`

| source | status | blocks_publication | max_observed_at | row_count |
| --- | --- | ---: | --- | ---: |
| `src_ab_db_ads_truth` | `FRESH` | 0 | 2026-06-13T00:00:00+05:00 | 3271 |
| `src_web_automation_kaspi_marketing_directapi` | `FRESH` | 0 | 2026-06-13T23:59:59+05:00 | 6 |
| `src_facebook_ads_external_ads` | `BLOCKED` | 1 | 2026-06-13T23:59:59+05:00 | 1 |
| `src_ab_db_stock_truth` | `STALE` | 1 | 2026-06-13T00:00:00+05:00 | 77002 |

Gate readback:

| gate | status |
| --- | --- |
| `ads_source_truth` | `BLOCKED` |
| `cashflow_source_truth` | `PASS` |
| `exception_queue` | `PASS` |
| `manual_approvals` | `PASS` |
| `po_source_truth` | `PASS` |
| `policy_registry` | `PASS` |
| `source_freshness` | `BLOCKED` |
| `stock_source_truth` | `BLOCKED` |
| `wiki_context_routing` | `PASS` |

## Validator Readback

Passing:

- `PRAGMA integrity_check`: `ok`
- `scripts/validate_ads_sidecar_readiness.py --db db/app.db --as-of 2026-06-13 --readiness-mode live --strict`: `PASS`
- `scripts/check_no_db_tracked.sh`: `DB guard OK`
- `scripts/manage_business_automation.py verify --scope daily-ops --expect paused`: `OK`, `0/10 loaded`

Expected retained failures:

- `scripts/validate_policy_source_freshness.py --db db/app.db --as-of 2026-06-13 --strict --json` fails only on:
  - `src_ab_db_stock_truth`
  - `src_facebook_ads_external_ads`
- `scripts/validate_policy_gate_results.py --db db/app.db --strict --json` fails on:
  - `ads_source_truth`
  - `source_freshness`
  - `stock_source_truth`
- `scripts/validate_ads_offer_universe_coverage.py --db-path db/app.db --as-of 2026-06-13 --start 2026-06-13 --end 2026-06-13 --strict` still fails on:
  - `ACMEWEAR/LINE-31-TS`, one sold line, `9179.0` KZT net revenue, not covered.

Evidence files:

- `~/Docs/Autonomous_business/exports/validation/agent21_ads_partial_prod_apply_20260613/pre/`
- `~/Docs/Autonomous_business/exports/validation/agent21_ads_partial_prod_apply_20260613/prod_materializer_dry_run_report.json`
- `~/Docs/Autonomous_business/exports/validation/agent21_ads_partial_prod_apply_20260613/prod_materializer_apply_report.json`
- `~/Docs/Autonomous_business/exports/validation/agent21_ads_partial_prod_apply_20260613/materialize_policy_source_freshness.json`
- `~/Docs/Autonomous_business/exports/validation/agent21_ads_partial_prod_apply_20260613/materialize_policy_gate_results.json`
- `~/Docs/Autonomous_business/exports/validation/agent21_ads_partial_prod_apply_20260613/post/`

## Remaining Blockers

1. `src_facebook_ads_external_ads` remains `BLOCKED` because Agent 17 proved real Meta spend on 2026-06-13 (`124.64` KZT). Current AB code requires a positive-spend external ads ingestion lane; a no-spend freshness packet cannot clear it.
2. `ACMEWEAR/LINE-31-TS` remains uncovered for 2026-06-13. It needs exact mapped ads evidence, source-backed no-spend evidence, or a narrow policy-backed quarantine.
3. `src_ab_db_stock_truth` remains `STALE` because `fact_inventory_snapshot_size` cannot rebuild through 2026-06-13 while 15 negative stock ledger balances remain.

## Rollback

If this partial ads apply must be reverted:

```bash
cd ~/Docs/Autonomous_business
sqlite3 db/app.db ".restore 'exports/validation/agent21_ads_partial_prod_apply_20260613/backups/app_before_agent21_ads_partial_apply_20260613.db'"
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
PYTHONPATH=. .venv/bin/python scripts/validate_policy_source_freshness.py --db db/app.db --as-of 2026-06-13 --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_policy_gate_results.py --db db/app.db --strict --json
```

