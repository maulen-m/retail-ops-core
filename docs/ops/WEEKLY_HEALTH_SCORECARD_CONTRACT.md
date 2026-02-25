# Weekly Health Scorecard Contract

## Purpose
Provide one deterministic weekly view of operations reliability and safety risk.

## Builder
```bash
python3 scripts/build_weekly_health_scorecard.py --strict --as-of <YYYY-MM-DD>
python3 scripts/build_green_streak_tracker.py --strict --as-of <YYYY-MM-DD>
```

## Inputs
- `exports/daily/<YYYY-MM-DD>/daily_ops_report.json`
- `exports/diagnostics/<YYYY-MM-DD>/system_health.json`

## Outputs
- `exports/health/weekly/<YYYY-WW>/weekly_health_scorecard.json`
- `exports/health/weekly/<YYYY-WW>/weekly_health_scorecard.md`
- `exports/health/streak/<YYYY-MM-DD>/green_streak.json`
- `exports/health/streak/<YYYY-MM-DD>/green_streak.md`

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
- `green_streak_days`
- `green_streak_target_days`
- `green_streak_status`

## Fail-closed rules
- Missing daily or diagnostics artifacts in the target week produce errors.
- `--strict` returns non-zero when errors exist.
- Green streak cannot be marked valid without linked gate transcript evidence (`full_gates_green_final.md`).
