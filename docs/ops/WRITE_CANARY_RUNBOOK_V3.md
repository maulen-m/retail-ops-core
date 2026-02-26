# Write Canary Runbook V3

## Purpose
Graduate canary execution from DB-only rehearsal to bounded production-DB canary,
while preserving fail-closed safety.

## Modes
- `db_only`:
  - writes are isolated to `exports/canary/<as_of>/db_canary.sqlite`
  - apply gate: `ENABLE_WRITE_CANARY_APPLY=1` + `--apply`
- `prod_db`:
  - write target is the `--db` path directly
  - apply gate: `ENABLE_PROD_DB_CANARY_WRITE=1` + `--apply`
  - backup is mandatory before any apply

## Safety Contract
- Dry-run default (`--apply` absent) for all modes.
- Apply requires BOTH explicit env gate and `--apply`.
- Backup must exist before any apply.
- Rollback proof artifact is required for every run.
- No live API writes are involved in this runbook.

## Commands

### 1) DB-only dry-run
```bash
python3 scripts/run_write_canary.py \
  --mode db_only \
  --db db/app.db \
  --as-of <YYYY-MM-DD> \
  --strict
```

### 2) DB-only apply (bounded)
```bash
ENABLE_WRITE_CANARY_APPLY=1 \
python3 scripts/run_write_canary.py \
  --mode db_only \
  --db db/app.db \
  --as-of <YYYY-MM-DD> \
  --max-rows 5 \
  --idempotence-key HORIZON_H3_DB_ONLY \
  --apply \
  --strict
```

### 3) Prod-DB dry-run (no writes)
```bash
python3 scripts/run_write_canary.py \
  --mode prod_db \
  --db db/app.db \
  --as-of <YYYY-MM-DD> \
  --strict
```

### 4) Prod-DB apply (explicitly gated)
```bash
ENABLE_PROD_DB_CANARY_WRITE=1 \
python3 scripts/run_write_canary.py \
  --mode prod_db \
  --db db/app.db \
  --as-of <YYYY-MM-DD> \
  --max-rows 3 \
  --idempotence-key HORIZON_H3_PROD_DB \
  --apply \
  --strict
```

## Output Artifacts
- `exports/canary/<as_of>/write_canary_report.json`
- `exports/canary/<as_of>/write_canary_report.md`
- `exports/canary/<as_of>/db_diff_summary.json`
- `exports/canary/<as_of>/db_diff_summary.md`
- `exports/canary/<as_of>/rollback_proof.json`
- `exports/canary/<as_of>/db_backup_pre_canary.sqlite` (`db_only`)
- `exports/canary/<as_of>/db_backup_pre_prod_apply.sqlite` (`prod_db`, unless overridden)

## Rollback
For `db_only`:
```bash
cp exports/canary/<as_of>/db_backup_pre_canary.sqlite \
   exports/canary/<as_of>/db_canary.sqlite
```

For `prod_db`:
```bash
cp exports/canary/<as_of>/db_backup_pre_prod_apply.sqlite db/app.db
```

## Required Validation
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_write_canary_contract.py \
  tests/test_write_canary_prod_db_gating_contract.py \
  tests/test_write_canary_prod_db_backup_required.py
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml
```
