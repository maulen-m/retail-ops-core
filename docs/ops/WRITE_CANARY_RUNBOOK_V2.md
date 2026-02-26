# Write Canary Runbook V2

## Purpose
Execute a DB-only write canary with strict safety controls and reversible evidence.

## Scope
- No production DB mutation.
- Canary writes occur only in `exports/canary/<YYYY-MM-DD>/db_canary.sqlite`.
- Source DB is copied before canary execution.

## Safety Contract
- Default mode: dry-run.
- Apply mode requires BOTH:
  - environment gate: `ENABLE_WRITE_CANARY_APPLY=1`
  - CLI flag: `--apply`
- Backup is mandatory before apply.
- Rollback proof is mandatory and hash-verified.

## Command
Dry-run:
```bash
python3 scripts/run_write_canary.py \
  --db db/app.db \
  --as-of <YYYY-MM-DD> \
  --strict
```

Apply (canary-only):
```bash
ENABLE_WRITE_CANARY_APPLY=1 \
python3 scripts/run_write_canary.py \
  --db db/app.db \
  --as-of <YYYY-MM-DD> \
  --max-rows 5 \
  --idempotence-key V12_CANARY \
  --apply \
  --strict
```

## Outputs
- `exports/canary/<YYYY-MM-DD>/write_canary_report.json`
- `exports/canary/<YYYY-MM-DD>/write_canary_report.md`
- `exports/canary/<YYYY-MM-DD>/db_diff_summary.json`
- `exports/canary/<YYYY-MM-DD>/db_diff_summary.md`
- `exports/canary/<YYYY-MM-DD>/rollback_proof.json`
- `exports/canary/<YYYY-MM-DD>/db_backup_pre_canary.sqlite`

## Rollback
The canary DB can be reset with:
```bash
cp exports/canary/<YYYY-MM-DD>/db_backup_pre_canary.sqlite \
   exports/canary/<YYYY-MM-DD>/db_canary.sqlite
```

## Verification
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_write_canary_contract.py`
- `python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml`
