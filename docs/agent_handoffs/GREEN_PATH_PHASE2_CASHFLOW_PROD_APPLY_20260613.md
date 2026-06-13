# Green Path Phase 2 Cashflow Production Apply - 2026-06-13

Gate: GREEN

Repo: `~/Docs/Autonomous_business`
Branch: `greenpath/20260613-phase2-truth`
Production DB: `~/Docs/Autonomous_business/db/app.db`
Evidence root: `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/`
Backup: `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/backups/app_before_agent18_cashflow_d1_prod_apply_20260613.db`

## Result

The Agent 18 copied-DB proof was accepted and serialized into production after daily operations were verified paused.

Cashflow source truth is now green in production:

- `cash_in_missing_count`: `1314 -> 0`
- `duplicate_cash_in_count`: remains `0`
- `balance_anchor_fake_cash_in_count`: remains `0`
- `fact_cashflow_events`: `72538 -> 74026`
- `fact_cashflow_daily`: remains `888`
- production apply run id: `agent18_cashflow_d1_prod_apply_20260613`

Rows inserted under `agent18_cashflow_d1_prod_apply_20260613`:

| event_type | rows | amount_kzt |
| --- | ---: | ---: |
| `CASH_IN` | 1341 | 8062114.83 |
| `INVENTORY_MOVE` | 120 | 0.00 |
| `INVENTORY_RETURN` | 27 | 95765.68 |

## Commands And Evidence

Pre-write evidence:

- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/pre/backup_integrity.txt`
- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/pre/app_db_sha256_before.txt`
- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/pre/counts_before.txt`
- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/pre/order_cashflow_coverage_before.json`

Write reports:

- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/orders_to_cashflow_dryrun_report.txt`
- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/orders_to_cashflow_apply_report.txt`
- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/rebuild_cashflow_calendar_apply.txt`
- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/materialize_policy_source_freshness.json`
- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/materialize_policy_gate_results.json`

Post-write evidence:

- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/post/app_integrity_after.txt`
- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/post/app_db_sha256_after.txt`
- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/post/order_cashflow_coverage_after.json`
- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/post/cashflow_invariants_after.txt`
- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/post/policy_gate_results_after.json`
- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/post/policy_source_freshness_after.json`
- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/post/daily_ops_paused_after.txt`
- `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/post/check_no_db_tracked_after.txt`

## Validator Readback

Passing:

- `PRAGMA integrity_check`: `ok`
- `scripts/validate_order_cashflow_coverage.py --db db/app.db --as-of 2026-06-13 --strict --json`: `PASS`
- `scripts/validate_cashflow_invariants.py --db db/app.db`: `PASS: 888 days validated`
- `scripts/manage_business_automation.py verify --scope daily-ops --expect paused`: `OK`, `0/10 loaded`
- `scripts/check_no_db_tracked.sh`: `DB guard OK`

Expected retained blockers after cashflow apply:

- `ads_source_truth`
- `source_freshness`
- `stock_source_truth`

Strict source freshness retained blockers:

- `src_ab_db_ads_truth`: `STALE`
- `src_ab_db_stock_truth`: `STALE`
- `src_facebook_ads_external_ads`: `BLOCKED`

Gate materialization run `agent18_cashflow_d1_prod_gates_20260613` readback:

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

## Rollback

If this production apply must be reverted, restore the pre-write backup:

```bash
cd ~/Docs/Autonomous_business
sqlite3 db/app.db ".restore 'exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/backups/app_before_agent18_cashflow_d1_prod_apply_20260613.db'"
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
PYTHONPATH=. .venv/bin/python scripts/validate_order_cashflow_coverage.py --db db/app.db --as-of 2026-06-13 --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_cashflow_invariants.py --db db/app.db
PYTHONPATH=. .venv/bin/python scripts/validate_policy_gate_results.py --db db/app.db --strict --json
```

