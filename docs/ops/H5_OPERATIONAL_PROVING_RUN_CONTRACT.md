# H5 Operational Proving Run Contract

## Purpose
Define the production proving window contract for final autonomy closure:
- 14 consecutive daily cycles,
- all hard gates green,
- fail-closed exception handling.

## Run Window
- Duration: 14 consecutive days.
- Day key: `<YYYY-MM-DD>` in Asia/Qyzylorda timezone.
- Every day must produce a complete artifact set.

## Required Daily Artifacts
- `exports/daily/<day>/daily_ops_report.json`
- `exports/exceptions/<day>/exceptions.json`
- `exports/diagnostics/<day>/system_health.json`
- `exports/perf/<day>/daily_ops_timings.json`
- `exports/validation/<day>/single_truth_drift_pack.json`

## Weekly Artifacts
- `exports/health/weekly/weekly/<YYYY-W##>/weekly_health_scorecard.json`

## Hard Gates (daily)
- `python3 scripts/system_doctor.py --strict --project-root <REPO_PATH>`
- `python3 scripts/validate_as_of_consistency.py --strict --project-root <REPO_PATH> --as-of <day>`
- `python3 scripts/triage_exceptions.py --strict --exceptions exports/exceptions/<day>/exceptions.json`

## Stop-the-Line
- Any hard gate failure.
- Missing artifact for a day.
- Critical exception not fixed or explicitly allowlisted.
- Any uncontrolled write path activation.

## Completion
Run is complete only when:
- all 14 days are green,
- no artifact gaps,
- final board evidence references all day folders and weekly summaries.
