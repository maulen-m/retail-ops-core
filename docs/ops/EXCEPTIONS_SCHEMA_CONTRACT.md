# Exceptions Schema Contract

## Purpose
Define the fail-closed schema for autopilot exception artifacts.

## Artifact Path
- `exports/exceptions/<YYYY-MM-DD>/exceptions.json`
- `exports/exceptions/<YYYY-MM-DD>/exceptions.md`

## Top-Level Required Fields
- `generated_at`
- `as_of`
- `status` (`GREEN` or `RED`)
- `ok` (boolean)
- `steps` (array)
- `exceptions` (array)

## Exception Row Required Fields
- `id` (stable string id)
- `step`
- `domain`
- `severity` (`critical|high|medium|low`)
- `owner`
- `recommended_action`
- `evidence_paths` (non-empty list of strings)
- `rc` (integer)
- `reason`

## Fail-Closed Rules
- Any missing required field => schema FAIL.
- `ok=true` is invalid when critical exceptions exist.
- `status=GREEN` is invalid when critical exceptions exist.
- Critical exceptions must be surfaced by System Doctor governance checks.

## Validation Command
```bash
python3 scripts/validate_exceptions_schema.py \
  exports/exceptions/<YYYY-MM-DD>/exceptions.json \
  --strict
```

## Owning Tests
- `tests/test_exceptions_schema_contract.py`
- `tests/test_daily_autopilot_contract.py`
