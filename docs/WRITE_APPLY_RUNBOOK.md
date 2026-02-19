# WRITE_APPLY_RUNBOOK

## Purpose
Provide one copy/paste-safe process for any write-side script protected by env + `--apply`.

## Contract
1. Default mode is dry-run.
2. Apply is allowed only when both are true:
   - matching env gate is set to `1`
   - `--apply` flag is passed
3. DB backup is mandatory before write-side apply.

## Preflight (required)
```bash
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml
python3 scripts/validate_params.py --strict
```

## DB Backup (required before apply)
```bash
mkdir -p db/backups
cp db/app.db "db/backups/app.db.pre_apply_$(date +%Y%m%d_%H%M%S).sqlite"
```

## Generic Apply Pattern
```bash
ENABLE_<GATE>=1 python3 scripts/<write_script>.py --apply
```

## Example (cashflow rebuild apply)
```bash
ENABLE_CASHFLOW_WRITE=1 python3 scripts/rebuild_cashflow_calendar.py --apply
```

## Rollback
1. Revert code:
```bash
git revert <newest_commit> ... <oldest_commit>
```
2. Restore DB:
```bash
cp db/backups/app.db.pre_apply_<timestamp>.sqlite db/app.db
```
3. Re-run minimum gates:
```bash
python3 scripts/validate_params.py --strict
scripts/check_no_db_tracked.sh
```
