# Daily Ops Performance Budgets

## Purpose
Define measurable timing budgets for daily ops benchmarking and make regressions fail-closed.

## Artifact Contract
- `exports/perf/<YYYY-MM-DD>/daily_ops_timings.json`
- `exports/perf/<YYYY-MM-DD>/daily_ops_timings.md`

Built by:
```bash
python3 scripts/build_daily_ops_timings.py --strict --project-root <REPO_PATH>
```

Validated by:
```bash
python3 scripts/validate_daily_ops_timing_artifact.py exports/perf/<YYYY-MM-DD>/daily_ops_timings.json --strict
```

## Budget Rules
- Default max average total run time: `900s` (`--max-avg-total-sec`).
- Any non-zero run exit code fails the timing contract.
- Any parity mismatch between repeated runs fails the timing contract.

## V10 Scale Rule
- Throughput changes are valid only when parity remains intact for:
  - selected order IDs,
  - assemble success/failure sets,
  - waybill download/existing/missing sets,
  - bundle grouping counts.

## Promotion Rule
Do not claim performance improvement without:
1. parity passing,
2. timing artifact generated,
3. budget check passing.
