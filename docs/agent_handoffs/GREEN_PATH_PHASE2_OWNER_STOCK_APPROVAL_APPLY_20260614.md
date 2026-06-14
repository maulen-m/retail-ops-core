# Green Path Phase 2 Owner Stock Approval Apply

Gate: GREEN

Date: 2026-06-14

## Scope

This lane closed the owner-gated stock stopline for the 9 remaining negative `stock_ledger` balances, rebuilt the `2026-06-13` inventory snapshot, and replayed C3/source-freshness state.

No Kaspi merchant, pricing, workbook, Telegram, LaunchAgent, customer, or operator-message writes were performed.

## Owner Evidence

- Owner evidence file: `exports/validation/orchestrator_owner_approval_stock_stopline_20260614/owner_approval_evidence/owner_stock_approval_20260614.txt`
- Durable owner decision record: `config/owner_decisions/owner_stock_approval_2026_06_14.json`
- Owner compatibility note preserved there: suit 3 in 1 sets and Nike 3 in 1 sets are backwards-compatible with regular suit 3 in 1 sets; S size follows kids 3 in 1 S size.
- Approval manifest: `config/governed_stock_owner_approval_repairs_20260614.json`
- No-approval dry-run blocked all 9 rows, proving the manifest could not self-authorize: `exports/validation/orchestrator_owner_approval_stock_stopline_20260614/dry_run_without_owner_evidence/`

## DB Writes

1. Owner-approved governed stock repair:
   - Production summary: `exports/validation/orchestrator_owner_approval_stock_stopline_20260614/prod_apply/governed_stock_repair_summary.json`
   - Applied rows: `9`
   - Blocked rows: `0`
   - Pre-SHA: `6a3292128172d6f271bd00f1e78da043c07f3e657d542019a700722ad85365cb`
   - Post-SHA: `2a1afca16c8d9044b221a8abb58fbbb24ec31754b7a1245d1329c3bf0678391b`
   - Backup: `exports/validation/orchestrator_owner_approval_stock_stopline_20260614/backups_prod_stock_approval/app_2026-06-14_063651.db`

2. Production-safe inventory snapshot rebuild:
   - Summary: `exports/validation/orchestrator_owner_approval_stock_stopline_20260614/rebuild_snapshot_20260613_apply/summary.json`
   - Snapshot date/store/mode: `2026-06-13` / `UNIVERSAL` / `ledger`
   - Rows created: `419`
   - Current stock total: `9123`
   - Inbound stock total: `475`
   - Pre-SHA: `2a1afca16c8d9044b221a8abb58fbbb24ec31754b7a1245d1329c3bf0678391b`
   - Post-SHA: `31575c6894fb8b8c4144b7bc22848d2b1bd2672e17ecf8c1fee7b882ba1f5cab`
   - Backup: `exports/validation/orchestrator_owner_approval_stock_stopline_20260614/backups_rebuild_snapshot_20260613/app_pre_rebuild_snapshot_20260614_063834_0500.db`

3. C3 policy materialization:
   - Command used env gate: `ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1`
   - Backup: `exports/validation/orchestrator_owner_approval_stock_stopline_20260614/backups_c3_owner_stock_approval/app_before_agent8_c3_policy_materialization_20260614_064239.db`
   - Source status counts: `FRESH=17`
   - Gate status counts: `PASS=9`
   - Final DB SHA: `5a53f2b0e15c2127a088d41ddb11740c5b63ef1ac06d595a1423fdf329608f8e`

## Validation

- Owner-evidence dry-run: `candidate_event_count=9`, `blocked_count=0`, `is_safe_to_apply=true`
- Copied DB apply: `applied_rows=9`, backup/integrity checks `ok`
- Production idempotency dry-run after apply: `candidate_event_count=0`, `existing_count=9`
- Negative ledger query after production apply: no rows returned
- Snapshot rebuild target stats: `419` rows, `9123` current stock, `475` inbound stock
- Strict source freshness: `ok=true`, evidence `exports/validation/orchestrator_owner_approval_stock_stopline_20260614/validate_policy_source_freshness_after_c3.json`
- Policy gate results: `ok=true`, evidence `exports/validation/orchestrator_owner_approval_stock_stopline_20260614/validate_policy_gate_results_after_c3.json`
- Operational stock integration: `status=GREEN`, `finding_count=267`, only retained warnings:
  - `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED=244`
  - `ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED=23`
- Operational stock daily truth: `status=GREEN`, `owner_trust_status=GREEN_DECISION_GRADE`, `exception_count_total=0`
- Focused tests:
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_materialize_governed_stock_repairs.py tests/test_apply_rebuild_snapshot_production_safe.py tests/test_policy_materialization_c3.py`
  Result: `41 passed`.
- Final integrity check: `ok`
- Final DB guard: `scripts/check_no_db_tracked.sh` -> `DB guard OK`
- Daily ops final verification: `0/10` loaded and quiet.

## Retained Visibility

The 267 operational-stock warnings remain visible by design. They are quarantine warnings, not publication blockers, and are excluded from product-level stock, COGS, profit, and SKU publication truth.

The C3 exception queue still has accepted active controls, but the daily truth run reports `exception_count_total=0` and all release gates pass for owner publication.

## Rollback

Rollback to before the owner-approved stock event apply:

```bash
cp exports/validation/orchestrator_owner_approval_stock_stopline_20260614/backups_prod_stock_approval/app_2026-06-14_063651.db db/app.db
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
```

Rollback to before the snapshot rebuild:

```bash
cp exports/validation/orchestrator_owner_approval_stock_stopline_20260614/backups_rebuild_snapshot_20260613/app_pre_rebuild_snapshot_20260614_063834_0500.db db/app.db
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
```

Rollback to before C3 materialization only:

```bash
cp exports/validation/orchestrator_owner_approval_stock_stopline_20260614/backups_c3_owner_stock_approval/app_before_agent8_c3_policy_materialization_20260614_064239.db db/app.db
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
```
