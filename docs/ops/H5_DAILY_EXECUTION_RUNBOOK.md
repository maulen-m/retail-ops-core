# H5 Daily Execution Runbook

## Purpose
Run a deterministic daily proving loop with low human time and strict fail-closed gates.

## Operator Rule
- Do not act on cash/PO/inventory facts unless today's H5 run is GREEN.
- If any hard gate is RED: stop-the-line, fix root cause, rerun.

## Inputs
- `<REPO_PATH>` root.
- `<DAY>` in Asia/Qyzylorda.

## Daily Commands
```bash
cd <REPO_PATH>
DAY="<YYYY-MM-DD>"

# Preferred one-command chain (doctor + as_of + exceptions + parity + artifact gate):
python3 scripts/run_h5_proving_day.py --strict --project-root . --as-of "$DAY"

# Expanded commands (debug mode):
python3 scripts/system_doctor.py --strict --project-root . --as-of "$DAY"
python3 scripts/validate_as_of_consistency.py --strict --project-root . --as-of "$DAY"
python3 scripts/triage_exceptions.py \
  --exceptions "exports/exceptions/$DAY/exceptions.json" \
  --playbook docs/ops/EXCEPTION_PLAYBOOK.md \
  --allowlist config/exceptions_allowlist.json \
  --strict
python3 scripts/validate_h5_artifact_set.py --strict --project-root . --as-of "$DAY"
```

## Read-Only Human Review (target <5%)
- `exports/diagnostics/<DAY>/system_health.md`
- `exports/exceptions/<DAY>/exceptions_triage.md`

## Decision Policy
- GREEN day:
  - You may trust `exports/daily/<DAY>/po_scorecard.json`, `inventory_scorecard.json`, `cashflow_scorecard.json`.
- RED day:
  - No operational/capital decisions from daily scorecards.
  - Fix root cause and rerun same day.

## Weekly Rollup
```bash
python3 scripts/build_weekly_health_scorecard.py --as-of "$DAY" --strict
```

## Streak Tracking
```bash
python3 scripts/build_green_streak_tracker.py --as-of "$DAY" --strict --target-days 14
```

## Evidence Paths
- Daily H5 validator:
  - `exports/validation/h5_artifact_set/<DAY>/h5_artifact_set_report.json`
  - `exports/validation/h5_artifact_set/<DAY>/h5_artifact_set_report.md`
- One-command proving summary:
  - `exports/validation/h5_proving_day/<DAY>/h5_proving_day_summary.json`
  - `exports/validation/h5_proving_day/<DAY>/h5_proving_day_summary.md`
- Streak:
  - `exports/health/streak/<DAY>/green_streak.json`
- Weekly:
  - `exports/health/weekly/<YYYY-W##>/weekly_health_scorecard.json`
