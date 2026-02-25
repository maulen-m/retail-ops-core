# DB Migrations Runbook

## Purpose
Prevent runtime schema drift by enforcing deterministic migration + validation before operational scripts.

## Contract
- Schema gate entrypoint: `scripts/validate_schema.py`
- Validator must fail closed on missing required tables/columns.
- Operational checks (`validate_params --strict`, `system_doctor --strict`) must include schema validation.

## Operator Flow
1. Validate schema:
   - `python3 scripts/validate_schema.py --db db/app.db`
2. If failure:
   - stop all apply/write workflows,
   - fix migration/table contract first,
   - rerun strict gate chain.

## Rollback
- Code rollback: `git revert <schema-change-commit>`
- DB rollback (if migrations applied): restore from backup snapshot and re-run:
  - `python3 scripts/validate_schema.py --db db/app.db`
  - `python3 scripts/validate_params.py --strict`
