# PLAN_SINGLE_TRUTH_OPS_ROLLOUT_V2_6_OBSERVABILITY_2026-02-20

## Objective
Produce a deterministic daily ops artifact that makes go/no-go status and drift visible without manual log digging.

## Inputs
- `python3 scripts/ops_status.py --project-root <repo>`
- `python3 scripts/check_anchor_health.py --project-root <repo>`
- `python3 scripts/build_ops_drift_pack.py --as-of <YYYY-MM-DD>`

## Outputs
- `exports/validation/daily/<YYYY-MM-DD>/single_truth_drift_pack.md`
- `exports/validation/daily/<YYYY-MM-DD>/single_truth_drift_pack.json`

## Alert policy
- `PASS`: all checks green, no unresolved stop-line findings.
- `WARN`: checks pass but drift counters are non-zero and below stop thresholds.
- `CRITICAL`: any anchor-health failure, ops-status failure, or unresolved COGS rows > 0.
- `STOP_LINE`: any strict gate failure or write-side gate contract breach.

## Determinism contract
1. JSON keys are stable and sorted by serializer.
2. Markdown sections are fixed and ordered.
3. Running twice with the same inputs yields the same payload values.
4. Script is read-only for DB and external systems.

## Validation
1. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_build_single_truth_drift_pack.py tests/test_build_ops_drift_pack.py`
2. `python3 scripts/build_ops_drift_pack.py --as-of <YYYY-MM-DD> --output-root exports/validation/daily`
3. `python3 scripts/ops_status.py --project-root ~/Docs/Autonomous_business`

## Rollback
- `git revert <commit_sha_that_added_v2_6_plan_or_script>`
- Re-run `python3 scripts/ops_status.py --project-root ~/Docs/Autonomous_business`
