# Agent 7 - C3 Rematerialize And Owner Brief Verification

Mode: read-only validation and owner-brief verification agent after Agent 6.

Status: UNBLOCKED FOR LIGHTWEIGHT READ-ONLY FINAL VERIFICATION.

Orchestrator review:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_6.md`

## Mission After Unblocked

Verify Agent 6 source-refresh execution outputs, confirm whether the current owner brief is valid, and produce a concise final closeout for this wave.

Do not force green. Current expected status is `RED_BLOCKED`.

## Required Inputs

Read:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_6.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_6_source_refresh_execution_closeout.md`
- `~/Docs/Autonomous_business/runs/agent6_c3_source_refresh/daily_runner_agent6_c3_source_refresh_check.json`
- `~/Docs/Autonomous_business/exports/operational_stock_daily_truth/2026-05-03/agent6-c3-source-refresh-check/owner_blocked_brief.md`
- `~/Docs/Autonomous_business/exports/operational_stock_daily_truth/2026-05-03/agent6-c3-source-refresh-check/exception_report.md`
- `~/Docs/Autonomous_business/exports/operational_stock_daily_truth/2026-05-03/agent6-c3-source-refresh-check/run_lineage.json`

## Verification Rules

- Prefer read-only validation and artifact parsing.
- Do not write DB rows.
- Do not re-run slow C3 materialization or the daily runner unless Agent 6 artifacts are missing or internally inconsistent.
- It is acceptable to run read-only validators:

```bash
python3 scripts/validate_policy_source_freshness.py --db db/app.db --as-of 2026-05-03 --strict
python3 scripts/validate_policy_gate_results.py --db db/app.db --strict
```

These are expected to fail while real blockers remain.

## Closeout Requirements

Write a closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- owner brief paths;
- validator pass/fail;
- remaining blockers;
- exact human owner actions if required;
- clear recommendation whether publication can proceed.
- recommended next wave split.

ASSIGNED CLOSEOUT: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_7_c3_rematerialize_owner_brief_closeout.md`
