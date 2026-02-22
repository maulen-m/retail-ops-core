# Write Canary V6 Apply Board (Draft)

## Purpose
Execute one reversible write canary in production conditions after V5 controls are green.

## Scope Limits (fail-closed)
- single store only
- bounded dataset size (`N <= X`, set before run)
- one command only per run window
- stop immediately on any gate failure

## Preconditions
1. `python3 scripts/validate_write_side_gating.py` is PASS.
2. Active board evidence contains `full_gates_green_final.md`.
3. No open stop-line issues for shipment/import workflows.

## Apply Contract
Apply is allowed only with both controls:
- `ENABLE_<GATE>=1`
- explicit `--apply`

Example pattern:
```bash
ENABLE_<GATE>=1 python3 scripts/<write_script>.py --apply
```

## Required DB backup before apply
```bash
mkdir -p db/backups
cp db/app.db "db/backups/app.db.pre_v6_canary_$(date +%Y%m%d_%H%M%S).sqlite"
```

## Execution Sequence
1. Run dry-run first and archive output under `exports/validation/<date>/`.
2. Confirm pre-apply gates:
   - `python3 scripts/validate_params.py --strict`
   - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
3. Run canary apply with explicit env gate + `--apply`.
4. Re-run full gates immediately.
5. Record evidence (command outputs + DB backup path + commit SHA + rollback command) in board evidence doc.

## Post-apply required gates
- `python3 scripts/validate_write_side_gating.py`
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`
- `python3 scripts/ops_status.py --project-root <REPO_PATH>`

## Rollback
1. Revert apply commit(s):
```bash
git revert <newest_canary_sha> ... <oldest_canary_sha>
```
2. Restore DB backup:
```bash
cp db/backups/app.db.pre_v6_canary_<timestamp>.sqlite db/app.db
```
3. Re-run minimum recheck gates:
```bash
python3 scripts/validate_params.py --strict
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
bash scripts/check_no_db_tracked.sh
```
