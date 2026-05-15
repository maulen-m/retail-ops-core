# Agent 14 - C3 Policy And Owner Brief Rematerialization After Agent 13

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_14_c3_owner_brief_rematerialization_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_source_truth_blocker_unblock_wave2/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/agent_13_serial_production_apply_closeout.md`
6. this starter prompt
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_source_truth_blocker_unblock_wave2/ORCHESTRATOR_REVIEW_AFTER_AGENT_13.md`

## Mission

Rematerialize C3 policy state and the daily owner brief after Agent 13 production apply as a limited blocked-brief lane.

Do not claim owner publication green. Ads source truth remains blocked after WA1/WA2 YELLOW closeouts, so this lane must preserve ads blockers and produce a blocked/YELLOW owner-state artifact unless every strict gate unexpectedly passes without weakening any validator.

Do not apply ads rows, do not convert missing ads evidence to zero spend, and do not use `--allow-green-owner-output`.

## Required Flow

Run from `~/Docs/Autonomous_business`.

```bash
ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 PYTHONDONTWRITEBYTECODE=1 python3 scripts/materialize_c3_policy_state.py --db db/app.db --policy config/operational_decision_policy.yaml --as-of 2026-05-03 --run-id source-truth-wave2-final --backup-dir runtime/backups --apply --json
python3 scripts/validate_policy_source_freshness.py --db db/app.db --as-of 2026-05-03 --strict
python3 scripts/validate_policy_gate_results.py --db db/app.db --strict
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_operational_stock_daily_truth.py --db db/app.db --as-of 2026-05-03 --output-root exports/operational_stock_daily_truth --run-id source-truth-wave2-final --require-c3-policy --json
scripts/lint_docs.sh
scripts/check_no_db_tracked.sh
```

If any strict validator remains RED, keep owner brief blocked and report exact blockers. Do not fake green.

Expected current blocker family:

- `ADS_REFRESH_MISSING`
- `ADS_COVERAGE_MISSING`

If strict validators fail only because ads remain blocked, close `YELLOW`, not `RED`.

## Closeout Requirements

Your closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- policy materialization backup path;
- source freshness and gate statuses;
- owner brief path;
- exact remaining blockers;
- final readiness statement.
