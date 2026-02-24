# Daily Ops Timing SLO Policy

## Purpose
Define how daily-ops runtime performance is measured without introducing fail-open behavior.

## Scope
- `scripts/run_kaspi_daily_ops.py`
- `scripts/benchmark_kaspi_daily_ops.py`
- `scripts/validate_daily_ops_timing_artifact.py`

## Measurement Contract
- Runtime metrics are artifact-driven, not log-scraped.
- Required fields:
  - `as_of`
  - `profile`
  - `runs[]`
  - `runs[].steps[]`
  - `runs[].steps[].duration_sec`
  - `runs[].total_duration_sec`
  - `step_stats`
- Artifact validator is fail-closed in strict mode:
  - `python3 scripts/validate_daily_ops_timing_artifact.py <artifact.json> --strict`

## Profiles
- `today-fast`: strict current-day checks (no overdue expansion).
- `catch-up`: overdue-inclusive safety profile.

## CI Policy
- CI validates artifact shape and correctness gates.
- CI does **not** fail on raw wall-clock thresholds.
- Performance regressions are reviewed by comparing benchmark artifacts:
  - `benchmark_timings.json`
  - `benchmark_timings.md`

## Stop-Line Rules
- Missing or malformed timing artifact in promotion evidence.
- Any correctness parity mismatch while claiming speed improvement.
- Any write/apply path enabled by default in benchmark/orchestrator flows.
