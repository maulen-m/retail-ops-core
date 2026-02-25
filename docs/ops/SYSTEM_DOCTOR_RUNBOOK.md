# System Doctor Runbook

## Purpose
`scripts/system_doctor.py` is the fail-closed diagnostic entrypoint for runtime, truth, domain, execution, and governance health checks.

## Entrypoint
```bash
python3 scripts/system_doctor.py --strict --project-root <REPO_PATH>
```

## Outputs
- `exports/diagnostics/<YYYY-MM-DD>/system_health.json`
- `exports/diagnostics/<YYYY-MM-DD>/system_health.md`
- `exports/diagnostics/<YYYY-MM-DD>/system_health_checks.json`

## Layer order (fail-closed)
1. `runtime`
2. `truth`
3. `domain`
4. `execution`
5. `governance`

If any check in a layer fails, later layers do not execute.

## Notes
- `--strict` returns non-zero on any failed check.
- Default mode is read-only.
- Missing required artifacts (for example daily report or timing artifacts) are treated as failures.
