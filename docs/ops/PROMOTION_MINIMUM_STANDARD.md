# Promotion Minimum Standard (Fail-Closed)

## Purpose
Define the non-optional merge standard when GitHub branch protections cannot enforce required checks.

## Authority
- Scheduler/workflow authority: `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`
- Write-side apply authority: `docs/WRITE_APPLY_RUNBOOK.md`
- Board evidence authority: latest `docs/OPS_ROLLOUT_EVIDENCE_BOARD_*.md`

## Mandatory Merge Checklist
No merge is allowed unless all items below are satisfied.

1. Promotion evidence doc is present for the active board.
2. Evidence doc contains:
   - PR link
   - merge SHA
   - required gate checklist
   - rollback commands
   - explicit no-apply statement (unless approved apply was executed and documented)
3. Evidence doc contains no placeholder tokens (`TBD`, `TODO`).
4. Evidence doc points to final gate transcript artifact:
   - `full_gates_green_final.md`
5. Oracle pack path for the promotion is recorded in the evidence doc or session log.

## Required Gate Set
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`
- `python3 scripts/ops_status.py --project-root <REPO_PATH>`

## CI Compensating Control
CI must fail if promotion evidence for the active board contains placeholders or misses `full_gates_green_final.md`.
