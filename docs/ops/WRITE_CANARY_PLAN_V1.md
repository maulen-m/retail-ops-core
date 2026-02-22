# Write Canary Plan V1

## Purpose
Define a reversible write-side canary process without enabling writes by default.

## Preconditions
- All strict gates green.
- Write-side manifest validator green:
  - `python3 scripts/validate_write_side_gating.py`
  - `config/write_side_gating_manifest.yaml` contains every write-capable command.
- Rollback operator is available.
- Board V5 policy: **No apply execution is allowed in board V5**.

## Safety model
- Dual gate required for every write path:
  - environment gate set (`ENABLE_*`)
  - explicit CLI `--apply`
- Default mode is dry-run.
- Any missing gate must fail closed.

## Canary steps
1. Validate contracts and strict chain in dry-run mode.
   - `python3 scripts/validate_write_side_gating.py`
2. Run canary command in dry-run and store artifact logs.
3. Review output diff and rollback readiness.
4. Execute apply only if explicitly approved and gated.
5. Re-run strict chain immediately after canary.

## Stop-line criteria
- Any write path reachable without env gate + `--apply`.
- Any unexpected mutation in dry-run mode.
- Any strict gate failure after canary.

## Rollback
1. Revert canary commit(s).
2. Restore affected data from backup if writes were executed.
3. Re-run minimum gates:
   - `python3 scripts/validate_params.py --strict`
   - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
   - `bash scripts/check_no_db_tracked.sh`
