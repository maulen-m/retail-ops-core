# Shipment Preflight

Purpose: fail-closed blocker before shipping/waybill workflow so shipment cannot run when critical integrity/runtime gates are red.

## Entrypoint
- `scripts/preflight_shipment.py`

## Checks (all required)
- `anchor_health`: `python3 scripts/check_anchor_health.py --project-root <repo>`
- `scheduler_validate_only`: `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `local_db_preflight`: run `scripts/check_local_app_db.py` with the same Python interpreter as the shipment preflight. Global accounting/economics publication validation remains a separate gate and does not block the daily shipping transport chain.
- `validate_single_truth_system`: `python3 scripts/validate_single_truth_system.py`
- `ops_status`: `python3 scripts/ops_status.py --project-root <repo>`

## Exit Contract
- Exit `0`: all checks green.
- Exit `1`: any check failed.

## Workflow integration
- `excel_ui/run_merged_build_waybills.command` runs this preflight immediately after `scripts/ops_preflight.py --shipping`.
- If preflight fails, workflow stops before API shipping and waybill download steps.

## Output
- Human summary by default.
- `--json` for machine-readable report.
- `--output <path>` to save report file.

## Fail-closed policy
- No check is warn-only.
- Any non-zero check return code blocks shipment flow.
