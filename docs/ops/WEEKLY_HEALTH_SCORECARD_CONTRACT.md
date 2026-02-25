# Weekly Health Scorecard Contract

## Purpose
Provide one deterministic weekly view of operations reliability and safety risk.

## Builder
```bash
python3 scripts/build_weekly_health_scorecard.py --strict --as-of <YYYY-MM-DD>
```

## Inputs
- `exports/daily/<YYYY-MM-DD>/daily_ops_report.json`
- `exports/diagnostics/<YYYY-MM-DD>/system_health.json`

## Outputs
- `exports/health/weekly/<YYYY-WW>/weekly_health_scorecard.json`
- `exports/health/weekly/<YYYY-WW>/weekly_health_scorecard.md`

## Required fields
- `week`
- `as_of`
- `days_evaluated`
- `green_days`
- `red_days`
- `daily_green_rate_pct`
- `avg_steps_failed`
- `avg_stores_red`
- `days[]`

## Fail-closed rules
- Missing daily or diagnostics artifacts in the target week produce errors.
- `--strict` returns non-zero when errors exist.
