# CI_HEADLESS_PLAN

## Goal
Run the single-truth ops gate chain in a clean, headless environment without machine-local absolute path dependencies.

## Scope
- Validate fail-closed operations checks.
- Validate docs/path contracts.
- Validate write-side gating contract.
- Do not run write/apply workflows.

## Required jobs
1. `python3 scripts/validate_params.py --strict`
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
3. `python3 scripts/run_contract_suite.py --fixture small`
4. `python3 scripts/validate_single_truth_system.py`
5. `scripts/lint_docs.sh`
6. `scripts/check_no_db_tracked.sh`
7. `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
8. `python3 scripts/check_anchor_health.py --project-root <repo>`
9. `python3 scripts/ops_status.py --project-root <repo>`

## Headless path rules
1. Active docs must not contain user-specific absolute paths (`~/...`).
2. Anchor path contract is centralized in `config/anchors/README.md`.
3. All scripts that support `--project-root` must be runnable from `/tmp`.

## Fixture expectations
- Workbook fixture for parser tests must be generated in temp dirs.
- Tests must not rely on local symlink targets.

## Rollback
- `git revert <ci_headless_plan_commit_sha>`
- Re-run docs/path contract tests and lint.
