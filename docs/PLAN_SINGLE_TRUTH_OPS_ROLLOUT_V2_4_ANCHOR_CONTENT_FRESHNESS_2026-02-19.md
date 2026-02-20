# Plan: Single-Truth Ops Rollout v2.4 (Anchor Content Freshness)

## Scope
- Add content-based CRM anchor freshness checks (fail-closed).
- Add deterministic `ops_status` command for daily operator health checks.
- Keep warning job installed by default and add alert spam guard.
- Keep anchor path authority centralized in `config/anchors/README.md`.
- No DB write/apply behavior in this rollout.

## Hard Gate Chain (canonical)
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_single_truth_system.py`
- `scripts/lint_docs.sh`
- `scripts/check_no_db_tracked.sh`

## Ops Stop-Line Checks (must pass)
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_anchor_health.py --project-root ~/Docs/Autonomous_business`
- docs/config banned-path sweep via current lint contract (`scripts/lint_docs.sh` + contract tests)

## Targeted Test Coverage (required)
- Content freshness parsing tests:
  - max-date lag fail-closed
  - future content-date fail-closed
  - parse/import failures fail-closed
- Warning job spam guard tests:
  - alert on failure transition
  - suppress repeated failures inside cooldown window
  - re-alert after recovery transition
- `ops_status.py` determinism tests:
  - exit `0` only when anchor health + validate-only are green
  - non-zero on any underlying failure

## Stop-the-Line Criteria
- Any canonical gate command exits non-zero.
- `--validate-only` fails or reports runtime/import mismatch.
- Anchor health fails (missing/broken symlink, stale content, stale mtime, or future skew/content-date breach).
- Docs/config path contracts fail lint/tests.
- Any new auto-fix path attempts DB writes without explicit env gate + `--apply`.
