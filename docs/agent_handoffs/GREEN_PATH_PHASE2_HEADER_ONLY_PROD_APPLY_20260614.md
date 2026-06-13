# Green Path Phase 2 Header-Only Production Apply

Gate: GREEN

Date: 2026-06-14

## Scope

This lane hardened and used the STOREB header-only source-gap production wrapper to apply the already-proven 251-row cleanup to `db/app.db`.

The lane did not synthesize item entries, did not use header fields as canonical product truth, and did not replace the production DB file with a staging file. It removed product-level publication leakage for header-only orders that still have no real API item-entry evidence.

Overall Phase 2 remains blocked by separate stock, order-entry, and lifecycle issues.

## Code Safety Change

Updated:

- `scripts/apply_header_only_source_gap_quarantine_production_safe.py`
- `scripts/materialize_header_only_source_gap_quarantine.py`
- `tests/test_header_only_source_gap_quarantine_prod_wrapper.py`

The direct materializer still refuses direct production `db/app.db` CLI apply by default. The production wrapper now:

1. verifies the production env gate,
2. verifies no SQLite sidecars exist,
3. verifies target DB SHA and integrity,
4. creates a SQLite backup,
5. proves exact deltas on a SQLite-backup staging DB,
6. rechecks target DB SHA,
7. applies in place to the target DB,
8. records rollback metadata.

Wrapper result field:

```text
target_replaced=False
write_mode=sqlite_in_place
```

## Evidence

Copied DB proof:

- root: `exports/validation/orchestrator_header_only_wrapper_hardened_proof_20260614/`
- summary: `exports/validation/orchestrator_header_only_wrapper_hardened_proof_20260614/wrapper_copied_db_apply/summary.json`
- copied DB pre-SHA: `0b61507e43061f13d7b58e4f9d0dd551f23efb8b3b16d7af81d91c2286cb0253`
- copied DB post-SHA: `a0a2aa9b957fb36e42a4d64af736ff6c17de0e367e0aaba45494f7d2677ac6be`

Production apply:

- root: `exports/validation/orchestrator_header_only_prod_apply_20260614/`
- summary: `exports/validation/orchestrator_header_only_prod_apply_20260614/wrapper_prod_apply/summary.json`
- pre-SHA: `75047bd9ca6d80573d1ea302543978e062061a50f13dac48a719286d3ef7ee26`
- post-SHA: `04a1e8a1ffbd0530ca6a435050f9d71a670d6f3e5eef4ffa4b350d5a6e347116`
- backup: `exports/validation/orchestrator_header_only_prod_apply_20260614/backups/app_2026-06-14_004623.db`
- backup SHA: `40e9fa7b4af7b5d7aa46b81206cfc234f21fd0b037d384bdcd1a9a9528fdb6e5`

Production apply deltas:

```text
candidate_rows=251
deleted_product_cashflow_rows=7
deleted_stock_ledger_rows=0
nulled_sales_fact_product_profit_rows=0
cash_in_before_count=262
cash_in_after_count=262
cash_in_preserved=True
fact_order_entries_inserted=0
header_fields_used_as_canonical_item_entry_truth=False
```

Daily-ops safety:

- before apply: `exports/validation/orchestrator_header_only_prod_apply_20260614/daily_ops_paused_before_prod_apply.json`
- after apply: `exports/validation/orchestrator_header_only_prod_apply_20260614/daily_ops_paused_after_prod_apply.json`
- result both times: `0/10` loaded, protected surfaces quiet, cron quiet.

## Validation

Focused tests:

```bash
pytest -q tests/test_header_only_source_gap_quarantine.py tests/test_header_only_source_gap_quarantine_prod_wrapper.py
python3 -m py_compile scripts/materialize_header_only_source_gap_quarantine.py scripts/apply_header_only_source_gap_quarantine_production_safe.py
```

Result:

```text
8 passed
py_compile passed
```

Operational stock integration after production apply:

- file: `exports/validation/orchestrator_header_only_prod_apply_20260614/operational_stock_after_prod_apply.json`
- status: `RED`
- finding_count: `496`

Post-apply finding census:

```text
ERROR ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_ENTRY_LEAK            1
ERROR ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_PRODUCT_COGS_LEAK    1
ERROR ORDER_ENTRY_MISSING                                   219
ERROR ORDER_LIFECYCLE_MISSING_COMPLETED                       8
WARN  ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED         244
WARN  ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED                23
```

C3 strict validators after production apply:

- `validate_policy_source_freshness_strict.json`: `ok=false`
- `validate_policy_gate_results_strict.json`: `ok=false`

Retained C3 blockers:

```text
Required source src_ab_db_stock_truth freshness for requested as-of 2026-06-13 is STALE and blocks publication (blocks_publication=1)
Required C3 gate source_freshness is BLOCKED and blocks owner publication
Required C3 gate stock_source_truth is BLOCKED and blocks owner publication
```

Remaining negative stock rows:

- `exports/validation/orchestrator_header_only_prod_apply_20260614/negative_stock_rows_20260613.txt`

## Rollback

Rollback DB backup:

```text
~/Docs/Autonomous_business/exports/validation/orchestrator_header_only_prod_apply_20260614/backups/app_2026-06-14_004623.db
```

Rollback command recorded in the production summary:

```bash
python3 - <<'PY'
import sqlite3
backup_path = '~/Docs/Autonomous_business/exports/validation/orchestrator_header_only_prod_apply_20260614/backups/app_2026-06-14_004623.db'
target_db = '~/Docs/Autonomous_business/db/app.db'
with sqlite3.connect(backup_path) as source, sqlite3.connect(target_db) as target:
    source.backup(target)
PY
```

Then verify:

```bash
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
```

## Remaining Work

Next safe repair lane:

1. Resolve `906730647` as a real-entry de-quarantine or reclassification repair.
2. Repair or strictly quarantine the 219 `ORDER_ENTRY_MISSING` rows.
3. Repair the 8 `ORDER_LIFECYCLE_MISSING_COMPLETED` rows.
4. Apply the 9 owner-approval stock rows only after exact approval evidence exists.
5. Rebuild the 2026-06-13 stock snapshot and replay C3.

