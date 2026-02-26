# As-Of Date Authority Contract

## Purpose
Define one deterministic rule for selecting `as_of` in strict daily diagnostics and autopilot flows.

## Authority Rule
Order of precedence:
1. Explicit CLI `--as-of YYYY-MM-DD`.
2. Latest complete day from `exports/daily/<YYYY-MM-DD>/daily_ops_report.json`.
3. Non-strict fallback only: `today`.

Strict mode forbids fallback-to-today when no complete day exists.

## Complete-Day Definition
`exports/daily/<day>/daily_ops_report.json` is complete only if:
- file exists and is valid JSON object,
- `as_of` equals `<day>`,
- `status` is `GREEN` or `RED`,
- `ok` is a boolean.

If any check fails, the day is not complete.

## Enforced Scripts
- `scripts/system_doctor.py`
- `scripts/build_domain_scorecards.py`
- `scripts/build_daily_ops_timings.py`
- `scripts/build_green_streak_tracker.py`
- `scripts/run_daily_autopilot.py`
- `scripts/validate_as_of_consistency.py`

## No Mixed-Date Writes
- Required daily artifacts for one run must all resolve to the same `as_of`.
- Mixed `as_of` payloads inside `exports/daily/<as_of>/` are forbidden.
- Required convergence set:
  - `exports/daily/<as_of>/daily_ops_report.json`
  - `exports/daily/<as_of>/po_scorecard.json`
  - `exports/daily/<as_of>/inventory_scorecard.json`
  - `exports/daily/<as_of>/cashflow_scorecard.json`
  - `exports/daily/<as_of>/truth_drift_report.json`
  - `exports/perf/<as_of>/daily_ops_timings.json`
  - `exports/diagnostics/<as_of>/system_health.json`
  - `exports/exceptions/<as_of>/exceptions.json`

All scripts above must use `scripts/resolve_as_of_date.py`.

## Fail-Closed Conditions
- Strict run with missing complete day: non-zero exit.
- Invalid explicit `--as-of` format/date: non-zero exit.

## Validation Contract
- `tests/test_as_of_date_authority_contract.py` must pass.
- Contract is considered broken if any enforced script resolves a different `as_of` for the same inputs.
- `tests/test_as_of_consistency_contract.py` must pass.
